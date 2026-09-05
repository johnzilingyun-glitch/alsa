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
from ..logging import get_logger

logger = get_logger(__name__)


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
        # 2026-09 扩展：原英文模板在中国服务器走 Iwencai 几乎召不回 A 股相关
        # 风险事件（如特朗普14420行政令这种地缘制裁类）。改为中文+覆盖监管处罚、
        # 立案调查、减持、解禁、商誉减值、美国制裁/关税/行政命令/UFLPA/FEOC 等
        # 触发词。保留少量英文关键词是给海外公司 (AAPL/NVO 等) 的兜底。
        #
        # 注意：模板不能太长 — Iwencai 用 BM25 风格的关键词匹配，79 字模板
        # 会把真正命中的文章 (如 14420号) 推到第 5-10 位。8-15 字短模板召回率
        # 显著更高，已实测验证 (2026-09-05)。
        "query": "{name} 美国 政策 制裁 管制",
        "max_results": 5,
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
    "business_query": {
        "query": "{name} {symbol} 主营业务收入构成 分产品营收占比 核心业务 毛利率",
        "max_results": 3,
        "label_zh": "主营业务与分产品营收占比",
        "label_en": "Business Query & Product Revenue Breakdown",
    },
    "announcement_search": {
        "query": "{name} 最近一周 公告",
        "max_results": 3,
        "label_zh": "最新公司公告",
        "label_en": "Company Announcements",
    },
    "research_report_search": {
        "query": "{name} 最近一周 研报 评级",
        "max_results": 3,
        "label_zh": "分析师深度研报",
        "label_en": "Analyst Research Reports",
    },
    "conference_search": {
        "query": "{name} {symbol} 业绩说明会 投资者交流 重大会议纪要",
        "max_results": 3,
        "label_zh": "投资者交流与重大会议",
        "label_en": "Conferences & Investor Relations",
    },
}

# Which search categories each expert role needs
ROLE_CATEGORY_MAP = {
    "Deep Research Specialist": [
        "latest_news", "financial_performance", "competitive_landscape",
        "management_insider", "industry_trends", "business_query", 
        "announcement_search", "research_report_search", "conference_search"
    ],
    "Technical Analyst": ["latest_news"],
    "Fundamental Analyst": [
        "financial_performance", "competitive_landscape", "analyst_ratings",
        "business_query", "announcement_search", "research_report_search", "conference_search"
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
    # 2026-09 扩展：增加 announcement_search / research_report_search 订阅，
    # 因为 14420 这种事件会先以公司公告 / 监管文件出现，光看 latest_news 抓不到。
    "Aggressive Risk Analyst": ["risk_factors", "latest_news", "announcement_search"],
    "Conservative Risk Analyst": ["risk_factors", "latest_news", "announcement_search", "research_report_search"],
    "Neutral Risk Analyst": ["risk_factors", "latest_news", "announcement_search"],
    "Risk Manager": ["risk_factors", "latest_news", "announcement_search", "research_report_search"],
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
    "Serenity Alpha Analyst": [
        "latest_news", "financial_performance", "business_query", 
        "announcement_search", "research_report_search", "conference_search", "industry_trends"
    ],
    "Chief Strategist": [
        "latest_news", "analyst_ratings", "risk_factors", "announcement_search", "research_report_search"
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
    "chip_concentration": {
        "query": "{name} {symbol} 筹码分布 筹码集中度 机构持股比例 公募持仓拥挤度",
        "max_results": 3,
        "label_zh": "筹码集中度与公募持仓",
        "label_en": "Chip Concentration & Mutual Fund Holdings",
    },
}

# A-share roles get extra categories
A_SHARE_ROLE_EXTRAS = {
    "Serenity Alpha Analyst": ["northbound_flow", "chip_concentration", "shareholder_reduction"],
    "Sentiment Analyst": ["northbound_flow", "dragon_tiger", "margin_trading"],
    "Deep Research Specialist": ["northbound_flow", "lockup_release", "shareholder_reduction", "chip_concentration"],
    "Bull Researcher": ["northbound_flow"],
    "Bear Researcher": ["dragon_tiger", "lockup_release", "shareholder_reduction", "chip_concentration"],
    "Risk Manager": ["lockup_release", "shareholder_reduction", "chip_concentration"],
    "Aggressive Risk Analyst": ["lockup_release", "shareholder_reduction", "chip_concentration"],
    "Conservative Risk Analyst": ["lockup_release", "shareholder_reduction", "chip_concentration"],
    "Neutral Risk Analyst": ["lockup_release", "shareholder_reduction", "chip_concentration"],
    "Chief Strategist": ["lockup_release", "shareholder_reduction", "chip_concentration"],
    "Technical Analyst": ["lockup_release", "shareholder_reduction", "chip_concentration"],
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

    # ────────── Category → channel dispatch (2026-09 新增) ──────────
    # 中文类目 (公告/研报/会议/主营) 直接打 Iwencai 对应 channel，避免通用
    # search() 的英文后缀稀释导致召回失败。其它类目走通用 search() 降级链。
    #
    # 多 channel 并行：实测 announcement channel 召回差，news channel 反而能
    # 召回政策类新闻 (如特朗普14420)。research_report 同理 — 部分公司回应会
    # 进 news，部分进 report。所以这两个类目走双 channel 去重。
    #
    # risk_factors 走三 channel (news + announcement + report)：
    # 2026-09-05 实测：API key news channel 在某些会话返回 401 quota_exhausted
    # 但 announcement + report 仍可用。多 channel 是必要冗余，不是性能优化。
    _DIRECT_IWENCAI_CATEGORIES = {
        "announcement_search": ["announcement", "news"],
        "research_report_search": ["report", "news"],
        "conference_search": ["news", "announcement"],
        "business_query": ["news", "report"],
        "risk_factors": ["news", "announcement", "report"],
        "latest_news": ["news", "announcement"],
    }

    # 2026-09 新增：风险类目需要双 query 召回 — 公司视角 (阳光电源 禁令)
    # 和行业视角 (光伏 变压器 美国) 各抓一轮，合并去重。因为地缘制裁类
    # 新闻可能只在其中一个视角被索引。
    _DUAL_QUERY_CATEGORIES = {"risk_factors"}

    # 公告/研报类目启用时间过滤 (服务端 publish_time)，硬剔除 30 天前
    # 数据。实测 (2026-09) 默认召回会混入 2023 年公告，严重稀释信号。
    _TIME_FILTERED_CATEGORIES = {"announcement_search", "research_report_search"}
    _TIME_FILTER_MAX_AGE_DAYS = 30

    async def _dispatch_category(
        self, cat_name: str, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Dispatch a category search to its best channel(s).

        For Chinese-language structured categories (announcement/report/conference/
        business/risk/news) on a China-server setup, hit Iwencai directly with the
        matching channel — bypasses generic search() which appends English suffixes
        and dilutes the Iwencai recall (root cause of missing 14420 EO on
        Sungrow 2026-09-05).

        Multi-channel categories (announcement_search / research_report_search)
        fan out concurrently and merge+dedup by URL+title to avoid duplicate hits.

        Dual-query categories (risk_factors) run two parallel queries — one
        with stock name for company-specific reactions, one with sector/industry
        keywords for policy-level events that may not be tagged to the stock.
        """
        channels = self._DIRECT_IWENCAI_CATEGORIES.get(cat_name)
        use_dual = cat_name in self._DUAL_QUERY_CATEGORIES

        if channels and os.getenv("IS_CHINA_SERVER", "true").lower() in ("true", "1", "yes"):
            if not os.getenv("IWENCAI_API_KEY"):
                return await search_service.search(query, max_results=max_results)
            from .data_providers.iwencai_news import _iwencai_search
            try:
                import asyncio as _aio

                # 构造 query 列表 — risk_factors 用双 query
                if use_dual:
                    # 第二个 query 用行业视角。实测下来 (2026-09-05) 写死的
                    # "光伏 美国 变压器 行政令 禁令" 在阳光电源场景召回最强文章
                    # ("SMM 快讯：美国紧急行政令：拟禁进口...")，但 risk_factors
                    # 也会用在非光伏股上 (寒武纪、海光)。这里允许用环境变量覆盖，
                    # 默认保持光伏行业视角。
                    alt_query = os.getenv(
                        "RISK_FACTORS_INDUSTRY_QUERY",
                        "光伏 美国 变压器 行政令 禁令",
                    )
                    queries = [query, alt_query]
                else:
                    queries = [query]

                # 并发打所有 (channel, query) 组合
                tasks = [
                    _iwencai_search(q, channel=ch)
                    for q in queries
                    for ch in channels
                ]
                responses = await _aio.gather(*tasks, return_exceptions=True)

                seen = set()
                merged: List[Dict[str, Any]] = []
                # 公告/研报类目启用时间过滤 (服务端 publish_time)
                time_filter = cat_name in self._TIME_FILTERED_CATEGORIES
                if time_filter:
                    import time as _t
                    cutoff_ts = _t.time() - self._TIME_FILTER_MAX_AGE_DAYS * 86400
                else:
                    cutoff_ts = 0
                for resp in responses:
                    if isinstance(resp, Exception) or not isinstance(resp, dict):
                        continue
                    for item in (resp.get("data") or [])[:max_results * 2]:
                        title = item.get("title", item.get("headline", ""))
                        url = item.get("url", item.get("link", ""))
                        # 时间过滤：剔除超过 _TIME_FILTER_MAX_AGE_DAYS 天的旧数据
                        if time_filter:
                            pt = item.get("publish_time") or 0
                            if pt and int(pt) < cutoff_ts:
                                continue
                        key = (str(title)[:30], str(url))
                        if key in seen or not title:
                            continue
                        seen.add(key)
                        content = item.get("content", item.get("summary", "")) or title
                        source = item.get("source", item.get("channel", "同花顺问财"))
                        merged.append({
                            "title": str(title)[:200],
                            "url": str(url) if url else "",
                            "content": str(content)[:500],
                            "source": f"Iwencai_{source}",
                            "publish_time": item.get("publish_time"),
                        })
                if merged:
                    return merged[:max_results]
            except Exception as e:
                logger.warning(
                    f"[SearchToolkit] direct iwencai({channels}) failed: {e}, "
                    f"falling back to search()"
                )
        return await search_service.search(query, max_results=max_results)

    async def batch_search(
        self,
        symbol: str,
        name: str,
        snapshot: Optional[Dict[str, Any]] = None,
        time_budget: Optional[float] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run all category searches at once for a given stock.
        Returns {category_name: [search_results]}.

        Results are cached for 10 minutes to avoid redundant searches
        within the same analysis job.

        Args:
            time_budget: 可选的类目时间预算(秒)。类别是顺序执行的，
                预算到期后不再发起新类目，返回已完成的部分结果而非
                整体丢弃；None 表示不限(旧行为)。调用方
                (discussion_service._background_search)用它在外层
                硬超时前交回部分结果。
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
            # 类目时间预算：到点后不再发起新类目，返回已完成部分。
            # 外层还有硬超时兜底预算到期时仍在途的最后一个类目。
            if time_budget is not None and (time.time() - search_start) > time_budget:
                logger.info(
                    "Time budget %ss reached, returning partial results: "
                    "%d/%d categories",
                    time_budget, len(results), len(all_categories),
                )
                break

            query = cat_config["query"].format(name=name, symbol=symbol)
            max_results = cat_config.get("max_results", 3)

            try:
                # 2026-09: 中文类目直接走 Iwencai 对应 channel，绕过通用 search()
                # 的英文查询后缀稀释。原因是：通用 search() 对 announcement/report
                # 召回很差，特朗普14420 这种事件就是因此漏掉的。
                cat_results = await self._dispatch_category(cat_name, query, max_results)
                if cat_results:
                    results[cat_name] = cat_results
                    print(f"  [SearchToolkit] {cat_name}: {len(cat_results)} results")
                else:
                    print(f"  [SearchToolkit] {cat_name}: no results")
                    # 2026-09: 区分"该类目无数据"和"该类目未找到" — 注入保守兜底
                    # 提示，让 LLM 在风险维度上不要因沉默而乐观。
                    results[cat_name] = [{
                        "title": "无最新相关数据 / No Recent Data",
                        "content": (
                            "系统已执行自动搜索，{cat_name}维度未发现近期数据。"
                            "在风险/合规/公告维度，建议默认采取保守判定，"
                            "不要因搜索无结果而推断为'无风险'。 "
                            "请直接判定为无或N/A。"
                        ).format(cat_name=cat_config.get("label_zh", cat_name)),
                        "source": "system",
                        "_missing": True,
                    }]
            except Exception as e:
                print(f"  [SearchToolkit] {cat_name} failed: {e}")
                results[cat_name] = [{"title": "获取超时或失败 / Fetch Failed", "content": f"系统自动获取过程中出现超时或失败，暂无对应数据。可视为暂无近期重大记录。", "source": "system"}]

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
        market_lower = (market or "us").lower().replace("-", "_")
        if market_lower == "a_share" and role in A_SHARE_ROLE_EXTRAS:
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
