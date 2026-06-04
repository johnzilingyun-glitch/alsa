import os
import aiohttp
from typing import List, Dict, Any
import asyncio


class SearchService:
    BLOCKED_SOURCE_DOMAINS = [
        "baidu.com", "baijiahao.baidu.com",
        "zhidao.baidu.com", "tieba.baidu.com", "wenku.baidu.com",
        "sogou.com", "360.cn", "so.com", "toutiao.com", "163.com",
    ]

    def __init__(self):
        self.max_results = 20
        self._ddg_timeout = 12
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
        """Search via ddgs package (v9+). Much more reliable than old duckduckgo_search.
        Uses retry with exponential backoff on transient failures."""
        loop = asyncio.get_event_loop()

        def _search():
            from ddgs import DDGS
            max_attempts = 3
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

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search with fallback chain: Google → DDG → SearXNG.
        
        Priority:
        1. Google Custom Search (if configured)
        2. DDG (ddgs v9, reliable default)
        3. SearXNG (if enabled, typically Linux only)
        """
        from .tools_config import is_skill_enabled

        if not query:
            return []

        # 1. Try Google Custom Search first (if configured)
        if self._google_api_key and self._google_cx:
            results = await self._google_search(query, max_results)
            if results:
                return results

        # 2. DDG (primary default — ddgs v9 is stable)
        if is_skill_enabled("ddg_fallback"):
            results = await self._ddg_text(query, max_results)
            if results:
                return results

        # 3. SearXNG fallback (if enabled)
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(query, max_results)
            if results:
                return results

        return []

    async def search_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search news with fallback chain: Google → DDG → SearXNG."""
        from .tools_config import is_skill_enabled

        if not query:
            return []

        # 1. Google (if configured)
        if self._google_api_key and self._google_cx:
            results = await self._google_search(f"{query} latest news 2025 2026", max_results)
            if results:
                return results

        # 2. DDG (primary default)
        if is_skill_enabled("ddg_fallback"):
            results = await self._ddg_text(f"{query} latest news 2025", max_results)
            if results:
                return results

        # 3. SearXNG fallback
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(f"{query} latest news 2025", max_results, categories="news")
            if results:
                return results

        return []


search_service = SearchService()

