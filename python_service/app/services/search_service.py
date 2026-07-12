import os
import logging

logger = logging.getLogger(__name__)
import re
import aiohttp
from typing import List, Dict, Any
import asyncio


# Determine if we're on a China-based server (check network environment)
# China servers typically can't reach DuckDuckGo/Google reliably
_IS_CHINA_SERVER = os.getenv("IS_CHINA_SERVER", "true").lower() in ("true", "1", "yes")


class SearchService:
    BLOCKED_SOURCE_DOMAINS = [
        "baidu.com", "baijiahao.baidu.com",
        "zhidao.baidu.com", "tieba.baidu.com", "wenku.baidu.com",
        "sogou.com", "360.cn", "so.com", "toutiao.com", "163.com",
    ]

    def __init__(self):
        self.max_results = 20
        self._ddg_timeout = 8  # Reduced from 12 — fail fast on China servers
        # SearXNG configuration
        self._searxng_base_url = os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")
        self._searxng_timeout = 15
        self._searxng_enabled = os.getenv("SEARXNG_ENABLED", "true").lower() in ("true", "1", "yes")
        # HTTP proxy for ddgs (primp doesn't read env vars)
        self._http_proxy = os.getenv("http_proxy", "")

    def _is_blocked_source(self, url: str) -> bool:
        return any(d in url for d in self.BLOCKED_SOURCE_DOMAINS)

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize text to defuse potential indirect prompt injection vectors."""
        if not text:
            return ""

        # 1. Defuse instruction overrides: e.g. "ignore previous instructions", "disregard instructions", etc.
        override_pattern = re.compile(
            r"\b(ignore|disregard|bypass|override)\s+(?:all\s+)?(?:previous\s+|system\s+|above\s+)?instructions\b",
            re.IGNORECASE
        )
        
        # 2. Defuse role modifications: e.g. "you are now a...", "act as a...", "acting as...", "your new role is..."
        role_pattern = re.compile(
            r"\b(you\s+are\s+now\s+(?:a|an|the)?|you\s+must\s+now\s+act\s+as\s+(?:a|an|the)?|act\s+as\s+(?:a|an|the)?|acting\s+as\s+(?:a|an|the)?|your\s+new\s+role\s+is\s+(?:a|an|the)?)\b",
            re.IGNORECASE
        )
        
        # 3. Defuse system-like instructions or bracketed developer blocks: e.g. [SYSTEM: ...] or [SYSTEM ...]
        bracket_system_pattern = re.compile(
            r"\[\s*(?:system|developer|instruction|user|assistant|prompt)\s*:.*?\]",
            re.IGNORECASE
        )
        
        # 4. Clean unbracketed "system: " or "system prompt: "
        colon_system_pattern = re.compile(
            r"\b(?:system|developer|instruction|system\s+prompt)\s*:\s*",
            re.IGNORECASE
        )

        sanitized = text
        sanitized = override_pattern.sub("[CLEANED DIRECTIVE]", sanitized)
        sanitized = role_pattern.sub("[CLEANED ROLE DIRECTIVE]", sanitized)
        sanitized = bracket_system_pattern.sub("[CLEANED DIRECTIVE]", sanitized)
        sanitized = colon_system_pattern.sub("[CLEANED DIRECTIVE]: ", sanitized)

        return sanitized

    def _sanitize_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results:
            return []
        sanitized = []
        for r in results:
            item = dict(r)
            if "title" in item and isinstance(item["title"], str):
                item["title"] = self.sanitize_text(item["title"])
            if "content" in item and isinstance(item["content"], str):
                item["content"] = self.sanitize_text(item["content"])
            sanitized.append(item)
        return sanitized

    # ────────── SearXNG ──────────
    async def _searxng_search(self, query: str, max_results: int = 10, categories: str = "general") -> List[Dict[str, Any]]:
        """Search via local SearXNG instance. Returns formatted results."""
        if not self._searxng_enabled:
            return []
        params = {
            "q": query,
            "format": "json",
            "categories": categories,
            "language": "auto",
            "pageno": 1,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._searxng_base_url}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self._searxng_timeout)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"SearXNG returned status {resp.status}")
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.error(f"SearXNG Search Error for '{query}': {e}")
            return []

        formatted = []
        for r in data.get("results", [])[:max_results]:
            url = r.get("url", "")
            if self._is_blocked_source(url):
                continue
            formatted.append({
                "title": r.get("title", ""),
                "url": url,
                "content": r.get("content", ""),
                "source": "SearXNG"
            })
        return formatted

    # ────────── DuckDuckGo (via ddgs v9+) ──────────
    async def _ddg_text(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search via ddgs package (v9+). Uses system proxy if configured."""
        loop = asyncio.get_event_loop()

        def _search():
            from ddgs import DDGS
            # Pass proxy explicitly — primp doesn't read env vars automatically
            proxy = self._http_proxy or None
            max_attempts = 1 if _IS_CHINA_SERVER else 3
            for attempt in range(max_attempts):
                try:
                    d = DDGS(proxy=proxy)
                    return d.text(query, max_results=max_results)
                except Exception as e:
                    if attempt < max_attempts - 1:
                        import time
                        time.sleep(1 * (attempt + 1))
                        continue
                    logger.warning(f"DDG search failed after {max_attempts} attempts: {e}")
                    return []
            return []

        try:
            ddg_results = await asyncio.wait_for(
                loop.run_in_executor(None, _search),
                timeout=self._ddg_timeout
            )
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
            logger.warning(f"DDG Search Error for '{query}': {e}")
            return []
        formatted = []
        for r in (ddg_results or []):
            url = r.get("href", "")
            if self._is_blocked_source(url):
                continue
            formatted.append({
                "title": r.get("title", ""),
                "url": url,
                "content": r.get("body", ""),
                "source": "DuckDuckGo"
            })
        return formatted

    # ────────── Public API ──────────
    async def quick_search(self, query: str) -> str:
        results = await self.search(query, max_results=3)
        if not results:
            return ""
        summaries = []
        for r in results:
            content = r['content'][:300] if len(r.get('content', '')) > 300 else r.get('content', '')
            summaries.append(f"Source: {r['source']}\nTitle: {r['title']}\nContent: {content}")
        return "\n\n".join(summaries)

    # ────────── Stock code detection ──────────
    _STOCK_CODE_RE = re.compile(r'\b\d{6}\b')
    _CHINESE_STOCK_KEYWORDS = re.compile(r'[沪深股涨停跌停板块煤炭白酒医药新能源]')

    def _is_chinese_stock_query(self, query: str) -> bool:
        """Detect if the query is about Chinese stocks (by stock code or keywords)."""
        if self._STOCK_CODE_RE.search(query):
            return True
        if self._CHINESE_STOCK_KEYWORDS.search(query):
            return True
        return False

    # ────────── Iwencai (同花顺问财) search — China-friendly, primary source ──────────
    async def _iwencai_search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search via 同花顺问财 (Iwencai) OpenAPI. Primary source for Chinese financial queries.
        Uses news + announcement + report channels combined."""
        try:
            from .data_providers.iwencai_news import search_comprehensive, search_news, search_announcements, search_reports
        except ImportError:
            return []

        iwencai_api_key = os.getenv("IWENCAI_API_KEY", "")
        if not iwencai_api_key:
            return []

        results = []
        try:
            data = await search_comprehensive(query)
            if data and data.get("status_code") == 0:
                items = data.get("data", [])
                for item in items[:max_results]:
                    title = item.get("title", item.get("headline", ""))
                    url = item.get("url", item.get("link", ""))
                    content = item.get("content", item.get("summary", "")) or title
                    source = item.get("source", item.get("channel", "同花顺问财"))
                    results.append({
                        "title": str(title)[:200],
                        "url": str(url) if url else "",
                        "content": str(content)[:500],
                        "source": f"Iwencai_{source}"
                    })
        except Exception as e:
            logger.warning(f"Iwencai search error: {e}")

        return results

    
        # Extract stock code from query
        stock_code = None
        match = self._STOCK_CODE_RE.search(query)
        if match:
            stock_code = match.group()

        results = []

        if stock_code:
            try:
                df = await asyncio.to_thread(ak.stock_news_em, symbol=stock_code)
                if df is not None and not df.empty:
                    for _, row in df.head(max_results).iterrows():
                        title = row.get("新闻标题", row.get("title", ""))
                        url = row.get("新闻链接", row.get("url", ""))
                        content = row.get("内容", row.get("content", "")) or title
                        results.append({
                            "title": str(title)[:200],
                            "url": str(url) if url else "",
                            "content": str(content)[:500],
                            "source": "EastMoney"
                        })
            except Exception as e:
                logger.warning(f"API news error for {stock_code}: {e}")

            if len(results) < max_results:
                try:
                    df2 = await asyncio.to_thread(ak.stock_individual_notice_report, stock_code)
                    if df2 is not None and not df2.empty:
                        for _, row in df2.head(max_results - len(results)).iterrows():
                            results.append({
                                "title": str(row.get("公告标题", row.get("title", "")))[:200],
                                "url": str(row.get("公告链接", row.get("url", ""))),
                                "content": str(row.get("内容", row.get("content", "公司公告")))[:500],
                                "source": "EastMoney_Announcement"
                            })
                except Exception as e:
                    logger.warning(f"API notice error for {stock_code}: {e}")



        return results

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search with fallback chain: DDG → 同花顺问财 → API → SearXNG.

        Priority:
        1. DDG (ddgs v9, via system proxy)
        2. 同花顺问财 (Iwencai, for Chinese stock/financial queries, requires IWENCAI_API_KEY)
        3. API (EastMoney, for Chinese stock queries)
        4. SearXNG (if enabled)
        """
        from .tools_config import is_skill_enabled

        if not query:
            return []

        # 1. DDG (primary default — via system proxy)
        if is_skill_enabled("ddg_fallback"):
            results = await self._ddg_text(query, max_results)
            if results:
                return self._sanitize_results(results)

        # 2. 同花顺问财 (primary source for Chinese financial data)
        if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
            results = await self._iwencai_search(query, max_results)
            if results:
                return self._sanitize_results(results)

            if results:
                return self._sanitize_results(results)

        # 4. SearXNG fallback (if enabled)
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(query, max_results)
            if results:
                return self._sanitize_results(results)

        return []

    async def search_news(self, query: str, max_results: int = 10, global_only: bool = False) -> List[Dict[str, Any]]:
        """Search news with fallback chain: DDG → 同花顺问财 → API → SearXNG."""
        from .tools_config import is_skill_enabled

        if not query:
            return []

        # 1. DDG (primary default)
        if is_skill_enabled("ddg_fallback"):
            results = await self._ddg_text(f"{query} latest news 2025", max_results)
            if results:
                return self._sanitize_results(results)

        if not global_only:
            # 2. 同花顺问财 (primary source for Chinese financial news)
            if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
                results = await self._iwencai_search(query, max_results)
                if results:
                    return self._sanitize_results(results)

        # 4. SearXNG fallback (or global primary if global_only=True)
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(f"{query} latest news 2025", max_results, categories="news")
            if results:
                return self._sanitize_results(results)

        return []


search_service = SearchService()
