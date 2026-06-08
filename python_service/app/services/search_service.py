import os
import re
import aiohttp
from typing import List, Dict, Any
import asyncio


# Determine if we're on a China-based server (check network environment)
# China servers typically can't reach DuckDuckGo/Google reliably
_IS_CHINA_SERVER = os.getenv("AKSHARE_ENABLED", "").lower() in ("true", "1", "yes")


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
        # Google Custom Search configuration
        self._google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY", "")
        self._google_cx = os.getenv("GOOGLE_SEARCH_CX", "")
        self._google_timeout = 10

    def _is_blocked_source(self, url: str) -> bool:
        return any(d in url for d in self.BLOCKED_SOURCE_DOMAINS)

    # ────────── Google Custom Search ──────────
    async def _google_search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search via Google Custom Search JSON API. Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX."""
        api_key = self._google_api_key
        cx = self._google_cx
        if not api_key or not cx:
            return []
        
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(max_results, 10),  # Google max is 10 per request
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self._google_timeout)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        print(f"Google Search returned status {resp.status}: {text[:200]}")
                        return []
                    data = await resp.json()
        except Exception as e:
            print(f"Google Search Error for '{query}': {e}")
            return []

        formatted = []
        for item in data.get("items", [])[:max_results]:
            url = item.get("link", "")
            if self._is_blocked_source(url):
                continue
            formatted.append({
                "title": item.get("title", ""),
                "url": url,
                "content": item.get("snippet", ""),
                "source": "Google"
            })
        return formatted

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
                        print(f"SearXNG returned status {resp.status}")
                        return []
                    data = await resp.json()
        except Exception as e:
            print(f"SearXNG Search Error for '{query}': {e}")
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
        """Search via ddgs package (v9+). Fail fast — single attempt on China servers."""
        loop = asyncio.get_event_loop()

        def _search():
            from ddgs import DDGS
            # Single attempt on China servers (no retry — fail fast, unblock analysis)
            max_attempts = 1 if _IS_CHINA_SERVER else 3
            for attempt in range(max_attempts):
                try:
                    d = DDGS()
                    return d.text(query, max_results=max_results)
                except Exception as e:
                    if attempt < max_attempts - 1:
                        import time
                        time.sleep(1 * (attempt + 1))  # 1s, 2s backoff
                        continue
                    print(f"DDG search failed after {max_attempts} attempts: {e}")
                    return []
            return []

        try:
            ddg_results = await asyncio.wait_for(
                loop.run_in_executor(None, _search),
                timeout=self._ddg_timeout
            )
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
            print(f"DDG Search Error for '{query}': {e}")
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
            print(f"Iwencai search error: {e}")

        return results

    # ────────── AkShare-based news/search (China-friendly fallback) ──────────
    async def _akshare_search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search via AkShare's EastMoney news APIs. Fast and reliable from China servers.
        Falls back to cached local results if akshare is unavailable."""
        try:
            import akshare as ak
        except ImportError:
            return []

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
                print(f"AkShare news error for {stock_code}: {e}")

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
                    print(f"AkShare notice error for {stock_code}: {e}")

        if not results:
            # General news fallback via akshare CCTV news
            try:
                df3 = await asyncio.to_thread(ak.news_cctv)
                if df3 is not None and not df3.empty:
                    for _, row in df3.head(max_results).iterrows():
                        results.append({
                            "title": str(row.get("标题", row.get("title", "")))[:200],
                            "url": str(row.get("url", "")),
                            "content": str(row.get("内容", row.get("content", "")))[:500],
                            "source": "CCTV_News"
                        })
            except Exception as e:
                print(f"AkShare CCTV news error: {e}")

        return results

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search with fallback chain: DDG → 同花顺问财 → AkShare → Google → SearXNG.

        Priority:
        1. DDG (ddgs v9, fast fallback)
        2. 同花顺问财 (Iwencai, for Chinese stock/financial queries, requires IWENCAI_API_KEY)
        3. AkShare (EastMoney, for Chinese stock queries)
        4. Google Custom Search (if configured)
        5. SearXNG (if enabled)
        """
        from .tools_config import is_skill_enabled

        if not query:
            return []

        # 1. DDG (primary default — fails fast on timeout)
        if is_skill_enabled("ddg_fallback"):
            results = await self._ddg_text(query, max_results)
            if results:
                return results

        # 2. 同花顺问财 (primary source for Chinese financial data)
        if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
            results = await self._iwencai_search(query, max_results)
            if results:
                return results

        # 3. AkShare fallback (for Chinese stock/financial queries)
        if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
            results = await self._akshare_search(query, max_results)
            if results:
                return results

        # 4. Try Google Custom Search (if configured)
        if self._google_api_key and self._google_cx:
            results = await self._google_search(query, max_results)
            if results:
                return results

        # 5. SearXNG fallback (if enabled)
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(query, max_results)
            if results:
                return results

        return []

    async def search_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search news with fallback chain: DDG → 同花顺问财 → AkShare → Google → SearXNG."""
        from .tools_config import is_skill_enabled

        if not query:
            return []

        # 1. DDG (primary default)
        if is_skill_enabled("ddg_fallback"):
            results = await self._ddg_text(f"{query} latest news 2025", max_results)
            if results:
                return results

        # 2. 同花顺问财 (primary source for Chinese financial news)
        if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
            results = await self._iwencai_search(query, max_results)
            if results:
                return results

        # 3. AkShare fallback (for Chinese stock queries)
        if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
            results = await self._akshare_search(query, max_results)
            if results:
                return results

        # 4. Google (if configured)
        if self._google_api_key and self._google_cx:
            results = await self._google_search(f"{query} latest news 2025 2026", max_results)
            if results:
                return results

        # 5. SearXNG fallback
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(f"{query} latest news 2025", max_results, categories="news")
            if results:
                return results

        return []


search_service = SearchService()

