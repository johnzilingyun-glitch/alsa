import os
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

    def _is_blocked_source(self, url: str) -> bool:
        return any(d in url for d in self.BLOCKED_SOURCE_DOMAINS)

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
        if not query:
            return []
        return await self._ddg_text(query, max_results)

    async def search_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        if not query:
            return []
        return await self._ddg_text(f"{query} latest news 2025", max_results)


search_service = SearchService()
