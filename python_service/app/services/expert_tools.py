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
    },
    {
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
    },
    {
        "name": "macro_query",
        "description": "Query macroeconomic indicators (GDP, CPI, PPI, interest rates, exchange rates, social financing, M2, PMI, industrial output, consumption, investment, imports/exports). Source: 同花顺问财 (Iwencai). Supports natural language queries in Chinese. Returns structured data with indicator values, time periods, and units.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Macro data query in natural language. Supports Chinese. Examples: '中国最新GDP增速', 'CPI同比', '美联储利率', 'M2货币供应量', '社融规模'.",
                "required": True,
            }
        },
        "examples": [
            'tool: macro_query\nreason: Get latest GDP growth rate\nquery: 中国最新GDP同比增速',
            'tool: macro_query\nreason: Check CPI inflation trend\nquery: 中国CPI同比最近6个月',
            'tool: macro_query\nreason: Get M2 money supply data\nquery: M2货币供应量同比',
            'tool: macro_query\nreason: Check PMI manufacturing index\nquery: 中国制造业PMI最新',
            'tool: macro_query\nreason: Get social financing data\nquery: 社会融资规模增量',
        ],
    },
    {
        "name": "business_query",
        "description": "Query company business/operations data: revenue breakdown by product/region, major customers, suppliers, subsidiaries, equity investments, major contracts. Source: 同花顺问财 (Iwencai). Supports natural language queries in Chinese. Use for understanding a company's business structure and operations.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Business data query. Include company name or stock code. Examples: '贵州茅台主营业务构成', '002532主要客户', '宁德时代供应商', '比亚迪参控股公司'.",
                "required": True,
            }
        },
        "examples": [
            'tool: business_query\nreason: Understand revenue breakdown by product\nquery: 贵州茅台 主营业务构成 产品收入占比',
            'tool: business_query\nreason: Check major customers concentration\nquery: 002532 主要客户 销售占比',
            'tool: business_query\nreason: Check subsidiary investments\nquery: 宁德时代 参控股公司',
        ],
    },
    {
        "name": "finance_query",
        "description": "Query company financial indicators: revenue, net profit, ROE, debt ratio, cash flow, gross margin, net margin, EPS, valuation metrics (PE/PB/PS). Source: 同花顺问财 (Iwencai). Supports natural language queries. Use for cross-market financial screening and comparison.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Financial data query. Include company name/code and metrics. Examples: '贵州茅台 ROE 净利润 营收', '沪深300成分股 市盈率低于15', '002532 毛利率 净利率 近3年'.",
                "required": True,
            }
        },
        "examples": [
            'tool: finance_query\nreason: Get key financial metrics\nquery: 贵州茅台 营业收入 净利润 ROE 近4个季度',
            'tool: finance_query\nreason: Screen stocks by financial criteria\nquery: 创业板 ROE大于20% 营收增速大于30%',
            'tool: finance_query\nreason: Check debt and cash flow health\nquery: 002532 资产负债率 经营性现金流 近3年',
        ],
    },
    {
        "name": "management_query",
        "description": "Query company shareholder/management data: share capital structure, top 10 shareholders, shareholder count changes, controlling shareholder, equity pledges, institutional holdings, executive team. Source: 同花顺问财 (Iwencai). Use for ownership analysis and governance assessment.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Shareholder/management query. Include company name or code. Examples: '贵州茅台 前十大股东', '002532 股东户数变化', '宁德时代 实控人'.",
                "required": True,
            }
        },
        "examples": [
            'tool: management_query\nreason: Check shareholder concentration\nquery: 002532 股东户数 户均持股 最近变化',
            'tool: management_query\nreason: Identify controlling shareholder\nquery: 贵州茅台 实控人 控股比例',
            'tool: management_query\nreason: Check institutional holdings\nquery: 宁德时代 前十大流通股东 机构持仓',
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
        "description": "Perform a full Discounted Cash Flow valuation with sensitivity table. Returns intrinsic value per share. To avoid WACC black-box audits, you MUST provide rf, beta, erp, and kd to calculate WACC dynamically. Provide FCF, growth rates, shares outstanding, and net debt.",
        "parameters": {
            "fcf_base": {"type": "number", "description": "Current year Free Cash Flow in millions", "required": True},
            "growth_rates": {"type": "array", "description": "List of 5 yearly FCF growth rates, e.g. [0.15, 0.12, 0.10, 0.08, 0.06]", "required": True},
            "terminal_growth": {"type": "number", "description": "Perpetual growth rate (must be < WACC), e.g. 0.03", "required": True},
            "wacc": {"type": "number", "description": "Weighted Average Cost of Capital (e.g. 0.09). Only use if rf/beta/erp are missing.", "required": False},
            "rf": {"type": "number", "description": "Risk-free rate (e.g. 0.04)", "required": False},
            "beta": {"type": "number", "description": "Beta coefficient (e.g. 1.2)", "required": False},
            "erp": {"type": "number", "description": "Equity Risk Premium (e.g. 0.05)", "required": False},
            "kd": {"type": "number", "description": "Cost of debt (e.g. 0.05)", "required": False},
            "debt_weight": {"type": "number", "description": "Debt to capital ratio (e.g. 0.3)", "required": False},
            "tax_rate": {"type": "number", "description": "Corporate tax rate (e.g. 0.25)", "required": False},
            "shares_outstanding": {"type": "number", "description": "Shares outstanding in millions", "required": True},
            "net_debt": {"type": "number", "description": "Net debt in millions (debt - cash). Negative if net cash.", "required": True},
            "currency": {"type": "string", "description": "Currency (USD/CNY/HKD)", "required": False},
        },
        "examples": [
            'tool: dcf_calculator\nreason: Calculate intrinsic value via DCF\nparams: {"fcf_base": 85000, "growth_rates": [0.15, 0.12, 0.10, 0.08, 0.06], "terminal_growth": 0.03, "rf": 0.04, "beta": 1.2, "erp": 0.05, "kd": 0.05, "shares_outstanding": 7440, "net_debt": -45000, "currency": "USD"}'
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
        "description": "Derive fair value range from peer comparison multiples. Takes target metrics and 3-5 peer multiples, calculates premium/discount and implied price. Use this for systematic relative valuation. WARNING: DO NOT hallucinate peer data. If you don't know the exact PE/PB of peers, you MUST use the financial_data tool to fetch peer metrics first before calling this tool.",
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
    {
        "name": "commodity_price_query",
        "description": "Query spot/market prices, historical trends, and weekly report quotes for commodities, materials, resources, and chemical products (e.g. 氯化钾, 尿素, 碳酸锂, 聚乙烯, 铁矿石). Source: 同花顺问财 (Iwencai) comprehensive search. Returns recent industry reports and market quotes.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Commodity search query in natural language. e.g. '国产60%氯化钾价格', '尿素市场报价'.",
                "required": True,
            }
        },
        "examples": [
            'tool: commodity_price_query\nreason: Check current spot price of potassium chloride\nquery:国产60%氯化钾 价格',
            'tool: commodity_price_query\nreason: Get latest market quotation for urea\nquery: 尿素 最新市场报价',
        ],
    },
    {
        "name": "futures_query",
        "description": "Query futures and commodity spot prices, basis, contract details, and indexes (e.g. 螺纹钢现货价, 黄金期货价格, 铜库存). Source: 同花顺问财 (Iwencai). Supports natural language queries in Chinese. Returns structured data with indicator values, time, and units.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Futures/commodity query in natural language. e.g. '螺纹钢现货价最新', '甲醇期货结算价'.",
                "required": True,
            }
        },
        "examples": [
            'tool: futures_query\nreason: Check current spot price of steel rebar\nquery: 螺纹钢现货价格',
        ],
    },
    {
        "name": "valuation_query",
        "description": "Query precise stock valuation metrics including PE (ttm/static/dynamic), PB, PS, dividend yield, and market cap. Source: 同花顺问财 (Iwencai). Supports natural language queries. Use for checking real-time valuation multiples.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Stock valuation query in natural language. e.g. '贵州茅台市盈率市净率', '腾讯控股最新股息率'.",
                "required": True,
            }
        },
        "examples": [
            'tool: valuation_query\nreason: Check current valuation multiples for Moutai\nquery: 贵州茅台 市盈率 市净率',
        ],
    },
    {
        "name": "industry_query",
        "description": "Query industry concepts, sector thematic indices, and concept stock inclusion reasons. Source: 同花顺问财 (Iwencai). Use for understanding stock concept associations.",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Industry or concept stock query. e.g. '低空经济概念股有哪些', '优刻得纳入低空经济概念原因'.",
                "required": True,
            }
        },
        "examples": [
            'tool: industry_query\nreason: Identify concept stocks and reasons\nquery: 低空经济 概念股及纳入原因',
        ],
    },
    {
        "name": "policy_query",
        "description": "Query policy support details, national/regional strategic directives, and policy-driven concept stock lists. Source: 同花顺问财 (Iwencai).",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Policy query in natural language. e.g. '低空经济政策支持利好个股'.",
                "required": True,
            }
        },
        "examples": [
            'tool: policy_query\nreason: Find policy-driven concept stocks\nquery: 半导体产业政策利好股票',
        ],
    },
]


ROLE_TOOLS_MAP = {
    "Deep Research Specialist": ["web_search", "news_search", "deep_scrape", "knowledge_search", "report_search", "announcement_search"],
    "Technical Analyst": ["minervini_stage", "stop_loss_validator", "position_sizer", "risk_reward", "futures_query", "commodity_price_query", "financial_data", "web_search", "news_search", "announcement_search"],
    "Fundamental Analyst": ["financial_data", "dcf_calculator", "dupont_decomposition", "comps_valuation", "earnings_quality_audit", "cagr_calculator", "macro_query", "business_query", "finance_query", "management_query", "valuation_query", "web_search", "news_search", "announcement_search"],
    "Serenity Alpha Analyst": ["minervini_stage", "position_sizer", "financial_data", "beat_miss_scorer", "comps_valuation", "cagr_calculator", "web_search", "news_search", "announcement_search"],
    "Chief Audit Officer": ["pillar_scorer", "earnings_quality_audit", "web_search", "news_search", "announcement_search", "financial_data"],
    "Risk Manager": ["drawdown_scenario", "position_sizer", "kelly_calculator", "web_search", "news_search", "announcement_search", "financial_data"],
    "Sentiment Analyst": ["news_search", "web_search", "industry_query", "policy_query", "announcement_search"],
    "Bull Researcher": ["pillar_scorer", "web_search", "news_search", "announcement_search", "financial_data"],
    "Bear Researcher": ["pillar_scorer", "web_search", "news_search", "announcement_search", "financial_data"],
    "Professional Reviewer": ["pillar_scorer", "web_search", "news_search", "announcement_search", "financial_data"],
    "Chief Strategist": ["position_sizer", "drawdown_scenario", "kelly_calculator", "web_search", "news_search", "announcement_search", "financial_data"]
}

def format_tool_descriptions(role: str = None, language: str = "zh-CN") -> str:
    """Format tool definitions for injection into system prompt. Respects tools_config.yaml."""
    from .tools_config import is_tool_enabled

    is_zh = language == "zh-CN"
    lines = []
    lines.append("# AVAILABLE TOOLS" if not is_zh else "# 可用工具")
    lines.append("")
    
    allowed_tools = ROLE_TOOLS_MAP.get(role) if role else None
    
    for tool in TOOL_DEFINITIONS:
        if not is_tool_enabled(tool['name']):
            continue
        # Removed allowed_tools filtering to allow LLM to use any tool when data is missing
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
    lines.append("params: {\"fcf_base\": 85000, \"growth_rates\": [0.15, 0.12, 0.10, 0.08, 0.06], \"terminal_growth\": 0.03, \"rf\": 0.04, \"beta\": 1.1, \"erp\": 0.05, \"kd\": 0.045, \"debt_weight\": 0.1, \"tax_rate\": 0.21, \"shares_outstanding\": 7440, \"net_debt\": -45000, \"currency\": \"USD\"}")
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


def get_openai_tools(role: str = None) -> list:
    """Convert TOOL_DEFINITIONS to OpenAI function calling format for DeepSeek native tool calling."""
    # Detailed items schema for array params so the model generates correct structured JSON
    ARRAY_ITEMS_SCHEMA = {
        "growth_rates": {"type": "number"},
        "intermediate_values": {"type": "number"},
        "scenarios": {"type": "number"},
        "kill_switches": {"type": "string"},
        "metrics": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Metric name (e.g. Revenue, EPS)"},
                "consensus": {"type": "number", "description": "Market consensus estimate"},
                "actual": {"type": "number", "description": "Actual reported value"},
                "significance": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["name", "consensus", "actual", "significance"],
        },
        "peers": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "pe": {"type": "number"},
                "pb": {"type": "number"},
                "ps": {"type": "number"},
                "ev_ebitda": {"type": "number"},
                "revenue_growth": {"type": "number"},
                "roe": {"type": "number"},
            },
            "required": ["symbol"],
        },
        "pillars": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pillar description"},
                "status": {"type": "string", "enum": ["on_track", "mixed", "broken"]},
                "weight": {"type": "number", "description": "Importance weight 0-100"},
                "evidence": {"type": "string", "description": "Brief evidence"},
            },
            "required": ["name", "status", "weight"],
        },
        "positions": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "weight_pct": {"type": "number"},
                "beta": {"type": "number"},
            },
            "required": ["symbol", "weight_pct", "beta"],
        },
    }

    # Detailed schema for object-type params
    OBJECT_SCHEMA = {
        "target": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "pe": {"type": "number"},
                "pb": {"type": "number"},
                "ps": {"type": "number"},
                "ev_ebitda": {"type": "number"},
                "earnings": {"type": "number", "description": "Total earnings (for PE method)"},
                "revenue": {"type": "number", "description": "Total revenue (for PS method)"},
                "ebitda": {"type": "number", "description": "EBITDA (for EV/EBITDA method)"},
                "shares_outstanding": {"type": "number"},
                "current_price": {"type": "number"},
            },
            "required": ["symbol", "shares_outstanding", "current_price"],
        },
    }

    allowed_tools = ROLE_TOOLS_MAP.get(role) if role else None
    tools = []
    for tool_def in TOOL_DEFINITIONS:
        # Removed allowed_tools filtering to allow LLM to use any tool when data is missing
        properties = {}
        required = []
        for param_name, param_info in tool_def.get("parameters", {}).items():
            prop = {
                "type": param_info["type"],
                "description": param_info["description"]
            }
            # Provide detailed items schema for array types
            if param_info["type"] == "array":
                prop["items"] = ARRAY_ITEMS_SCHEMA.get(param_name, {"type": "object"})
            # Provide detailed properties for object types
            elif param_info["type"] == "object" and param_name in OBJECT_SCHEMA:
                prop.update(OBJECT_SCHEMA[param_name])
            properties[param_name] = prop
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
    Includes a session-level result cache for financial_data to avoid
    redundant API calls across expert rounds (e.g., Screener and Risk Auditor
    fetching the same stock data).
    """

    def __init__(self):
        self._search_service = None
        self._brain_manager = None
        self._financial_cache: Dict[str, str] = {}  # Cache: "symbol|query_hash" -> result

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
        """Execute a single tool call and return formatted observation.
        All outputs pass through TokenGuard for defensive size enforcement."""
        from .tools_config import is_tool_enabled
        from .token_guard import token_guard

        tool_name = tool_call.get("tool", "")
        query = tool_call.get("query", "")
        reason = tool_call.get("reason", "")

        # Check if tool is enabled in config
        if not is_tool_enabled(tool_name):
            return f"<tool_observation>\nTool '{tool_name}' is currently disabled. Check tools_config.yaml to re-enable it.\n</tool_observation>"

        # Computation tools (deterministic, no async needed)
        if tool_name in COMPUTATION_TOOL_NAMES:
            return self._exec_computation(tool_name, tool_call)

        if not query and tool_name != "financial_data":
            return f"<tool_observation>\nError: Empty query for tool '{tool_name}'.\n</tool_observation>"

        try:
            if tool_name == "web_search":
                raw = await self._exec_web_search(query)
            elif tool_name == "news_search":
                raw = await self._exec_news_search(query)
            elif tool_name == "announcement_search":
                raw = await self._exec_announcement_search(query)
            elif tool_name == "report_search":
                raw = await self._exec_report_search(query)
            elif tool_name == "knowledge_search":
                raw = await self._exec_knowledge_search(query)
            elif tool_name == "deep_scrape":
                url = tool_call.get("url", "")
                if not url:
                    return "<tool_observation>\nError: deep_scrape requires a 'url' parameter.\n</tool_observation>"
                raw = await self._exec_deep_scrape(url, query)
            elif tool_name == "financial_data":
                symbol = tool_call.get("symbol", "")
                if not symbol:
                    return "<tool_observation>\nError: financial_data requires a 'symbol' parameter.\n</tool_observation>"
                raw = await self._exec_financial_data(symbol, query)
            elif tool_name == "macro_query":
                raw = await self._exec_macro_query(query)
            elif tool_name == "business_query":
                raw = await self._exec_business_query(query)
            elif tool_name == "finance_query":
                raw = await self._exec_finance_query(query)
            elif tool_name == "management_query":
                raw = await self._exec_management_query(query)
            elif tool_name == "commodity_price_query":
                raw = await self._exec_commodity_price_query(query)
            elif tool_name == "futures_query":
                raw = await self._exec_futures_query(query)
            elif tool_name == "valuation_query":
                raw = await self._exec_valuation_query(query)
            elif tool_name == "industry_query":
                raw = await self._exec_industry_query(query)
            elif tool_name == "policy_query":
                raw = await self._exec_policy_query(query)
            else:
                return f"<tool_observation>\nError: Unknown tool '{tool_name}'. Available: web_search, news_search, announcement_search, report_search, knowledge_search, deep_scrape, financial_data, macro_query, business_query, finance_query, management_query, commodity_price_query, futures_query, valuation_query, industry_query, policy_query, dcf_calculator, position_sizer, kelly_calculator, beat_miss_scorer, comps_valuation, pillar_scorer, dupont_decomposition, minervini_stage, earnings_quality_audit, drawdown_scenario, risk_reward, stop_loss_validator, cagr_calculator.\n</tool_observation>"
            
            # TokenGuard: enforce per-tool char limits and round budget
            return token_guard.enforce(tool_name, raw)
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

    async def _exec_news_search(self, query: str) -> str:
        """Search news using Iwencai (同花顺问财) as primary for Chinese financial news,
        with SearXNG as supplement for international coverage.
        
        Token-defensive: 5 iwencai + 3 searxng, title≤80, content≤150 chars."""
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
            from .data_providers.iwencai_news import search_news as iwencai_search
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

        # Format Iwencai results (compact: no URL, short fields)
        if iwencai_results:
            for i, r in enumerate(iwencai_results, 1):
                lines.append(f"{i}. [{r['date']}] {r['title']}")
                if r['content']:
                    lines.append(f"   {r['content']}")

        # Supplement with SearXNG for broader/international coverage
        searxng_results = await self.search_service.search_news(query, max_results=MAX_SEARXNG)
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

    async def _exec_announcement_search(self, query: str) -> str:
        """Search company announcements via Iwencai (同花顺问财).
        Token-defensive: max 6 items, title≤80, summary≤200, no URL."""
        MAX_ITEMS = 6
        MAX_TITLE = 80
        MAX_SUMMARY = 200

        try:
            from .data_providers.iwencai_news import search_announcements
            raw = await search_announcements(query)
            if raw.get("error"):
                return f"<tool_observation>\nAnnouncement error: {raw['error']}\n</tool_observation>"
            items = raw.get("data", [])
            if not items:
                return "<tool_observation>\nNo announcements found.\n</tool_observation>"

            lines = ["<tool_observation>"]
            lines.append(f"Announcements: {query}")
            lines.append("")
            for i, item in enumerate(items[:MAX_ITEMS], 1):
                title = item.get("title", "")[:MAX_TITLE]
                date = item.get("publish_date", "")[:10]
                summary = item.get("summary", "")[:MAX_SUMMARY]
                lines.append(f"{i}. [{date}] {title}")
                if summary:
                    lines.append(f"   {summary}")
            lines.append("</tool_observation>")
            return "\n".join(lines)
        except Exception as e:
            return f"<tool_observation>\nAnnouncement error: {str(e)}\n</tool_observation>"

    async def _exec_report_search(self, query: str) -> str:
        """Search analyst research reports via Iwencai (同花顺问财).
        Token-defensive: max 6 items, title≤80, summary≤250, no URL."""
        MAX_ITEMS = 6
        MAX_TITLE = 80
        MAX_SUMMARY = 250

        try:
            from .data_providers.iwencai_news import search_reports
            raw = await search_reports(query)
            if raw.get("error"):
                return f"<tool_observation>\nReport search error: {raw['error']}\n</tool_observation>"
            items = raw.get("data", [])
            if not items:
                return "<tool_observation>\nNo research reports found.\n</tool_observation>"

            lines = ["<tool_observation>"]
            lines.append(f"Research reports: {query}")
            lines.append("")
            for i, item in enumerate(items[:MAX_ITEMS], 1):
                title = item.get("title", "")[:MAX_TITLE]
                date = item.get("publish_date", "")[:10]
                summary = item.get("summary", "")[:MAX_SUMMARY]
                source = item.get("extra", {}).get("real_publish_source", "")[:20]
                lines.append(f"{i}. [{date}] {title} ({source})")
                if summary:
                    lines.append(f"   {summary}")
            lines.append("</tool_observation>")
            return "\n".join(lines)
        except Exception as e:
            return f"<tool_observation>\nReport search error: {str(e)}\n</tool_observation>"

    async def _exec_macro_query(self, query: str) -> str:
        """Query macroeconomic data via Iwencai (同花顺问财) hithink-macro-query skill."""
        return await self._exec_iwencai_query(query, "hithink-macro-query", "Macro data")

    async def _exec_business_query(self, query: str) -> str:
        """Query company business/operations data via Iwencai (同花顺问财)."""
        return await self._exec_iwencai_query(query, "hithink-business-query", "Business data")

    async def _exec_finance_query(self, query: str) -> str:
        """Query company financial data via Iwencai (同花顺问财)."""
        return await self._exec_iwencai_query(query, "hithink-finance-query", "Financial data")

    async def _exec_management_query(self, query: str) -> str:
        """Query company shareholder/management data via Iwencai (同花顺问财)."""
        return await self._exec_iwencai_query(query, "hithink-management-query", "Management/shareholder data")

    async def _exec_commodity_price_query(self, query: str) -> str:
        """Search for commodity spot prices using Iwencai comprehensive search."""
        import os
        from datetime import datetime
        MAX_ITEMS = 8
        MAX_TITLE = 80
        MAX_CONTENT = 250

        lines = ["<tool_observation>"]
        lines.append(f"Commodity Price Search: {query}")
        lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        try:
            from .data_providers.iwencai_news import search_comprehensive
            raw = await search_comprehensive(query)
            if raw.get("status_code") == 0 and raw.get("data"):
                # Sort by publish date descending
                items = raw["data"]
                def get_date(x):
                    d = x.get("publish_date", "")
                    return d if d else "0000-00-00"
                items.sort(key=get_date, reverse=True)
                
                count = 0
                for item in items:
                    if count >= MAX_ITEMS:
                        break
                    title = item.get("title", "")[:MAX_TITLE]
                    content = item.get("summary", "")[:MAX_CONTENT]
                    date = item.get("publish_date", "")[:10]
                    source = item.get("extra", {}).get("real_publish_source", "")[:20]
                    
                    lines.append(f"{count+1}. [{date}] {title} ({source})")
                    if content:
                        lines.append(f"   {content}")
                    count += 1
                if count == 0:
                    lines.append("No results found in Iwencai comprehensive search.")
            else:
                lines.append("No results found in Iwencai comprehensive search.")
        except Exception as e:
            lines.append(f"Error querying Iwencai: {str(e)}")

        lines.append("</tool_observation>")
        return "\n".join(lines)

    async def _exec_futures_query(self, query: str) -> str:
        """Query futures and commodity spot prices via Iwencai (同花顺问财)."""
        return await self._exec_iwencai_query(query, "hithink-futures-query", "Futures/commodity data")

    async def _exec_valuation_query(self, query: str) -> str:
        """Query stock valuation metrics via Iwencai (同花顺问财)."""
        return await self._exec_iwencai_query(query, "hithink-valuation-query", "Valuation data")

    async def _exec_industry_query(self, query: str) -> str:
        """Query industry/sector themes and concept stocks via Iwencai (同花顺问财)."""
        return await self._exec_iwencai_query(query, "hithink-industry-query", "Industry data")

    async def _exec_policy_query(self, query: str) -> str:
        """Query national/local policy drivers and concept inclusions via Iwencai (同花顺问财)."""
        return await self._exec_iwencai_query(query, "hithink-policy-query", "Policy data")

    async def _exec_iwencai_query(self, query: str, skill_id: str, label: str) -> str:
        """Generic Iwencai query2data API call for structured data skills.
        Token-defensive: max 8 items, 6 fields/item, values truncated to 50 chars."""
        import os
        import secrets
        import httpx
        import json as _json

        MAX_ITEMS = 8
        MAX_FIELDS = 6
        MAX_VALUE_LEN = 50

        api_key = os.getenv("IWENCAI_API_KEY", "")
        if not api_key:
            return f"<tool_observation>\n{label}: IWENCAI_API_KEY not configured.\n</tool_observation>"

        url = "https://openapi.iwencai.com/v1/query2data"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Claw-Call-Type": "normal",
            "X-Claw-Skill-Id": skill_id,
            "X-Claw-Skill-Version": "1.0.0",
            "X-Claw-Plugin-Id": "none",
            "X-Claw-Plugin-Version": "none",
            "X-Claw-Trace-Id": secrets.token_hex(32),
        }
        payload = {
            "query": query,
            "page": "1",
            "limit": str(MAX_ITEMS),
            "is_cache": "1",
            "expand_index": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            # Parse response - handle both list and dict formats
            datas = data.get("datas", data.get("data", []))
            if not datas:
                text_resp = data.get("text_response", "")
                if text_resp:
                    return f"<tool_observation>\n{label}: {query}\n{text_resp[:500]}\n</tool_observation>"
                return f"<tool_observation>\nNo {label.lower()} found.\n</tool_observation>"

            lines = ["<tool_observation>"]
            lines.append(f"{label}: {query} ({len(datas)} items)")
            lines.append("")

            for item in datas[:MAX_ITEMS]:
                if isinstance(item, dict):
                    # Strict field limit + value truncation
                    parts = []
                    for k, v in list(item.items())[:MAX_FIELDS]:
                        if v is not None and v != "":
                            v_str = str(v)[:MAX_VALUE_LEN]
                            parts.append(f"{k}:{v_str}")
                    if parts:
                        lines.append("• " + " | ".join(parts))
                else:
                    lines.append(f"• {str(item)[:100]}")
            lines.append("</tool_observation>")
            return "\n".join(lines)
        except httpx.HTTPStatusError as e:
            return f"<tool_observation>\n{label} HTTP error: {e.response.status_code}\n</tool_observation>"
        except Exception as e:
            return f"<tool_observation>\n{label} error: {str(e)}\n</tool_observation>"

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
        BLOCKED_DOMAINS = ["finance.yahoo.com", "yahoo.com", "login.yahoo.com"]
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
        """Fetch structured financial data from AkShare/yfinance based on the query.
        Uses DataRouter first for A-shares (fastest path), falls back to direct APIs.
        Uses session-level cache to avoid redundant API calls across expert rounds.
        
        Token-defensive: field whitelists, row limits, internal char budget."""
        import akshare as ak
        import yfinance as yf
        from ..utils.network import safe_ak_call
        from ..services.data_providers import data_router
        from ..utils.data_validation import validate_ak_data
        from .token_guard import token_guard

        # Hard limits for this tool (internal budget before TokenGuard's external enforcement)
        MAX_PERIODS = 4          # Max historical periods to show
        MAX_ROWS = 5             # Max data rows per section
        MAX_SECTION_CHARS = 800  # Max chars per section
        INTERNAL_BUDGET = 4500   # Stop adding sections after this many chars

        # Cache key: symbol + normalized query keywords for category matching
        cache_key = f"{symbol}|{query.lower().strip()}"
        if cache_key in self._financial_cache:
            print(f"  [ToolExecutor] financial_data CACHE HIT: {symbol}")
            return self._financial_cache[cache_key]

        query_lower = query.lower()
        lines = ["<tool_observation>"]
        lines.append(f"Financial data: {symbol} | {query}")
        lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("")

        def _chars_so_far():
            return sum(len(l) for l in lines)

        def _budget_ok():
            return _chars_so_far() < INTERNAL_BUDGET

        is_a_share = symbol.isdigit() and len(symbol) == 6

        def _fmt_num(v):
            """Compact number formatting: 1.23B / 45.6M / 1,234"""
            if v is None or (isinstance(v, float) and v != v):
                return "N/A"
            if isinstance(v, (int, float)):
                if abs(v) >= 1e9:
                    return f"{v/1e9:.2f}B"
                if abs(v) >= 1e6:
                    return f"{v/1e6:.1f}M"
                if abs(v) >= 1e3:
                    return f"{v:,.0f}"
                return f"{v:.2f}"
            return str(v)[:30]

        try:
            if is_a_share:
                # --- A-Share: Fast path via DataRouter (Tencent/Sina, no rate limits) ---
                if _budget_ok():
                    try:
                        summary = await data_router.get_financial_summary(symbol)
                        if summary and "error" not in summary:
                            lines.append("## DataRouter 财务概览")
                            key_fields = ["name", "price", "pe", "pb", "roe", "marketCap",
                                          "revenue", "netProfit", "revenueGrowth", "netProfitGrowth",
                                          "eps", "turnoverPct", "industry"]
                            parts = []
                            for f in key_fields:
                                v = summary.get(f)
                                if v is not None and v != "":
                                    parts.append(f"{f}:{v}")
                            if parts:
                                lines.append(" | ".join(parts))
                                lines.append("")
                    except Exception as e:
                        pass  # Non-fatal — fall through to detailed sections below

                # --- A-Share: Quarterly financial abstract ---
                if _budget_ok() and any(kw in query_lower for kw in ["quarter", "earnings", "revenue", "profit", "净利润", "营收", "扣非", "季度", "eps", "roe", "margin"]):
                    try:
                        df = await safe_ak_call(ak.stock_financial_abstract_ths, symbol=symbol)
                        if validate_ak_data(df, min_rows=1):
                            lines.append("## 季度财务摘要")
                            # Whitelist: only the most analytically important fields
                            whitelist = ['报告期', '净利润', '净利润同比增长率', '营业总收入', 
                                        '营业总收入同比增长率', '基本每股收益', '净资产收益率', '资产负债率']
                            available = [c for c in whitelist if c in df.columns]
                            for _, row in df.tail(MAX_PERIODS).iterrows():
                                vals = [f"{c}:{row.get(c, 'N/A')}" for c in available]
                                lines.append(" | ".join(vals))
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ quarterly failed: {e}")

                # --- Balance sheet ---
                if _budget_ok() and any(kw in query_lower for kw in ["balance", "cash", "debt", "asset", "资产", "负债", "现金"]):
                    try:
                        yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                        ticker = yf.Ticker(yf_symbol)
                        bs = ticker.balance_sheet
                        if bs is not None and not bs.empty:
                            lines.append("## 资产负债表")
                            key_items = ['Total Assets', 'Total Liabilities Net Minority Interest',
                                         'Cash And Cash Equivalents', 'Total Debt', 'Current Assets', 'Current Liabilities']
                            for item in key_items:
                                if item in bs.index:
                                    row = bs.loc[item]
                                    vals = [f"{str(col)[:10]}:{_fmt_num(v)}" for col, v in list(row.items())[:MAX_PERIODS] if v is not None and v == v]
                                    if vals:
                                        lines.append(f"- {item}: {' | '.join(vals)}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ balance sheet failed: {e}")

                # --- Cash flow ---
                if _budget_ok() and any(kw in query_lower for kw in ["cash flow", "capex", "fcf", "现金流", "资本开支"]):
                    try:
                        yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                        ticker = yf.Ticker(yf_symbol)
                        cf = ticker.cashflow
                        if cf is not None and not cf.empty:
                            lines.append("## 现金流量表")
                            key_items = ['Operating Cash Flow', 'Capital Expenditure', 'Free Cash Flow']
                            for item in key_items:
                                if item in cf.index:
                                    row = cf.loc[item]
                                    vals = [f"{str(col)[:10]}:{_fmt_num(v)}" for col, v in list(row.items())[:MAX_PERIODS] if v is not None and v == v]
                                    if vals:
                                        lines.append(f"- {item}: {' | '.join(vals)}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ cash flow failed: {e}")

                # --- Income statement ---
                if _budget_ok() and any(kw in query_lower for kw in ["income", "利润表", "cost", "成本", "breakdown"]):
                    try:
                        yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                        ticker = yf.Ticker(yf_symbol)
                        fin = ticker.financials
                        if fin is not None and not fin.empty:
                            lines.append("## 利润表")
                            key_items = ['Total Revenue', 'Gross Profit', 'Operating Income', 'Net Income', 'EBITDA']
                            for item in key_items:
                                if item in fin.index:
                                    row = fin.loc[item]
                                    vals = [f"{str(col)[:10]}:{_fmt_num(v)}" for col, v in list(row.items())[:MAX_PERIODS] if v is not None and v == v]
                                    if vals:
                                        lines.append(f"- {item}: {' | '.join(vals)}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ income statement failed: {e}")

                # --- Dividend (field whitelist) ---
                if _budget_ok() and any(kw in query_lower for kw in ["dividend", "分红", "派息", "股息"]):
                    try:
                        div_df = await safe_ak_call(ak.stock_history_dividend_detail, symbol=symbol)
                        if validate_ak_data(div_df, min_rows=1):
                            lines.append("## 分红历史")
                            # Whitelist only essential dividend fields
                            div_whitelist = ['除权除息日', '送转股份', '派息', '股权登记日']
                            available_div = [c for c in div_whitelist if c in div_df.columns]
                            if not available_div:
                                # Fallback: take first 4 columns
                                available_div = list(div_df.columns[:4])
                            for _, row in div_df.head(MAX_ROWS).iterrows():
                                vals = [f"{c}:{row.get(c, '')}" for c in available_div]
                                lines.append(" | ".join(vals))
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ dividend failed: {e}")

                # --- Peer comparison (reduced) ---
                if _budget_ok() and any(kw in query_lower for kw in ["peer", "industry", "比较", "同业", "行业", "对标"]):
                    try:
                        from .search_service import search_service
                        search_res = await search_service.quick_search(f"{symbol} 行业对比 PE PB ROE 同业估值")
                        if search_res:
                            lines.append("## 行业对比")
                            lines.append(search_res[:1000])
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ peer comparison failed: {e}")

            else:
                # --- US/HK data from yfinance ---
                yf_symbol = symbol
                if symbol.endswith(".HK") or (symbol.isdigit() and len(symbol) <= 5):
                    clean = symbol.replace(".HK", "").zfill(4)
                    yf_symbol = f"{clean}.HK"

                ticker = yf.Ticker(yf_symbol)

                if _budget_ok() and any(kw in query_lower for kw in ["valuation", "pe", "pb", "roe", "margin", "marketcap", "peer", "industry", "估值", "对标", "同业", "市盈率", "市净率"]):
                    try:
                        info = ticker.info
                        if info:
                            lines.append("## Valuation & Key Metrics")
                            lines.append(f"- Market Cap: {_fmt_num(info.get('marketCap'))}")
                            lines.append(f"- Trailing PE: {_fmt_num(info.get('trailingPE'))}")
                            lines.append(f"- Forward PE: {_fmt_num(info.get('forwardPE'))}")
                            lines.append(f"- Price to Book (PB): {_fmt_num(info.get('priceToBook'))}")
                            roe_val = info.get('returnOnEquity')
                            roe_str = f"{roe_val * 100:.2f}%" if isinstance(roe_val, (int, float)) else "N/A"
                            lines.append(f"- Return on Equity (ROE): {roe_str}")
                            margin_val = info.get('profitMargins')
                            margin_str = f"{margin_val * 100:.2f}%" if isinstance(margin_val, (int, float)) else "N/A"
                            lines.append(f"- Net Profit Margin: {margin_str}")
                            lines.append("")
                    except Exception as e:
                        lines.append(f"⚠ valuation metrics failed: {e}")

                if _budget_ok() and any(kw in query_lower for kw in ["quarter", "earnings", "revenue", "profit", "eps"]):
                    qf = ticker.quarterly_financials
                    if qf is not None and not qf.empty:
                        lines.append("## Quarterly Financials")
                        for item in ['Total Revenue', 'Net Income', 'Gross Profit', 'Operating Income', 'EBITDA']:
                            if item in qf.index:
                                row = qf.loc[item]
                                vals = [f"{str(col)[:10]}:{_fmt_num(v)}" for col, v in list(row.items())[:MAX_PERIODS] if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals)}")
                        lines.append("")

                if _budget_ok() and any(kw in query_lower for kw in ["balance", "cash", "debt", "asset"]):
                    bs = ticker.balance_sheet
                    if bs is not None and not bs.empty:
                        lines.append("## Balance Sheet")
                        for item in ['Total Assets', 'Total Liabilities Net Minority Interest', 'Cash And Cash Equivalents',
                                     'Total Debt', 'Current Assets', 'Current Liabilities']:
                            if item in bs.index:
                                row = bs.loc[item]
                                vals = [f"{str(col)[:10]}:{_fmt_num(v)}" for col, v in list(row.items())[:MAX_PERIODS] if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals)}")
                        lines.append("")

                if _budget_ok() and any(kw in query_lower for kw in ["cash flow", "capex", "fcf"]):
                    cf = ticker.cashflow
                    if cf is not None and not cf.empty:
                        lines.append("## Cash Flow")
                        for item in ['Operating Cash Flow', 'Capital Expenditure', 'Free Cash Flow']:
                            if item in cf.index:
                                row = cf.loc[item]
                                vals = [f"{str(col)[:10]}:{_fmt_num(v)}" for col, v in list(row.items())[:MAX_PERIODS] if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals)}")
                        lines.append("")

                if _budget_ok() and any(kw in query_lower for kw in ["income", "breakdown", "cost"]):
                    fin = ticker.financials
                    if fin is not None and not fin.empty:
                        lines.append("## Income Statement")
                        for item in ['Total Revenue', 'Gross Profit', 'Operating Income', 'Net Income', 'EBITDA']:
                            if item in fin.index:
                                row = fin.loc[item]
                                vals = [f"{str(col)[:10]}:{_fmt_num(v)}" for col, v in list(row.items())[:MAX_PERIODS] if v is not None and v == v]
                                if vals:
                                    lines.append(f"- {item}: {' | '.join(vals)}")
                        lines.append("")

                if _budget_ok() and any(kw in query_lower for kw in ["dividend"]):
                    divs = ticker.dividends
                    if divs is not None and len(divs) > 0:
                        lines.append("## Dividend History")
                        for date, val in list(divs.items())[-5:]:
                            lines.append(f"  {str(date)[:10]}: {val:.4f}")
                        lines.append("")

        except Exception as e:
            lines.append(f"⚠ Financial data query failed: {str(e)}")

        # --- OpenBB enrichment (US/HK stocks, only if budget allows) ---
        if not is_a_share and _budget_ok():
            try:
                from .openbb_service import openbb_service
                openbb_result = await openbb_service.query(symbol, query)
                if openbb_result:
                    # Truncate OpenBB result to fit within remaining budget
                    remaining = INTERNAL_BUDGET - _chars_so_far()
                    if len(openbb_result) > remaining:
                        openbb_result = openbb_result[:remaining] + "\n[OpenBB data truncated]"
                    lines.append(openbb_result)
            except Exception as e:
                lines.append(f"⚠ OpenBB enrichment failed: {e}")

        if len(lines) <= 4:
            lines.append("No matching financial data found for the query. Try a more specific query or different keywords.")

        lines.append("</tool_observation>")
        result = "\n".join(lines)
        
        # Store in cache for future rounds
        self._financial_cache[cache_key] = result
        return result

    async def execute_all(self, tool_calls: List[Dict[str, str]]) -> List[str]:
        """Execute multiple tool calls in parallel for speed (respects TokenGuard budget)."""
        async def _run_one(tc):
            label = tc.get('url', tc.get('symbol', tc.get('query', '')))[:60]
            print(f"  [ToolExecutor] {tc['tool']}: {label}...")
            return await self.execute(tc)

        observations = await asyncio.gather(*[_run_one(tc) for tc in tool_calls], return_exceptions=True)
        results = []
        for obs in observations:
            if isinstance(obs, Exception):
                results.append(f"<tool_observation>\nTool execution error: {obs}\n</tool_observation>")
            else:
                results.append(obs)
        return results

    def clear_cache(self):
        """Clear the financial data cache. Call between analysis jobs."""
        self._financial_cache.clear()


# Singleton
tool_executor = ToolExecutor()
