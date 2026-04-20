from ddgs import DDGS
from typing import List, Dict, Any
import asyncio
import time

class SearchService:
    def __init__(self):
        self.max_results = 20

    async def search(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Perform a general text search using DuckDuckGo (ddgs).
        """
        loop = asyncio.get_event_loop()
        try:
            # ddgs is synchronous, run in executor
            def _search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))
            
            results = await loop.run_in_executor(None, _search)
            
            # Format to a standard format used by the frontend
            formatted = []
            for r in results:
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

    async def search_news(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Perform a news-specific search using DuckDuckGo (ddgs).
        """
        loop = asyncio.get_event_loop()
        try:
            def _news():
                with DDGS() as ddgs:
                    # news() returns results with 'date', 'title', 'body', 'url', 'source'
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
