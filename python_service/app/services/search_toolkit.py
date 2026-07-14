"""
SearchToolkit — Pre-search enrichment for AI analyst pipeline.

Runs batch searches ONCE per analysis job, then distributes relevant
results to each expert role. Works with ALL models (Gemini, DeepSeek, etc.)
by injecting search context as text — no LLM tool-calling needed.

Architecture:
  1. batch_search() — runs ~8 category searches at analysis start
  2. get_enrichment_for_role() — filters results by expert role
  3. format_enrichment() — formats for prompt injection
"""

import os
import asyncio
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from .search_service import search_service


# ────────────── CATEGORY DEFINITIONS ──────────────

# Query templates per search category. {name} and {symbol} are substituted.
SEARCH_CATEGORIES = {
    "latest_news": {
        "query": "{name} {symbol} latest news",
        "max_results": 5,
        "label_zh": "最新新闻",
        "label_en": "Latest News",
    },
    "financial_performance": {
        "query": "{name} {symbol} latest quarterly earnings revenue profit results",
        "max_results": 3,
        "label_zh": "最新财务业绩",
        "label_en": "Financial Performance",
    },
    "analyst_ratings": {
        "query": "{name} {symbol} analyst ratings price target consensus upgrade downgrade",
        "max_results": 3,
        "label_zh": "分析师评级与目标价",
        "label_en": "Analyst Ratings & Price Targets",
    },
    "competitive_landscape": {
        "query": "{name} {symbol} competitors market share industry comparison",
        "max_results": 3,
        "label_zh": "竞争格局",
        "label_en": "Competitive Landscape",
    },
    "risk_factors": {
        "query": "{name} {symbol} risk factors regulatory lawsuits short seller concerns",
        "max_results": 3,
        "label_zh": "风险因素",
        "label_en": "Risk Factors",
    },
    "sentiment_social": {
        "query": "{name} {symbol} investor sentiment social media discussion forum",
        "max_results": 3,
        "label_zh": "市场情绪与社媒讨论",
        "label_en": "Market Sentiment & Social Media",
    },
    "industry_trends": {
        "query": "{name} {symbol} industry sector trends outlook forecast",
        "max_results": 3,
        "label_zh": "行业趋势与展望",
        "label_en": "Industry Trends & Outlook",
    },
    "management_insider": {
        "query": "{name} {symbol} management CEO insider trading leadership changes",
        "max_results": 3,
        "label_zh": "管理层与内部人交易",
        "label_en": "Management & Insider Activity",
    },
}

# Which search categories each expert role needs
ROLE_CATEGORY_MAP = {
    "Deep Research Specialist": [
        "latest_news", "financial_performance", "competitive_landscape",
        "management_insider", "industry_trends",
    ],
    "Technical Analyst": ["latest_news"],
    "Fundamental Analyst": [
        "financial_performance", "competitive_landscape", "analyst_ratings",
    ],
    "Sentiment Analyst": [
        "sentiment_social", "latest_news",
    ],
    "Bull Researcher": [
        "financial_performance", "industry_trends", "analyst_ratings",
    ],
    "Bear Researcher": [
        "risk_factors", "competitive_landscape", "latest_news",
    ],
    "Contrarian Strategist": [
        "risk_factors", "analyst_ratings", "sentiment_social",
    ],
    "Aggressive Risk Analyst": ["risk_factors", "latest_news"],
    "Conservative Risk Analyst": ["risk_factors", "latest_news"],
    "Neutral Risk Analyst": ["risk_factors", "latest_news"],
    "Risk Manager": ["risk_factors", "latest_news"],
    "Professional Reviewer": [
        "latest_news", "analyst_ratings",
    ],
    "Soros-style Financial Philosopher": [
        "latest_news", "industry_trends",
    ],
    "Growth Visionary": [
        "industry_trends", "financial_performance",
    ],
    "Macro Hedge Titan": [
        "industry_trends", "latest_news",
    ],
    "Value Investing Sage": [
        "financial_performance", "competitive_landscape",
    ],
    "Chief Strategist": [
        "latest_news", "analyst_ratings", "risk_factors",
    ],
}

# A-share specific extra categories
A_SHARE_EXTRA_CATEGORIES = {
    "northbound_flow": {
        "query": "{name} {symbol} 北向资金 净流入 沪深港通",
        "max_results": 3,
        "label_zh": "北向资金流向",
        "label_en": "Northbound Fund Flow",
    },
    "dragon_tiger": {
        "query": "{name} {symbol} 龙虎榜 游资 机构 席位",
        "max_results": 3,
        "label_zh": "龙虎榜数据",
        "label_en": "Dragon & Tiger Board",
    },
    "margin_trading": {
        "query": "{name} {symbol} 融资融券 两融余额",
        "max_results": 3,
        "label_zh": "融资融券数据",
        "label_en": "Margin Trading Data",
    },
    "lockup_release": {
        "query": "{name} {symbol} 限售股解禁 解禁计划",
        "max_results": 3,
        "label_zh": "限售股解禁",
        "label_en": "Lockup Release",
    },
    "shareholder_reduction": {
        "query": "{name} {symbol} 股东减持 减持计划",
        "max_results": 3,
        "label_zh": "股东减持公告",
        "label_en": "Shareholder Reduction",
    },
}

# A-share roles get extra categories
A_SHARE_ROLE_EXTRAS = {
    "Sentiment Analyst": ["northbound_flow", "dragon_tiger", "margin_trading"],
    "Deep Research Specialist": ["northbound_flow", "lockup_release", "shareholder_reduction"],
    "Bull Researcher": ["northbound_flow"],
    "Bear Researcher": ["dragon_tiger", "lockup_release", "shareholder_reduction"],
    "Risk Manager": ["lockup_release", "shareholder_reduction"],
    "Aggressive Risk Analyst": ["lockup_release", "shareholder_reduction"],
    "Conservative Risk Analyst": ["lockup_release", "shareholder_reduction"],
    "Neutral Risk Analyst": ["lockup_release", "shareholder_reduction"],
    "Chief Strategist": ["lockup_release", "shareholder_reduction"],
}


class SearchToolkit:
    """
    Pre-search enrichment engine for the AI analyst pipeline.

    Usage:
        toolkit = SearchToolkit()
        # At analysis start — run batch search once
        all_results = await toolkit.batch_search("NVO", "Novo Nordisk")
        # For each expert — get their subset
        enrichment = toolkit.get_enrichment_for_role("Sentiment Analyst", all_results)
        # Format for prompt injection
        text = toolkit.format_enrichment(enrichment, language="zh-CN")
    """

    def __init__(self):
        self.enabled = os.getenv("SEARCH_ENRICHMENT_ENABLED", "true").lower() in ("true", "1", "yes")
        self._rate_limit_delay = float(os.getenv("SEARCH_RATE_LIMIT_DELAY", "0.5"))  # seconds between searches
        self._cache: Dict[str, Dict[str, Any]] = {}  # symbol -> {category -> results}
        self._cache_ttl = 600  # 10 minutes cache

    def _detect_market(self, symbol: str) -> str:
        """Detect market type from symbol format."""
        if symbol.endswith(".HK"):
            return "hk"
        if symbol.endswith(".SH") or symbol.endswith(".SZ"):
            return "a_share"
        if symbol.isdigit() and len(symbol) == 6:
            return "a_share"
        return "us"

    async def batch_search(
        self,
        symbol: str,
        name: str,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run all category searches at once for a given stock.
        Returns {category_name: [search_results]}.

        Results are cached for 10 minutes to avoid redundant searches
        within the same analysis job.
        """
        if not self.enabled:
            print("[SearchToolkit] Disabled via SEARCH_ENRICHMENT_ENABLED=false")
            return {}

        # Check cache
        cache_key = f"{symbol}_{name}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.time() - cached.get("_timestamp", 0) < self._cache_ttl:
                print(f"[SearchToolkit] Using cached results for {symbol}")
                return {k: v for k, v in cached.items() if k != "_timestamp"}

        market = self._detect_market(symbol)
        all_categories = dict(SEARCH_CATEGORIES)

        # Add A-share specific categories
        if market == "a_share":
            all_categories.update(A_SHARE_EXTRA_CATEGORIES)

        print(f"[SearchToolkit] Starting batch search for {symbol} ({name}), {len(all_categories)} categories")
        results: Dict[str, List[Dict[str, Any]]] = {}
        search_start = time.time()

        # Run searches with rate limiting
        for cat_name, cat_config in all_categories.items():
            query = cat_config["query"].format(name=name, symbol=symbol)
            max_results = cat_config.get("max_results", 3)

            try:
                cat_results = await search_service.search(query, max_results=max_results)
                if cat_results:
                    results[cat_name] = cat_results
                    print(f"  [SearchToolkit] {cat_name}: {len(cat_results)} results")
                else:
                    print(f"  [SearchToolkit] {cat_name}: no results")
            except Exception as e:
                print(f"  [SearchToolkit] {cat_name} failed: {e}")

            # Rate limiting to avoid overloading search provider
            if self._rate_limit_delay > 0:
                await asyncio.sleep(self._rate_limit_delay)

        elapsed = time.time() - search_start
        print(f"[SearchToolkit] Batch search complete: {len(results)}/{len(all_categories)} categories, {elapsed:.1f}s")

        # Cache results
        results["_timestamp"] = time.time()
        self._cache[cache_key] = results

        return {k: v for k, v in results.items() if k != "_timestamp"}

    def get_enrichment_for_role(
        self,
        role: str,
        all_results: Dict[str, List[Dict[str, Any]]],
        market: str = "us",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Filter batch search results to only the categories relevant to a specific expert role.
        """
        if not all_results:
            return {}

        # Get standard categories for this role
        categories = list(ROLE_CATEGORY_MAP.get(role, ["latest_news"]))

        # Add A-share extras if applicable
        if market == "a_share" and role in A_SHARE_ROLE_EXTRAS:
            categories.extend(A_SHARE_ROLE_EXTRAS[role])

        enrichment = {}
        for cat in categories:
            if cat in all_results:
                enrichment[cat] = all_results[cat]

        return enrichment

    def format_enrichment(
        self,
        enrichment: Dict[str, List[Dict[str, Any]]],
        language: str = "zh-CN",
    ) -> str:
        """
        Format search enrichment results into a prompt-injectable text block.
        """
        if not enrichment:
            return ""

        is_zh = language == "zh-CN"
        lines = []
        lines.append("--- [SEARCH ENRICHMENT] 预搜索数据 ---" if is_zh else "--- [SEARCH ENRICHMENT] Pre-Search Data ---")
        lines.append(
            "以下数据由系统在分析开始前自动搜索获取 (SearxNG/Iwencai)，供参考。"
            if is_zh else
            "The following data was automatically retrieved by the system before analysis (SearxNG/Iwencai), for reference."
        )
        lines.append(
            "⚠ 搜索数据可能存在时效性或准确性问题，请结合 [API DATA] 交叉验证。"
            if is_zh else
            "⚠ Search data may have timeliness/accuracy issues. Cross-validate with [API DATA]."
        )
        lines.append("")

        for cat_name, cat_results in enrichment.items():
            # Get label
            cat_config = SEARCH_CATEGORIES.get(cat_name) or A_SHARE_EXTRA_CATEGORIES.get(cat_name, {})
            label = cat_config.get("label_zh" if is_zh else "label_en", cat_name)

            lines.append(f"**[{label}]**")
            for i, r in enumerate(cat_results[:5], 1):
                title = search_service.sanitize_text(r.get("title", "N/A"))
                content = search_service.sanitize_text(r.get("content", ""))
                source = search_service.sanitize_text(r.get("source", "web"))
                url = r.get("url", "")
                date = r.get("date", "")

                # Truncate content to prevent prompt bloat
                if len(content) > 300:
                    content = content[:300] + "..."

                line = f"  {i}. [{title}]"
                if date:
                    line += f" ({date})"
                line += f"\n     {content}"
                line += f"\n     Source: {source}"
                if url:
                    line += f" | {url}"
                lines.append(line)
            lines.append("")

        lines.append(f"[搜索时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}]" if is_zh else f"[Search time: {datetime.now().strftime('%Y-%m-%d %H:%M')}]")
        return "\n".join(lines)

    def clear_cache(self, symbol: Optional[str] = None):
        """Clear search cache (all or specific symbol)."""
        if symbol:
            keys_to_remove = [k for k in self._cache if k.startswith(symbol)]
            for k in keys_to_remove:
                del self._cache[k]
        else:
            self._cache.clear()


# Singleton
search_toolkit = SearchToolkit()
