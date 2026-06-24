from datetime import datetime
from typing import Dict
from .registry import tool_registry

# Try to import search service locally
from app.services.search_service import SearchService
search_service = SearchService()

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": "Search the internet for financial data, company info, filings, analyst reports, market data. Use when API data is N/A or you need latest information.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Search query. Be specific: include company name, ticker, metric, and time frame.",
            "required": True,
        }
    },
    "examples": [
        'tool: web_search\nreason: Need latest earnings guidance\nquery: NVIDIA Q1 2026 earnings guidance',
        'tool: web_search\nreason: Check current analyst consensus\nquery: NVO Novo Nordisk analyst price target consensus 2025',
    ],
}

@tool_registry.register(WEB_SEARCH_SCHEMA)
async def exec_web_search(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    results = await search_service.search(query, max_results=5)
    if not results:
        return "<tool_observation>\nNo results found for this query.\n</tool_observation>"
    
    lines = ["<tool_observation>"]
    lines.append(f"Web search results for: {query}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    for i, r in enumerate(results[:5], 1):
        title = r.get("title", "N/A")[:80]
        content = r.get("content", "")[:200]
        url = r.get("url", "")
        lines.append(f"{i}. {title}")
        if content:
            lines.append(f"   {content}")
        if url:
            lines.append(f"   {url}")
    lines.append("</tool_observation>")
    return "\n".join(lines)


NEWS_SEARCH_SCHEMA = {
    "name": "news_search",
    "description": "Search for recent financial news and articles. Primary source: 同花顺问财 (Iwencai) — covers Chinese official media, mainstream financial media, vertical industry sites, listed/non-listed company portals. Supplemented by international web news. Best for: breaking news, regulatory updates, policy changes, corporate announcements, industry trends.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "News search query. Include company name and topic. Supports Chinese keywords for A-share news.",
            "required": True,
        }
    },
    "examples": [
        'tool: news_search\nreason: Check for recent regulatory actions\nquery: Novo Nordisk FDA approval Ozempic 2025',
        'tool: news_search\nreason: Check A-share company latest news\nquery: 贵州茅台 最新动态',
        'tool: news_search\nreason: Check industry policy updates\nquery: 人工智能 芯片 产业政策',
    ],
}

@tool_registry.register(NEWS_SEARCH_SCHEMA)
async def exec_news_search(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    MAX_IWENCAI = 5
    MAX_SEARXNG = 3
    MAX_TITLE = 80
    MAX_CONTENT = 150

    lines = ["<tool_observation>"]
    lines.append(f"News: {query}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    # Try Iwencai first for financial news (Chinese market focus)
    iwencai_results = []
    try:
        from app.services.data_providers.iwencai_news import search_news as iwencai_search
        raw = await iwencai_search(query)
        if raw.get("status_code") == 0 and raw.get("data"):
            for item in raw["data"][:MAX_IWENCAI]:
                iwencai_results.append({
                    "title": item.get("title", "")[:MAX_TITLE],
                    "content": item.get("summary", "")[:MAX_CONTENT],
                    "date": item.get("publish_date", "")[:10],
                    "source": item.get("extra", {}).get("real_publish_source", "")[:20],
                })
    except Exception:
        pass

    # Format Iwencai results
    if iwencai_results:
        for i, r in enumerate(iwencai_results, 1):
            lines.append(f"{i}. [{r['date']}] {r['title']}")
            if r['content']:
                lines.append(f"   {r['content']}")

    # Supplement with SearXNG for broader/international coverage
    searxng_results = await search_service.search_news(query, max_results=MAX_SEARXNG)
    if searxng_results:
        start_idx = len(iwencai_results) + 1
        for i, r in enumerate(searxng_results, start_idx):
            title = r.get("title", "")[:MAX_TITLE]
            content = r.get("content", "")[:MAX_CONTENT]
            date = r.get("date", "")[:10]
            lines.append(f"{i}. [{date}] {title}")
            if content:
                lines.append(f"   {content}")

    if not iwencai_results and not searxng_results:
        return "<tool_observation>\nNo news results found.\n</tool_observation>"

    lines.append("</tool_observation>")
    return "\n".join(lines)


ANNOUNCEMENT_SEARCH_SCHEMA = {
    "name": "announcement_search",
    "description": "Search company announcements (公告) from A-share, HK-share, funds, ETFs. Source: 同花顺问财. Covers: periodic financial reports, dividends, buybacks, asset restructuring, equity changes, regulatory filings.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Announcement search query. Include company name or stock code and topic. Supports Chinese.",
            "required": True,
        }
    },
    "examples": [
        'tool: announcement_search\nreason: Check recent dividend announcements\nquery: 贵州茅台 分红',
        'tool: announcement_search\nreason: Check restructuring filings\nquery: 002532 资产重组公告',
    ],
}

@tool_registry.register(ANNOUNCEMENT_SEARCH_SCHEMA)
async def exec_announcement_search(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    MAX_ITEMS = 6
    MAX_TITLE = 80
    MAX_SUMMARY = 200

    lines = ["<tool_observation>"]
    lines.append(f"Announcements for: {query}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    # Try iwencai first
    iwencai_results = []
    try:
        from app.services.data_providers.iwencai_news import search_announcements
        raw = await search_announcements(query)
        if raw.get("error") == "quota_exhausted":
            # Quota exhausted — skip straight to web search fallback
            pass
        elif raw.get("data"):
            iwencai_results = raw["data"]
    except Exception:
        pass

    if iwencai_results:
        for i, item in enumerate(iwencai_results[:MAX_ITEMS], 1):
            title = item.get("title", "")[:MAX_TITLE]
            date = item.get("publish_date", "")[:10]
            summary = item.get("summary", "")[:MAX_SUMMARY]
            lines.append(f"{i}. [{date}] {title}")
            if summary:
                lines.append(f"   {summary}")
    else:
        # Fallback: web search
        from app.services.search_service import SearchService
        search_service = SearchService()
        try:
            results = await search_service.search(query, max_results=MAX_ITEMS)
            if results:
                for i, r in enumerate(results, 1):
                    title = r.get("title", "")[:MAX_TITLE]
                    content = r.get("content", "")[:MAX_SUMMARY]
                    source = r.get("source", "")[:20]
                    lines.append(f"{i}. {title} ({source})")
                    if content:
                        lines.append(f"   {content}")
            else:
                lines.append("No announcements found.")
        except Exception as e:
            lines.append(f"No announcements found. (fallback error: {e})")

    lines.append("</tool_observation>")
    return "\n".join(lines)


REPORT_SEARCH_SCHEMA = {
    "name": "report_search",
    "description": "Search analyst research reports (研报) from mainstream brokerages. Source: 同花顺问财. Returns professional analysis, investment ratings, target prices, and industry insights from sell-side analysts.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Research report search query. Include company name, ticker, or sector topic. Supports Chinese.",
            "required": True,
        }
    },
    "examples": [
        'tool: report_search\nreason: Check latest analyst ratings and target price\nquery: 贵州茅台 研报 目标价',
        'tool: report_search\nreason: Get industry research on AI semiconductors\nquery: 人工智能 芯片 行业研报',
    ],
}

@tool_registry.register(REPORT_SEARCH_SCHEMA)
async def exec_report_search(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    MAX_ITEMS = 5
    MAX_TITLE = 80
    MAX_SUMMARY = 250

    lines = ["<tool_observation>"]
    lines.append(f"Research Reports for: {query}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    # Try iwencai first
    iwencai_results = []
    try:
        from app.services.data_providers.iwencai_news import search_reports
        raw = await search_reports(query)
        if raw.get("error") == "quota_exhausted":
            pass  # skip to web search fallback
        elif raw.get("data"):
            iwencai_results = raw["data"]
    except Exception:
        pass

    if iwencai_results:
        for i, item in enumerate(iwencai_results[:MAX_ITEMS], 1):
            title = item.get("title", "")[:MAX_TITLE]
            date = item.get("publish_date", "")[:10]
            source = item.get("extra", {}).get("real_publish_source", "")[:20]
            summary = item.get("summary", "")[:MAX_SUMMARY]
            lines.append(f"{i}. [{date}] {title} (Source: {source})")
            if summary:
                lines.append(f"   {summary}")
    else:
        # Fallback: web search
        from app.services.search_service import SearchService
        search_service = SearchService()
        try:
            results = await search_service.search(query, max_results=MAX_ITEMS)
            if results:
                for i, r in enumerate(results, 1):
                    title = r.get("title", "")[:MAX_TITLE]
                    content = r.get("content", "")[:MAX_SUMMARY]
                    source = r.get("source", "")[:20]
                    lines.append(f"{i}. {title} ({source})")
                    if content:
                        lines.append(f"   {content}")
            else:
                lines.append("No research reports found.")
        except Exception as e:
            lines.append(f"No research reports found. (fallback error: {e})")

    lines.append("</tool_observation>")
    return "\n".join(lines)
