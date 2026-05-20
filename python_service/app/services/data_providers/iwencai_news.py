"""
Iwencai (同花顺问财) Data Provider.
Integrates the Iwencai SkillHub skills into the data layer.
Supports: news, announcement, report channels via unified API.
API: https://openapi.iwencai.com/v1/comprehensive/search
"""

import os
import secrets
import logging
from typing import Dict, Any

import httpx

logger = logging.getLogger(__name__)

IWENCAI_BASE_URL = os.getenv("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
IWENCAI_API_KEY = os.getenv("IWENCAI_API_KEY", "")

# Channel → Skill ID mapping
CHANNEL_SKILL_MAP = {
    "news": "news-search",
    "announcement": "announcement-search",
    "report": "report-search",
}
SKILL_VERSION = "1.0.0"


def _generate_trace_id() -> str:
    """Generate a 64-character hex trace ID as required by the gateway."""
    return secrets.token_hex(32)


async def _iwencai_search(query: str, channel: str = "news", retry: bool = False) -> Dict[str, Any]:
    """
    Core search function for Iwencai OpenAPI.
    
    Args:
        query: Search keywords (supports Chinese)
        channel: One of 'news', 'announcement', 'report'
        retry: Whether this is a retry attempt
    
    Returns the raw API response (transparent passthrough per gateway spec).
    """
    api_key = IWENCAI_API_KEY or os.getenv("IWENCAI_API_KEY", "")
    if not api_key:
        return {"error": "IWENCAI_API_KEY not configured"}

    skill_id = CHANNEL_SKILL_MAP.get(channel, "news-search")
    url = f"{IWENCAI_BASE_URL}/v1/comprehensive/search"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Claw-Call-Type": "retry" if retry else "normal",
        "X-Claw-Skill-Id": skill_id,
        "X-Claw-Skill-Version": SKILL_VERSION,
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": _generate_trace_id(),
    }
    payload = {
        "channels": [channel],
        "app_id": "AIME_SKILL",
        "query": query,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"[iwencai-{channel}] HTTP {e.response.status_code} for query '{query}'")
        if not retry and e.response.status_code >= 500:
            return await _iwencai_search(query, channel, retry=True)
        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text}
    except httpx.TimeoutException:
        logger.error(f"[iwencai-{channel}] Timeout for query '{query}'")
        if not retry:
            return await _iwencai_search(query, channel, retry=True)
        return {"error": "Request timeout"}
    except Exception as e:
        logger.error(f"[iwencai-{channel}] Unexpected error: {e}")
        return {"error": str(e)}


# ────── Public API ──────

async def search_news(query: str) -> Dict[str, Any]:
    """Search financial news (财经新闻). Source: 同花顺问财."""
    return await _iwencai_search(query, channel="news")


async def search_announcements(query: str) -> Dict[str, Any]:
    """Search company announcements (公告). Covers A-share, HK, funds, ETFs."""
    return await _iwencai_search(query, channel="announcement")


async def search_reports(query: str) -> Dict[str, Any]:
    """Search research reports (研报). Covers analyst reports with ratings and target prices."""
    return await _iwencai_search(query, channel="report")


async def search_news_batch(queries: list[str]) -> list[Dict[str, Any]]:
    """Search multiple news queries concurrently."""
    import asyncio
    tasks = [search_news(q) for q in queries]
    return await asyncio.gather(*tasks)


async def search_comprehensive(query: str) -> Dict[str, Any]:
    """
    Search across all channels (news + announcement + report) simultaneously.
    Returns combined results from all sources for maximum coverage.
    """
    import asyncio
    results = await asyncio.gather(
        _iwencai_search(query, "news"),
        _iwencai_search(query, "announcement"),
        _iwencai_search(query, "report"),
    )
    combined = {"status_code": 0, "data": [], "channels_queried": ["news", "announcement", "report"]}
    for r in results:
        if r.get("status_code") == 0:
            combined["data"].extend(r.get("data", []))
    combined["total"] = len(combined["data"])
    return combined
