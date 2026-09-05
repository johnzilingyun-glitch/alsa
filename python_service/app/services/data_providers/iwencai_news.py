"""
Iwencai (同花顺问财) Data Provider.
Integrates the Iwencai SkillHub skills into the data layer.
Supports: news, announcement, report channels via unified API.
API: https://openapi.iwencai.com/v1/comprehensive/search
"""

import os
import secrets
import time
import logging
from typing import Dict, Any

import httpx

logger = logging.getLogger(__name__)

IWENCAI_BASE_URL = os.getenv("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
IWENCAI_API_KEY = os.getenv("IWENCAI_API_KEY", "")

# Circuit breaker: per-channel 401 "quota exhausted" cooldown.
# 2026-09: was process-lifetime (boolean); now TTL-backed so transient 401s
# don't permanently disable Iwencai for a long-running process. Also per-channel
# because the Iwencai API has separate quotas per channel — when news hits 401,
# announcement + report channels can still serve requests.
_quota_exhausted_until: Dict[str, float] = {}  # channel -> epoch seconds
# Default cooldown: 30 minutes. Tunable via IWENCAI_QUOTA_COOLDOWN_SECONDS.
_IWENCAI_QUOTA_COOLDOWN_SECONDS = int(os.getenv("IWENCAI_QUOTA_COOLDOWN_SECONDS", "1800"))

# Known quota-exhausted messages from the Iwencai API.
_QUOTA_EXHAUSTED_KEYWORDS = ("次数已用完", "quota", "rate limit", "insufficient balance")

# Channel → Skill ID mapping
CHANNEL_SKILL_MAP = {
    "news": "news-search",
    "announcement": "announcement-search",
    "report": "report-search",
}
SKILL_VERSION = "2.0.0"  # bumped from 1.0.0 — older versions may be rejected


def _is_quota_error(status_code: int, body: str) -> bool:
    """Check whether a 401/403 response indicates quota exhaustion vs. auth failure."""
    return status_code in (401, 403)


def _generate_trace_id() -> str:
    """Generate a 64-character hex trace ID as required by the gateway."""
    return secrets.token_hex(32)


def _is_quota_breaker_open(channel: str) -> bool:
    """Returns True if the quota circuit breaker is currently tripped for `channel`.

    Per-channel isolation: news tripping does NOT block announcement/report.
    """
    expiry = _quota_exhausted_until.get(channel, 0.0)
    if expiry <= 0:
        return False
    if time.time() >= expiry:
        # Cooldown expired — auto-reset
        logger.info(f"[iwencai-{channel}] Quota cooldown expired, resetting.")
        _quota_exhausted_until.pop(channel, None)
        return False
    return True


async def _iwencai_search(query: str, channel: str = "news", retry: bool = False) -> Dict[str, Any]:
    """
    Core search function for Iwencai OpenAPI.

    Args:
        query: Search keywords (supports Chinese)
        channel: One of 'news', 'announcement', 'report'
        retry: Whether this is a retry attempt

    Returns the raw API response (transparent passthrough per gateway spec).
    """
    # Fast-path skip when this channel's breaker is tripped.
    if _is_quota_breaker_open(channel):
        return {"error": "quota_exhausted", "status_code": 401, "data": []}

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
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        body = e.response.text
        logger.warning("[iwencai-%s] HTTP %s for query '%s'", channel, status, query)

        # Detect quota exhaustion — trip per-channel breaker so subsequent calls
        # on the same channel skip the API until cooldown expires (TTL-backed, 2026-09).
        if _is_quota_error(status, body):
            _quota_exhausted_until[channel] = time.time() + _IWENCAI_QUOTA_COOLDOWN_SECONDS
            logger.warning(
                "[iwencai-%s] Quota exhausted — disabling for %ds. "
                "(Other channels unaffected.)",
                channel, _IWENCAI_QUOTA_COOLDOWN_SECONDS,
            )
            return {"error": "quota_exhausted", "status_code": 401, "data": []}

        if not retry and status >= 500:
            return await _iwencai_search(query, channel, retry=True)
        return {"error": f"HTTP {status}", "detail": body}
    except httpx.TimeoutException:
        logger.warning("[iwencai-%s] Timeout for query '%s'", channel, query)
        if not retry:
            return await _iwencai_search(query, channel, retry=True)
        return {"error": "Request timeout"}
    except Exception as e:
        logger.error("[iwencai-%s] Unexpected error: %s", channel, e)
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
