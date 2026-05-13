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
    {
        "name": "financial_data",
        "description": "Query structured financial data from authoritative APIs (AkShare/yfinance/OpenBB). Returns precise financial metrics for a given stock. Much more reliable than web_search for financial figures. Supports: quarterly earnings, income statement items, balance sheet items, cash flow, valuation metrics, dividend history, industry comparison. For US stocks also supports: analyst consensus/target price, SEC filings, insider trading, key financial ratios.",
        "parameters": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol/code. A-Share: 6-digit code (e.g. '002532'). US: ticker (e.g. 'AAPL'). HK: code with .HK suffix (e.g. '0700.HK').",
                "required": True,
            },
            "query": {
                "type": "string",
                "description": "What financial data you need. Examples: 'quarterly earnings last 4 quarters', 'balance sheet cash and debt', 'income statement breakdown', 'dividend history', 'peer comparison PE PB', 'cash flow statement', 'capex history', 'analyst consensus target price', 'SEC filings 10-Q', 'insider trading', 'key metrics valuation ratios'.",
                "required": True,
            },
        },
        "examples": [
            'tool: financial_data\nreason: Need quarterly earnings breakdown\nsymbol: 002532\nquery: quarterly earnings last 4 quarters revenue net profit',
            'tool: financial_data\nreason: Check cash flow details\nsymbol: AAPL\nquery: cash flow statement operating investing financing',
            'tool: financial_data\nreason: Need peer comparison data\nsymbol: 002532\nquery: industry peers PE PB ROE comparison',
            'tool: financial_data\nreason: Check analyst consensus and target price\nsymbol: MSFT\nquery: analyst consensus target price recommendation',
            'tool: financial_data\nreason: Check recent SEC filings\nsymbol: AAPL\nquery: SEC filings 10-Q latest',
            'tool: financial_data\nreason: Check insider trading activity\nsymbol: TSLA\nquery: insider trading recent transactions',
        ],
    },
    # ────── COMPUTATION TOOLS (deterministic, no LLM math needed) ──────
    {
        "name": "dcf_calculator",
        "description": "Perform a full Discounted Cash Flow valuation with sensitivity table. Returns intrinsic value per share. Use this instead of calculating DCF manually — this tool guarantees arithmetic accuracy. Provide FCF, growth rates, WACC, shares outstanding, and net debt.",
        "parameters": {
            "fcf_base": {"type": "number", "description": "Current year Free Cash Flow in millions", "required": True},
            "growth_rates": {"type": "array", "description": "List of 5 yearly FCF growth rates, e.g. [0.15, 0.12, 0.10, 0.08, 0.06]", "required": True},
            "terminal_growth": {"type": "number", "description": "Perpetual growth rate (must be < WACC), e.g. 0.03", "required": True},
            "wacc": {"type": "number", "description": "Weighted Average Cost of Capital, e.g. 0.09", "required": True},
            "shares_outstanding": {"type": "number", "description": "Shares outstanding in millions", "required": True},
            "net_debt": {"type": "number", "description": "Net debt in millions (debt - cash). Negative if net cash.", "required": True},
            "currency": {"type": "string", "description": "Currency (USD/CNY/HKD)", "required": False},
        },
        "examples": [
            'tool: dcf_calculator\nreason: Calculate intrinsic value via DCF\nfcf_base: 85000\ngrowth_rates: [0.15, 0.12, 0.10, 0.08, 0.06]\nterminal_growth: 0.03\nwacc: 0.09\nshares_outstanding: 7440\nnet_debt: -45000\ncurrency: USD',
        ],
    },
    {
        "name": "position_sizer",
        "description": "Calculate exact position size (number of shares) based on fixed-fractional risk management. Provides R-multiple targets, constraint checks (max position %, portfolio heat). Use this instead of manual calculation.",
        "parameters": {
            "account_size": {"type": "number", "description": "Total portfolio value in local currency", "required": True},
            "entry_price": {"type": "number", "description": "Planned entry price", "required": True},
            "stop_price": {"type": "number", "description": "Stop-loss price", "required": True},
            "risk_pct": {"type": "number", "description": "Risk per trade as percentage (default 1.0)", "required": False},
            "currency": {"type": "string", "description": "Currency (USD/CNY/HKD)", "required": False},
            "max_position_pct": {"type": "number", "description": "Max single position % (default 10)", "required": False},
            "current_heat": {"type": "number", "description": "Current portfolio heat % (default 0)", "required": False},
        },
        "examples": [
            'tool: position_sizer\nreason: Calculate position size for MSFT entry\naccount_size: 100000\nentry_price: 410\nstop_price: 385\nrisk_pct: 1.0\ncurrency: USD',
        ],
    },
    {
        "name": "kelly_calculator",
        "description": "Calculate Kelly Criterion optimal position size. Returns full Kelly and half-Kelly (recommended). Use this for precise position sizing based on edge and odds.",
        "parameters": {
            "win_rate": {"type": "number", "description": "Probability of winning (0-1), e.g. 0.55", "required": True},
            "avg_win": {"type": "number", "description": "Average win amount/ratio, e.g. 1.5", "required": True},
            "avg_loss": {"type": "number", "description": "Average loss amount/ratio, e.g. 1.0", "required": True},
            "fraction": {"type": "number", "description": "Kelly fraction (default 0.5 = half-Kelly)", "required": False},
        },
        "examples": [
            'tool: kelly_calculator\nreason: Determine optimal bet size\nwin_rate: 0.55\navg_win: 2.0\navg_loss: 1.0\nfraction: 0.5',
        ],
    },
    {
        "name": "beat_miss_scorer",
        "description": "Score earnings beat/miss quantitatively. Takes actual vs consensus for each metric and returns a composite score with verdict. Use after earnings data is available.",
        "parameters": {
            "metrics": {"type": "array", "description": "List of {name, consensus, actual, significance} objects", "required": True},
            "guidance_consensus": {"type": "number", "description": "Expected forward guidance value", "required": False},
            "guidance_actual": {"type": "number", "description": "Actual guidance given", "required": False},
        },
        "examples": [
            'tool: beat_miss_scorer\nreason: Score MSFT Q3 earnings beat/miss\nmetrics: [{"name": "Revenue", "consensus": 68.7, "actual": 70.1, "significance": "high"}, {"name": "EPS", "consensus": 3.18, "actual": 3.46, "significance": "high"}]\nguidance_consensus: 72.5\nguidance_actual: 74.0',
        ],
    },
    {
        "name": "comps_valuation",
        "description": "Derive fair value range from peer comparison multiples. Takes target metrics and 3-5 peer multiples, calculates premium/discount and implied price. Use this for systematic relative valuation.",
        "parameters": {
            "target": {"type": "object", "description": "Target company metrics: {symbol, pe, pb, ps, ev_ebitda, earnings, revenue, ebitda, shares_outstanding, current_price}", "required": True},
            "peers": {"type": "array", "description": "List of peer metrics: [{symbol, pe, pb, ps, ev_ebitda, revenue_growth, roe}]", "required": True},
        },
        "examples": [
            'tool: comps_valuation\nreason: Derive fair value from peer multiples\ntarget: {"symbol": "MSFT", "pe": 35, "pb": 12, "ps": 13, "ev_ebitda": 25, "earnings": 88000, "revenue": 245000, "ebitda": 120000, "shares_outstanding": 7440, "current_price": 410}\npeers: [{"symbol": "AAPL", "pe": 30, "pb": 45, "ps": 8, "ev_ebitda": 22}, {"symbol": "GOOGL", "pe": 22, "pb": 6, "ps": 6, "ev_ebitda": 16}]',
        ],
    },
    {
        "name": "pillar_scorer",
        "description": "Score investment thesis health based on 3-5 supporting pillars. Each pillar is rated on_track/mixed/broken with a weight. Returns composite health score and exit recommendation. Use this to systematically evaluate thesis validity.",
        "parameters": {
            "pillars": {"type": "array", "description": "List of {name, status, weight, evidence} objects. Status: on_track/mixed/broken", "required": True},
            "kill_switches": {"type": "array", "description": "List of pillar names where broken = automatic exit", "required": False},
        },
        "examples": [
            'tool: pillar_scorer\nreason: Evaluate thesis health\npillars: [{"name": "Revenue growth", "status": "on_track", "weight": 30, "evidence": "+22% YoY"}, {"name": "Margin expansion", "status": "mixed", "weight": 25, "evidence": "Flat QoQ"}]\nkill_switches: ["Revenue growth"]',
        ],
    },
    {
        "name": "dupont_decomposition",
        "description": "Decompose ROE into net margin × asset turnover × equity multiplier. Use this for precise DuPont analysis instead of manual calculation.",
        "parameters": {
            "net_income": {"type": "number", "description": "Net income", "required": True},
            "revenue": {"type": "number", "description": "Total revenue", "required": True},
            "total_assets": {"type": "number", "description": "Total assets", "required": True},
            "total_equity": {"type": "number", "description": "Total shareholders equity", "required": True},
        },
        "examples": [
            'tool: dupont_decomposition\nreason: Decompose ROE drivers\nparams: {"net_income": 72000, "revenue": 245000, "total_assets": 512000, "total_equity": 166000}',
        ],
    },
    {
        "name": "minervini_stage",
        "description": "Classify stock into Minervini Stage 1-4 based on price vs moving averages. Returns trend template checklist and action recommendation. Use this for systematic stage analysis.",
        "parameters": {
            "price": {"type": "number", "description": "Current stock price", "required": True},
            "ma50": {"type": "number", "description": "50-day moving average", "required": True},
            "ma150": {"type": "number", "description": "150-day moving average", "required": True},
            "ma200": {"type": "number", "description": "200-day moving average", "required": True},
            "ma200_prev": {"type": "number", "description": "MA200 from 1 month ago (for slope)", "required": False},
            "high_52w": {"type": "number", "description": "52-week high", "required": True},
            "low_52w": {"type": "number", "description": "52-week low", "required": True},
        },
        "examples": [
            'tool: minervini_stage\nreason: Classify MSFT trend stage\nparams: {"price": 410, "ma50": 395, "ma150": 380, "ma200": 370, "ma200_prev": 365, "high_52w": 430, "low_52w": 310}',
        ],
    },
    {
        "name": "earnings_quality_audit",
        "description": "Audit earnings quality using OCF/NI ratio, AR/Revenue ratio, and non-recurring items check. Returns quality score with alerts.",
        "parameters": {
            "operating_cashflow": {"type": "number", "description": "Operating cash flow", "required": True},
            "net_income": {"type": "number", "description": "Net income", "required": True},
            "accounts_receivable": {"type": "number", "description": "Accounts receivable", "required": True},
            "revenue": {"type": "number", "description": "Total revenue", "required": True},
            "non_recurring_items": {"type": "number", "description": "Non-recurring/one-off items", "required": False},
        },
        "examples": [
            'tool: earnings_quality_audit\nreason: Check earnings quality\nparams: {"operating_cashflow": 85000, "net_income": 72000, "accounts_receivable": 45000, "revenue": 245000, "non_recurring_items": 3000}',
        ],
    },
    {
        "name": "drawdown_scenario",
        "description": "Calculate portfolio impact under various market decline scenarios. Shows dollar loss per position and total portfolio drawdown.",
        "parameters": {
            "positions": {"type": "array", "description": "List of {symbol, weight_pct, beta}", "required": True},
            "scenarios": {"type": "array", "description": "Market decline percentages, e.g. [-10, -20, -30]", "required": False},
            "account_size": {"type": "number", "description": "Portfolio value", "required": False},
        },
        "examples": [
            'tool: drawdown_scenario\nreason: Stress test portfolio\nparams: {"positions": [{"symbol": "MSFT", "weight_pct": 25, "beta": 1.1}, {"symbol": "AAPL", "weight_pct": 20, "beta": 1.2}], "scenarios": [-10, -20, -30], "account_size": 100000}',
        ],
    },
    {
        "name": "risk_reward",
        "description": "Calculate risk/reward ratio, expected value, and breakeven win rate. Use for precise trade evaluation.",
        "parameters": {
            "entry": {"type": "number", "description": "Entry price", "required": True},
            "target": {"type": "number", "description": "Target/take-profit price", "required": True},
            "stop": {"type": "number", "description": "Stop-loss price", "required": True},
            "win_probability": {"type": "number", "description": "Estimated win probability (0-1)", "required": False},
        },
        "examples": [
            'tool: risk_reward\nreason: Evaluate MSFT trade setup\nparams: {"entry": 410, "target": 460, "stop": 385, "win_probability": 0.55}',
        ],
    },
    {
        "name": "stop_loss_validator",
        "description": "Validate stop-loss placement against volatility (ATR). Checks if stop is too tight (noise) or too wide (excessive loss).",
        "parameters": {
            "entry_price": {"type": "number", "description": "Entry price", "required": True},
            "stop_price": {"type": "number", "description": "Stop-loss price", "required": True},
            "atr": {"type": "number", "description": "14-day Average True Range", "required": True},
            "daily_volatility_pct": {"type": "number", "description": "Daily volatility in %", "required": False},
        },
        "examples": [
            'tool: stop_loss_validator\nreason: Check if stop is feasible\nparams: {"entry_price": 410, "stop_price": 385, "atr": 8.5, "daily_volatility_pct": 2.1}',
        ],
    },
    {
        "name": "cagr_calculator",
        "description": "Calculate Compound Annual Growth Rate. Also provides doubling time and year-by-year consistency check.",
        "parameters": {
            "start_value": {"type": "number", "description": "Starting value", "required": True},
            "end_value": {"type": "number", "description": "Ending value", "required": True},
            "years": {"type": "number", "description": "Number of years", "required": True},
            "intermediate_values": {"type": "array", "description": "Optional intermediate year values for consistency check", "required": False},
        },
        "examples": [
            'tool: cagr_calculator\nreason: Calculate 3-year revenue CAGR\nparams: {"start_value": 168000, "end_value": 245000, "years": 3}',
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
    lines.append("For financial_data (querying structured API data — much more reliable than web_search for financial figures):")
    lines.append("")
    lines.append("<tool_call>")
    lines.append("tool: financial_data")
    lines.append("reason: Need quarterly cash flow statement details")
    lines.append("symbol: 002532")
    lines.append("query: cash flow capex operating investing")
    lines.append("</tool_call>")
    lines.append("")
    lines.append("For computation tools (dcf_calculator, position_sizer, kelly_calculator, beat_miss_scorer, comps_valuation, pillar_scorer, dupont_decomposition, minervini_stage, earnings_quality_audit, drawdown_scenario, risk_reward, stop_loss_validator, cagr_calculator):")
    lines.append("These tools perform EXACT arithmetic — always use them instead of manual calculation.")
    lines.append("")
    lines.append("<tool_call>")
    lines.append("tool: dcf_calculator")
    lines.append("reason: Calculate intrinsic value for MSFT")
    lines.append("params: {\"fcf_base\": 85000, \"growth_rates\": [0.15, 0.12, 0.10, 0.08, 0.06], \"terminal_growth\": 0.03, \"wacc\": 0.09, \"shares_outstanding\": 7440, \"net_debt\": -45000, \"currency\": \"USD\"}")
    lines.append("</tool_call>")
    lines.append("")
    lines.append("<tool_call>")
    lines.append("tool: position_sizer")
    lines.append("reason: Calculate position size for entry")
    lines.append("params: {\"account_size\": 100000, \"entry_price\": 410, \"stop_price\": 385, \"risk_pct\": 1.0, \"currency\": \"USD\"}")
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

# Pattern for financial_data (has symbol: and query: fields)
FINANCIAL_DATA_PATTERN = re.compile(
    r'<tool_call>\s*tool:\s*(financial_data)\s*\n\s*reason:\s*(.*?)\s*\n\s*symbol:\s*(.*?)\s*\n\s*query:\s*(.*?)\s*\n?\s*</tool_call>',
    re.DOTALL | re.IGNORECASE
)

# Pattern for computation tools (have params: JSON field)
COMPUTATION_TOOL_NAMES = {"dcf_calculator", "position_sizer", "kelly_calculator", "beat_miss_scorer", "comps_valuation", "pillar_scorer", "dupont_decomposition", "minervini_stage", "earnings_quality_audit", "drawdown_scenario", "risk_reward", "stop_loss_validator", "cagr_calculator"}
COMPUTATION_PATTERN = re.compile(
    r'<tool_call>\s*tool:\s*(\w+)\s*\n\s*reason:\s*(.*?)\s*\n\s*params:\s*(.*?)\s*\n?\s*</tool_call>',
    re.DOTALL | re.IGNORECASE
)

def parse_tool_calls(text: str) -> List[Dict[str, str]]:
    """Parse <tool_call> blocks from LLM output."""
    calls = []
    parsed_spans = set()
    # First parse deep_scrape calls (they have url: field)
    for match in DEEP_SCRAPE_PATTERN.finditer(text):
        calls.append({
            "tool": match.group(1).strip(),
            "reason": match.group(2).strip(),
            "url": match.group(3).strip(),
            "query": match.group(4).strip(),
        })
        parsed_spans.add(match.span())
    # Parse computation tool calls (they have params: JSON field)
    for match in COMPUTATION_PATTERN.finditer(text):
        tool_name = match.group(1).strip()
        if tool_name in COMPUTATION_TOOL_NAMES and match.span() not in parsed_spans:
            calls.append({
                "tool": tool_name,
                "reason": match.group(2).strip(),
                "params_json": match.group(3).strip(),
            })
            parsed_spans.add(match.span())
    # Parse financial_data calls (they have symbol: and query: fields)
    for match in FINANCIAL_DATA_PATTERN.finditer(text):
        if match.span() not in parsed_spans:
            calls.append({
                "tool": match.group(1).strip(),
                "reason": match.group(2).strip(),
                "symbol": match.group(3).strip(),
                "query": match.group(4).strip(),
            })
            parsed_spans.add(match.span())
    # Then parse standard tool calls (skip already-parsed ones)
    for match in TOOL_CALL_PATTERN.finditer(text):
        if match.span() not in parsed_spans and match.group(1).strip() not in ("deep_scrape", "financial_data") and match.group(1).strip() not in COMPUTATION_TOOL_NAMES:
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

        # Computation tools (deterministic, no async needed)
        if tool_name in COMPUTATION_TOOL_NAMES:
            return self._exec_computation(tool_name, tool_call)

        if not query and tool_name != "financial_data":
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
            elif tool_name == "financial_data":
                symbol = tool_call.get("symbol", "")
                if not symbol:
                    return "<tool_observation>\nError: financial_data requires a 'symbol' parameter.\n</tool_observation>"
                return await self._exec_financial_data(symbol, query)
            else:
                return f"<tool_observation>\nError: Unknown tool '{tool_name}'. Available: web_search, news_search, knowledge_search, deep_scrape, financial_data, dcf_calculator, position_sizer, kelly_calculator, beat_miss_scorer, comps_valuation, pillar_scorer, dupont_decomposition, minervini_stage, earnings_quality_audit, drawdown_scenario, risk_reward, stop_loss_validator, cagr_calculator.\n</tool_observation>"
        except Exception as e:
            return f"<tool_observation>\nError executing {tool_name}: {str(e)}\n</tool_observation>"

    def _exec_computation(self, tool_name: str, tool_call: Dict[str, str]) -> str:
        """Execute a computation tool (synchronous, deterministic)."""
        import json
        from .computation_tools import execute_computation_tool
        
        params_json = tool_call.get("params_json", "{}")
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError as e:
            return f"<tool_observation>\nError: Invalid JSON in params for {tool_name}: {str(e)}\n</tool_observation>"
        
        result = execute_computation_tool(tool_name, params)
        if result is None:
            return f"<tool_observation>\nError: Computation tool '{tool_name}' not found.\n</tool_observation>"
        return result

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

    async def _exec_financial_data(self, symbol: str, query: str) -> str:
        """Fetch structured financial data from AkShare/yfinance based on the query."""
        import akshare as ak
        import yfinance as yf
        from ..utils.network import safe_ak_call
        from ..utils.data_validation import validate_ak_data

        query_lower = query.lower()
        lines = ["<tool_observation>"]
        lines.append(f"Financial data query for: {symbol}")
        lines.append(f"Query: {query}")
        lines.append(f"Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        is_a_share = symbol.isdigit() and len(symbol) == 6

        try:
            if is_a_share:
                # --- A-Share data from AkShare ---
                # Quarterly financial abstract (comprehensive)
                if any(kw in query_lower for kw in ["quarter", "earnings", "revenue", "profit", "净利润", "营收", "扣非", "季度", "eps", "roe", "margin"]):
                    try:
                        df = await safe_ak_call(ak.stock_financial_abstract_ths, symbol=symbol)
                        if validate_ak_data(df, min_rows=1):
                            lines.append("## 季度财务摘要 (同花顺)")
                            cols = ['报告期', '净利润', '净利润同比增长率', '扣非净利润', '扣非净利润同比增长率',
                                    '营业总收入', '营业总收入同比增长率', '基本每股收益', '销售毛利率',
                                    '销售净利率', '净资产收益率', '资产负债率', '每股经营现金流']
                            available_cols = [c for c in cols if c in df.columns]
                            for _, row in df.tail(6).iterrows():
                                vals = [f"{c}: {row.get(c, 'N/A')}" for c in available_cols]
                                lines.append("| " + " | ".join(vals) + " |")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ stock_financial_abstract_ths failed: {e}")

                # Balance sheet / cash / debt
                if any(kw in query_lower for kw in ["balance", "cash", "debt", "asset", "资产", "负债", "现金"]):
                    try:
                        yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                        ticker = yf.Ticker(yf_symbol)
                        bs = ticker.balance_sheet
                        if bs is not None and not bs.empty:
                            lines.append("## 资产负债表 (yfinance)")
                            key_items = ['Total Assets', 'Total Liabilities Net Minority Interest', 'Total Equity Gross Minority Interest',
                                         'Cash And Cash Equivalents', 'Total Debt', 'Current Assets', 'Current Liabilities',
                                         'Inventory', 'Net PPE']
                            for item in key_items:
                                if item in bs.index:
                                    row = bs.loc[item]
                                    vals = [f"{str(col)[:10]}: {v:,.0f}" for col, v in row.items() if v is not None and v == v]
                                    if vals:
                                        lines.append(f"- {item}: {' | '.join(vals[:4])}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ Balance sheet fetch failed: {e}")

                # Cash flow statement
                if any(kw in query_lower for kw in ["cash flow", "capex", "fcf", "现金流", "资本开支"]):
                    try:
                        yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                        ticker = yf.Ticker(yf_symbol)
                        cf = ticker.cashflow
                        if cf is not None and not cf.empty:
                            lines.append("## 现金流量表 (yfinance)")
                            key_items = ['Operating Cash Flow', 'Capital Expenditure', 'Free Cash Flow',
                                         'Investing Cash Flow', 'Financing Cash Flow']
                            for item in key_items:
                                if item in cf.index:
                                    row = cf.loc[item]
                                    vals = [f"{str(col)[:10]}: {v:,.0f}" for col, v in row.items() if v is not None and v == v]
                                    if vals:
                                        lines.append(f"- {item}: {' | '.join(vals[:4])}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ Cash flow fetch failed: {e}")

                # Income statement
                if any(kw in query_lower for kw in ["income", "利润表", "cost", "成本", "breakdown"]):
                    try:
                        yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                        ticker = yf.Ticker(yf_symbol)
                        fin = ticker.financials
                        if fin is not None and not fin.empty:
                            lines.append("## 利润表 (yfinance annual)")
                            key_items = ['Total Revenue', 'Cost Of Revenue', 'Gross Profit',
                                         'Operating Income', 'Net Income', 'EBITDA', 'Interest Expense',
                                         'Tax Provision', 'Research Development']
                            for item in key_items:
                                if item in fin.index:
                                    row = fin.loc[item]
                                    vals = [f"{str(col)[:10]}: {v:,.0f}" for col, v in row.items() if v is not None and v == v]
                                    if vals:
                                        lines.append(f"- {item}: {' | '.join(vals[:4])}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ Income statement fetch failed: {e}")

                # Dividend
                if any(kw in query_lower for kw in ["dividend", "分红", "派息", "股息"]):
                    try:
                        div_df = await safe_ak_call(ak.stock_history_dividend_detail, symbol=symbol)
                        if validate_ak_data(div_df, min_rows=1):
                            lines.append("## 分红历史 (AkShare)")
                            for _, row in div_df.head(5).iterrows():
                                lines.append(f"  {row.to_dict()}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ Dividend data failed: {e}")

                # Peer / industry comparison
                if any(kw in query_lower for kw in ["peer", "industry", "比较", "同业", "行业", "对标"]):
                    try:
                        from .search_service import search_service
                        search_res = await search_service.quick_search(f"{symbol} 行业对比 PE PB ROE 同业估值")
                        if search_res:
                            lines.append("## 行业对比 (搜索)")
                            lines.append(search_res[:2000])
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ Peer comparison search failed: {e}")

            else:
                # --- US/HK data from yfinance ---
                yf_symbol = symbol
                if symbol.endswith(".HK") or (symbol.isdigit() and len(symbol) <= 5):
                    clean = symbol.replace(".HK", "").zfill(4)
                    yf_symbol = f"{clean}.HK"

                ticker = yf.Ticker(yf_symbol)

                if any(kw in query_lower for kw in ["quarter", "earnings", "revenue", "profit", "eps"]):
                    qf = ticker.quarterly_financials
                    if qf is not None and not qf.empty:
                        lines.append("## Quarterly Financials (yfinance)")
                        for item in ['Total Revenue', 'Net Income', 'Gross Profit', 'Operating Income', 'EBITDA', 'Cost Of Revenue']:
                            if item in qf.index:
                                row = qf.loc[item]
                                vals = [f"{str(col)[:10]}: {v:,.0f}" for col, v in row.items() if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals[:5])}")
                        lines.append("")

                if any(kw in query_lower for kw in ["balance", "cash", "debt", "asset"]):
                    bs = ticker.balance_sheet
                    if bs is not None and not bs.empty:
                        lines.append("## Balance Sheet (yfinance)")
                        for item in ['Total Assets', 'Total Liabilities Net Minority Interest', 'Cash And Cash Equivalents',
                                     'Total Debt', 'Current Assets', 'Current Liabilities', 'Inventory']:
                            if item in bs.index:
                                row = bs.loc[item]
                                vals = [f"{str(col)[:10]}: {v:,.0f}" for col, v in row.items() if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals[:4])}")
                        lines.append("")

                if any(kw in query_lower for kw in ["cash flow", "capex", "fcf"]):
                    cf = ticker.cashflow
                    if cf is not None and not cf.empty:
                        lines.append("## Cash Flow Statement (yfinance)")
                        for item in ['Operating Cash Flow', 'Capital Expenditure', 'Free Cash Flow',
                                     'Investing Cash Flow', 'Financing Cash Flow']:
                            if item in cf.index:
                                row = cf.loc[item]
                                vals = [f"{str(col)[:10]}: {v:,.0f}" for col, v in row.items() if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals[:4])}")
                        lines.append("")

                if any(kw in query_lower for kw in ["income", "breakdown", "cost"]):
                    fin = ticker.financials
                    if fin is not None and not fin.empty:
                        lines.append("## Income Statement (yfinance annual)")
                        for item in ['Total Revenue', 'Cost Of Revenue', 'Gross Profit', 'Operating Income',
                                     'Net Income', 'EBITDA', 'Interest Expense', 'Research Development']:
                            if item in fin.index:
                                row = fin.loc[item]
                                vals = [f"{str(col)[:10]}: {v:,.0f}" for col, v in row.items() if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals[:4])}")
                        lines.append("")

                if any(kw in query_lower for kw in ["dividend"]):
                    divs = ticker.dividends
                    if divs is not None and len(divs) > 0:
                        lines.append("## Dividend History (yfinance)")
                        for date, val in list(divs.items())[-8:]:
                            lines.append(f"  {str(date)[:10]}: {val:.4f}")
                        lines.append("")

        except Exception as e:
            lines.append(f"⚠ Financial data query failed: {str(e)}")

        # --- OpenBB enrichment (US/HK stocks) ---
        if not is_a_share:
            try:
                from .openbb_service import openbb_service
                openbb_result = await openbb_service.query(symbol, query)
                if openbb_result:
                    lines.append(openbb_result)
            except Exception as e:
                lines.append(f"⚠ OpenBB enrichment failed: {e}")

        if len(lines) <= 4:
            lines.append("No matching financial data found for the query. Try a more specific query or different keywords.")

        lines.append("</tool_observation>")
        return "\n".join(lines)

    async def execute_all(self, tool_calls: List[Dict[str, str]]) -> List[str]:
        """Execute multiple tool calls (sequentially to respect rate limits)."""
        observations = []
        for tc in tool_calls:
            label = tc.get('url', tc.get('symbol', tc.get('query', '')))[:60]
            print(f"  [ToolExecutor] {tc['tool']}: {label}...")
            obs = await self.execute(tc)
            observations.append(obs)
            # Small delay between calls
            await asyncio.sleep(0.3)
        return observations


# Singleton
tool_executor = ToolExecutor()
