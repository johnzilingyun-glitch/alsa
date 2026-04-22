import os
import httpx
from ddgs import DDGS
from typing import List, Dict, Any
import asyncio
import time
from dotenv import load_dotenv

# Load env to get SEARXNG_URL
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
load_dotenv(os.path.join(root_dir, ".env"))

class SearchService:
    def __init__(self):
        self.max_results = 20
        self.searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")

    async def _searxng_search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Internal helper to call SearxNG instance.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                params = {
                    "q": query,
                    "format": "json",
                    "pageno": 1,
                    "language": "zh-CN,en-US"
                }
                response = await client.get(f"{self.searxng_url}/search", params=params)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    
                    formatted = []
                    for r in results[:max_results]:
                        formatted.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": r.get("content", ""),
                            "source": f"SearxNG ({r.get('engine', 'unknown')})"
                        })
                    return formatted
        except Exception as e:
            print(f"SearxNG Search Failed: {e}")
        return []

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Perform a general text search. Prioritizes SearxNG, falls back to DuckDuckGo.
        """
        # 1. Try SearxNG
        results = await self._searxng_search(query, max_results)
        if results:
            return results

        # 2. Fallback to DuckDuckGo
        print(f"Falling back to DuckDuckGo for query: {query}")
        loop = asyncio.get_event_loop()
        try:
            def _search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))
            
            ddg_results = await loop.run_in_executor(None, _search)
            
            formatted = []
            for r in ddg_results:
                formatted.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                    "source": "DuckDuckGo"
                })
            return formatted
        except Exception as e:
            print(f"DDGS Search Error: {e}")
            return []

    async def search_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Perform a news-specific search. Prioritizes SearxNG (news category), falls back to DDG.
        """
        # 1. Try SearxNG (news category)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                params = {
                    "q": query,
                    "format": "json",
                    "categories": "news",
                    "pageno": 1
                }
                response = await client.get(f"{self.searxng_url}/search", params=params)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        formatted = []
                        for r in results[:max_results]:
                            formatted.append({
                                "title": r.get("title", ""),
                                "url": r.get("url", ""),
                                "content": r.get("content", ""),
                                "date": r.get("pubdate", ""),
                                "source": f"SearxNG News ({r.get('engine', 'unknown')})"
                            })
                        return formatted
        except Exception as e:
            print(f"SearxNG News Search Failed: {e}")

        # 2. Fallback to DuckDuckGo
        loop = asyncio.get_event_loop()
        try:
            def _news():
                with DDGS() as ddgs:
                    return list(ddgs.news(query, max_results=max_results))
            
            results = await loop.run_in_executor(None, _news)
            
            formatted = []
            for r in results:
                formatted.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("body", ""),
                    "date": r.get("date", ""),
                    "source": f"{r.get('source', 'DuckDuckGo News')}"
                })
            return formatted
        except Exception as e:
            print(f"DDGS News Error: {e}")
            return []

# Singleton instance
search_service = SearchService()
