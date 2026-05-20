import os
import aiohttp
from ddgs import DDGS
from typing import List, Dict, Any
import asyncio


class SearchService:
    BLOCKED_SOURCE_DOMAINS = [
        "100ppi.com", "baidu.com", "baijiahao.baidu.com",
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

    def _is_blocked_source(self, url: str) -> bool:
        return any(d in url for d in self.BLOCKED_SOURCE_DOMAINS)

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

    async def _ddg_text(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        try:
            ddg_results = await asyncio.wait_for(
                loop.run_in_executor(None, _search),
                timeout=self._ddg_timeout
            )
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
            print(f"DDG Search Error for '{query}': {e}")
            return []
        formatted = []
        for r in ddg_results:
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
        """Search using SearXNG (primary) with DDG fallback. Respects tools_config.yaml."""
        from .tools_config import is_skill_enabled

        if not query:
            return []
        # Try SearXNG first (if enabled in config)
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(query, max_results)
            if results:
                return results
        # Fallback to DuckDuckGo (if enabled in config)
        if is_skill_enabled("ddg_fallback"):
            return await self._ddg_text(query, max_results)
        return []

    async def search_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search news using SearXNG news category with DDG fallback."""
        from .tools_config import is_skill_enabled

        if not query:
            return []
        # Try SearXNG news category first
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(f"{query} latest news 2025", max_results, categories="news")
            if results:
                return results
        # Fallback to DDG
        if is_skill_enabled("ddg_fallback"):
            return await self._ddg_text(f"{query} latest news 2025", max_results)
        return []


search_service = SearchService()
