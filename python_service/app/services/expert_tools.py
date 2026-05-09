"""
Expert Tools — Tool definitions and executor for AI analyst tool-calling.

Provides tools that AI experts can invoke during analysis:
  - web_search: Search the internet for financial data, news, filings
  - news_search: Search specifically for recent news
  - knowledge_search: Search local brain/vector knowledge base

Tools follow a unified protocol:
  1. LLM outputs <tool_call> blocks
  2. Tool executor parses and runs them
  3. Results returned as <tool_observation> blocks
  4. LLM continues with real data
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, Callable, Awaitable
from datetime import datetime


# ────────────── TOOL DEFINITIONS ──────────────

TOOL_DEFINITIONS = [
    {
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
    },
    {
        "name": "news_search",
        "description": "Search for recent news articles about a company or topic. Prioritizes recency. Use for breaking news, regulatory updates, management changes.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "News search query. Include company name and topic.",
                "required": True,
            }
        },
        "examples": [
            'tool: news_search\nreason: Check for recent regulatory actions\nquery: Novo Nordisk FDA approval Ozempic 2025',
        ],
    },
    {
        "name": "knowledge_search",
        "description": "Search the local knowledge base (brain/vector DB) for historical analysis, prior research, and accumulated insights about a company or sector.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Knowledge query. Include ticker, topic, or analytical question.",
                "required": True,
            }
        },
        "examples": [
            'tool: knowledge_search\nreason: Check prior analysis history\nquery: NVO valuation concerns historical analysis',
        ],
    },
    {
        "name": "deep_scrape",
        "description": "Extract full page content from a URL using crawl4ai. Returns clean LLM-ready markdown. Use AFTER web_search/news_search finds a relevant URL that you need full details from (e.g. earnings report page, SEC filing, detailed article).",
        "parameters": {
            "url": {
                "type": "string",
                "description": "The URL to crawl and extract content from.",
                "required": True,
            },
            "query": {
                "type": "string",
                "description": "What information you're looking for on this page (used to focus extraction).",
                "required": True,
            }
        },
        "examples": [
            'tool: deep_scrape\nreason: Need full earnings details from this article\nurl: https://seekingalpha.com/article/nvo-earnings\nquery: NVO Q1 2025 revenue profit EPS guidance',
        ],
    },
]


def format_tool_descriptions(language: str = "zh-CN") -> str:
    """Format tool definitions for injection into system prompt."""
    is_zh = language == "zh-CN"
    lines = []
    lines.append("# AVAILABLE TOOLS" if not is_zh else "# 可用工具")
    lines.append("")
    
    for tool in TOOL_DEFINITIONS:
        lines.append(f"## {tool['name']}")
        lines.append(f"  Description: {tool['description']}")
        params = tool.get("parameters", {})
        if params:
            lines.append("  Parameters:")
            for pname, pinfo in params.items():
                req = " (required)" if pinfo.get("required") else ""
                lines.append(f"    - {pname}: {pinfo['type']}{req} — {pinfo['description']}")
        lines.append("")
    
    lines.append("# TOOL CALL FORMAT" if not is_zh else "# 工具调用格式")
    lines.append("")
    lines.append("When you need external information, output exactly:")
    lines.append("")
    lines.append("<tool_call>")
    lines.append("tool: web_search")
    lines.append("reason: Need latest earnings data")
    lines.append("query: NVIDIA Q4 2025 earnings results")
    lines.append("</tool_call>")
    lines.append("")
    lines.append("For deep_scrape (extracting full page from a URL found via web_search):")
    lines.append("")
    lines.append("<tool_call>")
    lines.append("tool: deep_scrape")
    lines.append("reason: Need full earnings details from this article")
    lines.append("url: https://example.com/article")
    lines.append("query: revenue profit EPS guidance")
    lines.append("</tool_call>")
    lines.append("")
    lines.append("After tool results are returned to you as <tool_observation>...</tool_observation>, continue your analysis using the real data.")
    lines.append("")
    lines.append("RULES:")
    lines.append("1. You may make multiple tool calls in one response (each in its own <tool_call> block).")
    lines.append("2. NEVER fabricate tool results. Wait for <tool_observation> responses.")
    lines.append("3. If a tool returns no useful data, state 'UNKNOWN — tool returned no results' with confidence LOW.")
    lines.append("4. Prefer knowledge_search before web_search for historical context.")
    lines.append("5. Use deep_scrape ONLY on URLs returned by web_search/news_search that need full content extraction.")
    lines.append("6. Always include 'reason:' explaining why you need this data.")
    lines.append("")
    
    return "\n".join(lines)


def get_openai_tools() -> list:
    """Convert TOOL_DEFINITIONS to OpenAI function calling format for DeepSeek native tool calling."""
    tools = []
    for tool_def in TOOL_DEFINITIONS:
        properties = {}
        required = []
        for param_name, param_info in tool_def.get("parameters", {}).items():
            properties[param_name] = {
                "type": param_info["type"],
                "description": param_info["description"]
            }
            if param_info.get("required"):
                required.append(param_name)

        tools.append({
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        })
    return tools


# ────────────── TOOL CALL PARSER ──────────────

# Pattern for standard tools (web_search, news_search, knowledge_search)
TOOL_CALL_PATTERN = re.compile(
    r'<tool_call>\s*tool:\s*(\w+)\s*\n\s*reason:\s*(.*?)\s*\n\s*query:\s*(.*?)\s*\n?\s*</tool_call>',
    re.DOTALL | re.IGNORECASE
)

# Pattern for deep_scrape (has url: field)
DEEP_SCRAPE_PATTERN = re.compile(
    r'<tool_call>\s*tool:\s*(deep_scrape)\s*\n\s*reason:\s*(.*?)\s*\n\s*url:\s*(.*?)\s*\n\s*query:\s*(.*?)\s*\n?\s*</tool_call>',
    re.DOTALL | re.IGNORECASE
)

def parse_tool_calls(text: str) -> List[Dict[str, str]]:
    """Parse <tool_call> blocks from LLM output."""
    calls = []
    # First parse deep_scrape calls (they have url: field)
    deep_matches = set()
    for match in DEEP_SCRAPE_PATTERN.finditer(text):
        calls.append({
            "tool": match.group(1).strip(),
            "reason": match.group(2).strip(),
            "url": match.group(3).strip(),
            "query": match.group(4).strip(),
        })
        deep_matches.add(match.span())
    # Then parse standard tool calls (skip deep_scrape ones)
    for match in TOOL_CALL_PATTERN.finditer(text):
        if match.span() not in deep_matches and match.group(1).strip() != "deep_scrape":
            calls.append({
                "tool": match.group(1).strip(),
                "reason": match.group(2).strip(),
                "query": match.group(3).strip(),
            })
    return calls


def has_tool_calls(text: str) -> bool:
    """Quick check if text contains tool calls."""
    return "<tool_call>" in text


# ────────────── TOOL EXECUTOR ──────────────

class ToolExecutor:
    """
    Executes tool calls by dispatching to the appropriate service.
    
    Requires lazy imports to avoid circular dependencies.
    """

    def __init__(self):
        self._search_service = None
        self._brain_manager = None

    @property
    def search_service(self):
        if self._search_service is None:
            from .search_service import search_service
            self._search_service = search_service
        return self._search_service

    @property
    def brain_manager(self):
        if self._brain_manager is None:
            from .brain_manager import brain_manager
            self._brain_manager = brain_manager
        return self._brain_manager

    async def execute(self, tool_call: Dict[str, str]) -> str:
        """Execute a single tool call and return formatted observation."""
        tool_name = tool_call.get("tool", "")
        query = tool_call.get("query", "")
        reason = tool_call.get("reason", "")

        if not query:
            return f"<tool_observation>\nError: Empty query for tool '{tool_name}'.\n</tool_observation>"

        try:
            if tool_name == "web_search":
                return await self._exec_web_search(query)
            elif tool_name == "news_search":
                return await self._exec_news_search(query)
            elif tool_name == "knowledge_search":
                return await self._exec_knowledge_search(query)
            elif tool_name == "deep_scrape":
                url = tool_call.get("url", "")
                if not url:
                    return "<tool_observation>\nError: deep_scrape requires a 'url' parameter.\n</tool_observation>"
                return await self._exec_deep_scrape(url, query)
            else:
                return f"<tool_observation>\nError: Unknown tool '{tool_name}'. Available: web_search, news_search, knowledge_search, deep_scrape.\n</tool_observation>"
        except Exception as e:
            return f"<tool_observation>\nError executing {tool_name}: {str(e)}\n</tool_observation>"

    async def _exec_web_search(self, query: str) -> str:
        results = await self.search_service.search(query, max_results=5)
        if not results:
            return "<tool_observation>\nNo results found for this query.\n</tool_observation>"
        
        lines = [f"<tool_observation>"]
        lines.append(f"Web search results for: {query}")
        lines.append(f"Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        for i, r in enumerate(results, 1):
            title = r.get("title", "N/A")
            content = r.get("content", "")[:400]
            source = r.get("source", "web")
            url = r.get("url", "")
            lines.append(f"{i}. [{title}]")
            lines.append(f"   {content}")
            lines.append(f"   Source: {source} | {url}")
            lines.append("")
        lines.append("</tool_observation>")
        return "\n".join(lines)

    async def _exec_news_search(self, query: str) -> str:
        results = await self.search_service.search_news(query, max_results=5)
        if not results:
            return "<tool_observation>\nNo news results found for this query.\n</tool_observation>"
        
        lines = ["<tool_observation>"]
        lines.append(f"News search results for: {query}")
        lines.append(f"Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        for i, r in enumerate(results, 1):
            title = r.get("title", "N/A")
            content = r.get("content", "")[:400]
            source = r.get("source", "news")
            date = r.get("date", "")
            url = r.get("url", "")
            lines.append(f"{i}. [{title}] ({date})")
            lines.append(f"   {content}")
            lines.append(f"   Source: {source} | {url}")
            lines.append("")
        lines.append("</tool_observation>")
        return "\n".join(lines)

    async def _exec_knowledge_search(self, query: str) -> str:
        try:
            ctx = self.brain_manager.get_brain_context("default", query=query)
            facts = ctx.get("facts", [])
            instructions = ctx.get("instructions", "")
            
            if not facts and not instructions:
                return "<tool_observation>\nNo relevant knowledge found in local database.\n</tool_observation>"
            
            lines = ["<tool_observation>"]
            lines.append(f"Knowledge base results for: {query}")
            lines.append("")
            if instructions:
                lines.append(f"Guidelines: {instructions[:500]}")
                lines.append("")
            if facts:
                for i, fact in enumerate(facts[:10], 1):
                    lines.append(f"{i}. {fact[:300]}")
                lines.append("")
            lines.append("</tool_observation>")
            return "\n".join(lines)
        except Exception as e:
            return f"<tool_observation>\nKnowledge search error: {str(e)}\n</tool_observation>"

    async def _exec_deep_scrape(self, url: str, query: str) -> str:
        """Use crawl4ai to extract full page content as LLM-ready markdown.
        
        Anti-bot optimized:
        - Stealth mode (playwright-stealth) to avoid fingerprinting
        - Random user agent rotation
        - Text-only mode (no images/CSS) for speed
        - Ad/tracker blocking
        - Realistic viewport and timing
        """
        # Block domains with server-side bot detection — auto-fallback to web_search
        from urllib.parse import urlparse
        BLOCKED_DOMAINS = ["finance.yahoo.com", "yahoo.com", "login.yahoo.com", "100ppi.com", "www.100ppi.com"]
        parsed_url = urlparse(url)
        if any(domain in parsed_url.netloc for domain in BLOCKED_DOMAINS):
            fallback = await self._exec_web_search(query)
            inner = fallback.replace("<tool_observation>", "").replace("</tool_observation>", "").strip()
            return (
                "<tool_observation>\n"
                f"⚠ deep_scrape skipped: {parsed_url.netloc} uses server-side bot detection that blocks all headless browsers.\n"
                f"Auto-fallback: searched for '{query}' via web_search instead.\n\n"
                f"{inner}\n"
                "</tool_observation>"
            )

        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig

            browser_config = BrowserConfig(
                headless=True,
                text_mode=True,        # Skip loading images — text only
                light_mode=True,       # Reduced background features
                enable_stealth=True,   # playwright-stealth for anti-bot bypass
                user_agent_mode="random",  # Randomize user agent per crawl
                avoid_ads=True,        # Block ad/tracker domains
                avoid_css=True,        # Skip CSS loading (we only need content)
                viewport_width=1920,
                viewport_height=1080,
                verbose=False,
            )

            run_config = CrawlerRunConfig(
                word_count_threshold=30,
                exclude_external_links=True,
                process_iframes=False,
                wait_until="domcontentloaded",  # Faster than networkidle
                page_timeout=30000,            # 30s timeout
                delay_before_return_html=1.0,  # Wait 1s for JS rendering
                scan_full_page=False,          # Don't scroll (speed)
                verbose=False,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)

            if not result or not result.success:
                error_msg = getattr(result, 'error_message', 'Unknown error') if result else 'Crawler returned None'
                return f"<tool_observation>\ndeep_scrape failed for {url}: {error_msg}\n</tool_observation>"

            # Prefer fit_markdown (cleaned, main content only) over raw markdown
            content = getattr(result, 'fit_markdown', '') or getattr(result, 'markdown', '') or ''
            if not content:
                return f"<tool_observation>\ndeep_scrape returned empty content for {url}.\n</tool_observation>"

            # Truncate to ~6000 chars to balance depth vs prompt size
            if len(content) > 6000:
                content = content[:6000] + "\n\n... [content truncated at 6000 chars]"

            lines = ["<tool_observation>"]
            lines.append(f"Deep scrape of: {url}")
            lines.append(f"Query focus: {query}")
            lines.append(f"Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"Content length: {len(content)} chars")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("</tool_observation>")
            return "\n".join(lines)
        except ImportError:
            return "<tool_observation>\ndeep_scrape unavailable: crawl4ai not installed. Use `pip install crawl4ai` and `crawl4ai-setup`.\n</tool_observation>"
        except Exception as e:
            return f"<tool_observation>\ndeep_scrape error for {url}: {str(e)}\n</tool_observation>"

    async def execute_all(self, tool_calls: List[Dict[str, str]]) -> List[str]:
        """Execute multiple tool calls (sequentially to respect rate limits)."""
        observations = []
        for tc in tool_calls:
            label = tc.get('url', tc.get('query', ''))[:60]
            print(f"  [ToolExecutor] {tc['tool']}: {label}...")
            obs = await self.execute(tc)
            observations.append(obs)
            # Small delay between calls
            await asyncio.sleep(0.3)
        return observations


# Singleton
tool_executor = ToolExecutor()
