import os
import json
import re
import ast
import asyncio
import markdown2
from datetime import datetime
from typing import List, Any, Dict, Optional
from .llm_gateway import llm_gateway, current_token_usage
from .signal_taxonomy import normalize_action
from .data_providers.a_stock_direct import _get_cn_risk_free_rate
from .valuation_config import (
    EQUITY_RISK_PREMIUM,
    DEFAULT_COST_OF_DEBT,
    CN_RISK_FREE_FALLBACK,
    US_RISK_FREE_DEFAULT,
    HK_RISK_FREE_DEFAULT,
    BETA_FLOOR,
    BETA_CEILING,
    WACC_FLOOR_MARGIN,
    WACC_FLOOR_ABS,
    MIN_WACC_G_SPREAD,
)
from ..logging import get_logger

logger = get_logger(__name__)

# Report UI data keeps the BUY/SELL/HOLD display convention; the taxonomy's
# watch degrades to HOLD for display (same behavior as the previous inline
# mapping, which also folded WATCH/NEUTRAL into HOLD).
_ACTION_DISPLAY = {"buy": "BUY", "sell": "SELL", "hold": "HOLD", "watch": "HOLD"}

# ── DCF sanity bounds (β / WACC / g guardrails for _compute_valuation) ──
# 单一定义点位于 valuation_config.py：provider 侧 β 护栏/WACC 估算、本渲染层
# DCF、computation_tools 校验边界四方同源（模块属性别名保留，测试仍可
# patch rgs._VALUATION_*）。
_VALUATION_BETA_FLOOR = BETA_FLOOR                # β 合理下限（CAPM 输入防护）
_VALUATION_BETA_CEILING = BETA_CEILING           # β 合理上限
_VALUATION_WACC_FLOOR_MARGIN = WACC_FLOOR_MARGIN  # WACC 下限 = max(Rf + 2%, 5%)
_VALUATION_WACC_FLOOR_ABS = WACC_FLOOR_ABS
_VALUATION_MIN_SPREAD = MIN_WACC_G_SPREAD        # WACC − g 最小利差，不足则拒绝 DCF


class ReportSchemaValidationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(f"LLM report schema validation failed: {reason}")
        self.reason = reason


class ReportGeneratorService:
    def generate_report(self, run, outputs: List) -> str:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.generate_html_report_async({
            "symbol": run.symbol,
            "market": run.market,
            "discussion": [{"role": art.artifact_type.replace("_output", "").replace("_", " ").title(), "content": art.content} for art in outputs],
            "snapshot": run.market_snapshot
        }, f"{run.symbol}_report.html"))

    def generate_html_report(self, result: dict, output_path: str) -> str:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.generate_html_report_async(result, output_path))

    async def generate_html_report_async(self, result: dict, output_path: str, model: str = None, deepseek_api_key: str = None, gemini_api_key: str = None, openrouter_api_key: str = None) -> str:
        stock_info = result.get("stockInfo", {})
        symbol = result.get("symbol") or stock_info.get("symbol", "UNKNOWN")
        market = result.get("market") or stock_info.get("market", "US-Share")
        discussion_msgs = result.get("discussion", [])
        snapshot = result.get("snapshot") or {}
        
        # Resolve model: explicit param > env var default
        if not model:
            provider = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek").lower()
            model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro") if provider == "deepseek" else os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
        
        # Clean discussion content: strip LLM thinking prefixes, then neutralize any
        # "own knowledge / training data" provenance labels so fabricated-source financial
        # claims are never presented as fact downstream.
        _fab_hit = {"hit": False}
        def _clean_content(raw):
            stripped = self._strip_thinking_prefix(raw)
            redacted, found = self._redact_fabricated_provenance(stripped)
            if found:
                _fab_hit["hit"] = True
            return redacted
        cleaned_msgs = [{"role": m.get("role", "分析师"), "content": _clean_content(m.get("content", "")), "model": m.get("model", model)} for m in discussion_msgs]
        fabrication_detected = _fab_hit["hit"]
        full_discussion = "\n".join([f"[{m['role']}]: {m['content']}" for m in cleaned_msgs])
        
        # Initialize token tracking for the report generation phase
        report_usage = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
        token_ctx = current_token_usage.set(report_usage)
        
        try:
            # UI Data Expert Pass - REFINED CONTENT (RESTORING RAW LOGS)
            ui_data = await self._run_ui_data_expert(symbol, market, snapshot, full_discussion, model=model, deepseek_api_key=deepseek_api_key, gemini_api_key=gemini_api_key, openrouter_api_key=openrouter_api_key)

            # If ui_data is missing/empty (LLM API error or JSON parse failure), attempt fallback extraction from discussion
            if not ui_data or not isinstance(ui_data, dict):
                fallback_ui = self._build_fallback_ui_data(symbol, cleaned_msgs, snapshot)
                if fallback_ui:
                    ui_data = fallback_ui

            # Run validation & backfilling on ui_data
            if ui_data and isinstance(ui_data, dict):
                self._validate_and_backfill_ui_data(ui_data, cleaned_msgs, snapshot)

            # If UI data is STILL missing or low quality, raise schema validation error
            if not ui_data or self._is_low_quality_ui_data(ui_data):
                raise ReportSchemaValidationError(self._describe_ui_data_schema_failure(ui_data))

            # Backstop: if any figure was sourced from the model's own knowledge, downgrade
            # data completeness and surface an integrity warning instead of presenting it as fact.
            if fabrication_detected:
                _dc = ui_data.get("data_completeness") or {}
                if isinstance(_dc, dict):
                    try:
                        _dc["score"] = min(int(_dc.get("score", 100)), 70)
                    except (TypeError, ValueError):
                        _dc["score"] = 70
                    _impact = _dc.get("impact", "")
                    _dc["impact"] = (_impact + " ⚠️ 检测到模型曾以'自有知识库/训练数据'标注来源，已按数据缺失处理；财务数值仅采信 API 或具名工具来源。").strip()
                    ui_data["data_completeness"] = _dc
                ui_data["data_integrity_warning"] = (
                    "本报告部分数据曾被模型以「自有知识库 / 训练数据」标注来源，系统已强制按数据缺失处理。"
                    "所有财务数值应仅以 API 或具名工具提供的实时来源为准。"
                )
            
            # Backfill empty upside/downside from discussion text
            if not ui_data.get("upside") or not ui_data.get("downside"):
                extracted = self._extract_thesis_from_discussion(cleaned_msgs)
                if not ui_data.get("upside") and extracted.get("upside"):
                    ui_data["upside"] = extracted["upside"]
                if not ui_data.get("downside") and extracted.get("downside"):
                    ui_data["downside"] = extracted["downside"]
            
            quote = snapshot.get("quote", {})
            currency = quote.get("currency", "USD" if "US" in market else "CNY")
            fundamentals = self._compile_fundamentals(snapshot, currency, ui_data, market=market)
            
            # Parallelize normalization for performance — fallback to markdown if LLM fails
            try:
                normalized_contents = await asyncio.gather(*[
                    self._normalize_log_style(m["content"], model=model, deepseek_api_key=deepseek_api_key, gemini_api_key=gemini_api_key, openrouter_api_key=openrouter_api_key) for m in cleaned_msgs
                ])
                # Check if all normalizations returned empty/error
                if all(not c or c.strip() == "" for c in normalized_contents):
                    raise ValueError("All normalizations returned empty")
            except Exception:
                # Fallback: convert raw markdown to HTML without LLM
                normalized_contents = [self._markdown_to_html_fallback(m["content"]) for m in cleaned_msgs]
        finally:
            current_token_usage.reset(token_ctx)
        
        data = {
            "info": {
                "name": quote.get("name", symbol),
                "symbol": symbol,
                "market": market,
                "price": quote.get("price", "N/A"),
                "changePercent": quote.get("changePercent", 0),
                "currency": currency,
                "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M")
            },
            "fund": fundamentals,
            "verdict": ui_data.get("verdict", ""),
            "action_stance": ui_data.get("action_stance", ""),
            "tagline": ui_data.get("tagline", ""),
            "investment_thesis": ui_data.get("investment_thesis", ""),
            "factor_profile": ui_data.get("factor_profile", {}),
            "consensus_vs_non_consensus": ui_data.get("consensus_vs_non_consensus", {}),
            "the_call": ui_data.get("the_call", ""),
            "catalyst_calendar": ui_data.get("catalyst_calendar", []),
            "stock_archetype": ui_data.get("stock_archetype", ""),
            "wacc_breakdown": ui_data.get("wacc_breakdown", {}),
            "kill_switch": ui_data.get("kill_switch", {}),
            "market_wind_control": ui_data.get("market_wind_control", {}),
            "trading_discipline": ui_data.get("trading_discipline", {}),
            "data_completeness": ui_data.get("data_completeness", {"score": 100, "missing": [], "impact": ""}),
            "data_integrity_warning": ui_data.get("data_integrity_warning", ""),
            "peer_comparison": ui_data.get("peer_comparison", []),
            "summary": ui_data.get("summary", "总结提炼中..."),
            "moat_summary": ui_data.get("moat_summary", ""),
            "moat_points": ui_data.get("moat_points") or [],
            "macro_summary": ui_data.get("macro_summary", ""),
            "macro_points": ui_data.get("macro_points") or [],
            "trading_plan": ui_data.get("trading_plan", "交易计划生成中..."),
            "trading_steps": ui_data.get("trading_steps") or [],
            "risks_points": ui_data.get("risks_points") or [],
            "key_opps": ui_data.get("upside") or [],
            "key_risks": ui_data.get("downside") or [],
            "scenarios": ui_data.get("scenarios") or self._default_scenarios(),
            "score": ui_data.get("score", 75),
            "recommendation": ui_data.get("recommendation", "WATCH"),
            "discussion": [
                {"role": m["role"], "content": content, "model": m.get("model", model)}
                for m, content in zip(cleaned_msgs, normalized_contents)
            ],
            "northbound": snapshot.get("northbound") or {},
            "baijiu_price": snapshot.get("baijiu_price") or {},
            "snapshot": snapshot,
        }

        # Merge snapshot peer_comparison (real fetched data) with LLM peers.
        # Real data takes precedence; LLM peers are kept only when their
        # symbol does not overlap with a real peer.
        _snap_peers = snapshot.get("peer_comparison") or []
        _llm_peers = data.get("peer_comparison") or []
        if _snap_peers and isinstance(_snap_peers, list):
            _llm_peers_map = {}
            for p in _llm_peers:
                if isinstance(p, dict) and p.get("symbol"):
                    _llm_peers_map[p["symbol"]] = p

            _merged = []
            _real_symbols = set()
            for rp in _snap_peers:
                if not isinstance(rp, dict):
                    continue
                sym = rp.get("symbol")
                if not sym:
                    _merged.append(rp)
                    continue
                _real_symbols.add(sym)
                
                llp = _llm_peers_map.get(sym)
                if llp:
                    for k in ["vs_target", "rationale", "evaluation"]:
                        if k in llp and llp[k]:
                            rp["vs_target"] = llp[k]
                            break
                _merged.append(rp)

            for p in _llm_peers:
                if isinstance(p, dict) and p.get("symbol") not in _real_symbols:
                    _merged.append(p)
            data["peer_comparison"] = _merged

        # Surface the COMPUTED data quality (from the snapshot pipeline), not just the
        # LLM-estimated one, so the report honestly reflects real data completeness.
        _dq = snapshot.get("data_quality") or {}
        if isinstance(_dq, dict):
            _dq_warnings = _dq.get("warnings") or []
            _dq_missing = [
                (w.get("message") or w.get("code") or "")
                for w in _dq_warnings if isinstance(w, dict)
            ]
            data["data_completeness"] = {
                "score": int(round((_dq.get("score") or 0) * 100)),
                "missing": _dq_missing,
                "impact": "; ".join(_dq_missing) or "核心数据完整度良好",
            }
            if _dq_warnings:
                data["data_integrity_warning"] = "⚠ 数据完整度提示: " + "; ".join(
                    f"[{w.get('severity', '')}] {w.get('message', '')}" for w in _dq_warnings if isinstance(w, dict)
                )

        # Compute deterministic factor scores from snapshot fundamentals
        data["factor_scores"] = self._compute_factor_scores(snapshot)

        # Compute WACC/DCF valuation from snapshot; only override the LLM-derived
        # wacc_breakdown if the computation produces a valid WACC value.
        # 综合目标价（scenarios 概率加权，与渲染层期望价同口径）供 DCF 偏离度守卫使用
        valuation = self._compute_valuation(snapshot, {
            "price": quote.get("price"),
            "market": market,
            "symbol": symbol,
            "currency": currency,
            "ref_target_price": self._scenario_expected_price(data.get("scenarios")),
        })
        if valuation and valuation.get("wacc"):
            data["wacc_breakdown"] = valuation
            # Backfill computable valuation metrics into the fundamentals table
            # (β and WACC are derivable even when the provider returned neither).
            if fundamentals.get("贝塔系数 (β)") == "N/A" and valuation.get("beta") is not None:
                _beta = valuation["beta"]
                # _compute_valuation returns display-formatted strings ("1.10"),
                # so round only when numeric — round(str) raises TypeError.
                fundamentals["贝塔系数 (β)"] = f"{round(_beta, 2)}" if isinstance(_beta, (int, float)) else str(_beta)
            if fundamentals.get("WACC (估算)") == "N/A" and valuation.get("wacc") is not None:
                fundamentals["WACC (估算)"] = str(valuation["wacc"])  # already formatted like '7.77%'

        html = self._render_html(data)
        
        # Inject precise token usage metadata as an HTML comment
        usage_json = json.dumps(report_usage)
        html += f"\n<!-- TOKEN_USAGE: {usage_json} -->\n"
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return os.path.abspath(output_path)

    async def _run_ui_data_expert(self, symbol: str, market: str, snapshot: dict, discussion: str, model: str = None, deepseek_api_key: str = None, gemini_api_key: str = None, openrouter_api_key: str = None) -> dict:
        prompt = f"""# ROLE
You are the ALSA Report Structuring Engine — a specialized system that transforms raw multi-expert stock analysis discussions into structured JSON for UI rendering.

# INPUT
- Stock: {symbol} ({market})
- Below you will receive the full expert discussion transcript.

# TASK
Extract ALL substantive analytical conclusions from the discussion and map them into the JSON schema below. You are a **data extraction pipeline**, not an analyst — do NOT generate new analysis, only reorganize what the experts already said.

# CRITICAL RULES (MUST FOLLOW)

## Rule 1: Filter Noise
The discussion may contain LLM artifacts like:
- "Now I have comprehensive data. Let me compile..."
- "Based on my analysis, here are my key findings:"
- "OK, let me write the full JSON output now."
- "Actually, let me reconsider..."
- Raw calculations, intermediate reasoning, self-talk

**SKIP ALL OF THESE.** Extract only the final analytical conclusions, not the thinking process.

## Rule 2: Zero Tolerance for Empty Critical Fields
These 5 fields MUST NEVER be null/empty if the discussion contains ANY relevant analysis:
1. **verdict** — If experts gave ANY conclusion, synthesize it into ≤20 words
2. **action_stance** — If ANY trading recommendation exists, extract it
3. **investment_thesis** — If ANY core logic/narrative is stated, capture it
4. **tagline** — Synthesize the stock name + key thesis into a hook
5. **recommendation** — Must be BUY, HOLD, or SELL (derive from discussion tone if not explicit)

If you cannot find these in the text, SYNTHESIZE from the overall discussion sentiment. Never return null for these 5 fields.

## Rule 3: Output Format
- Output ONLY a single valid JSON object. No markdown, no explanation, no commentary.
- Use Chinese for all text values (matching the discussion language).
- Numbers: use plain integers/floats, NOT strings (except when unit-attached like "48.18亿元").
- If a non-critical field's data is truly absent from the discussion, use null.

## Rule 4: Quality Bar
Each extracted field should meet this bar:
- **verdict**: Reads like a Bloomberg terminal flash (concise, decisive, actionable)
- **tagline**: Reads like a sell-side report title (compelling, specific)
- **scenarios**: Must have realistic probability splits summing to 100%, with specific price targets if discussed
- **data_completeness**: Honestly assess what data the experts had vs. what was missing

## Rule 5: Narrative Fields MUST Be Substantive
The fields `summary`, `moat_summary`, `macro_summary`, and `trading_plan` are **PARAGRAPH-LEVEL narrative fields** displayed prominently in the report. They MUST:
- Contain at least 3-5 complete sentences each (NOT single-line labels)
- Extract specific analytical content from the discussion, not generic placeholders
- Include concrete data points, mechanisms, or causal logic mentioned by experts
- NEVER be truncated with "..." or returned as single-phrase summaries like "稀缺的采矿权资源壁垒..."
- If the discussion truly lacks content for a narrative field, synthesize from nearby related analysis rather than returning a 5-word phrase

# JSON SCHEMA

```json
{{
  "verdict": "≤20字一句话定调，如：低估值铝业龙头，大股东减持压制短期，等Q2验证",
  "action_stance": "持仓建议+操作指引，如：当前持仓HOLD，新仓等待13元支撑确认后试探建仓",
  "tagline": "报告标题钩子，如：天山铝业：全产业链成本优势vs大股东套现，周期股的攻守博弈",
  "investment_thesis": "一句话核心逻辑，如：铝价高位+产能天花板刚性约束，但大股东减持构成估值天花板",
  "recommendation": "BUY|HOLD|SELL",
  "score": 75,
  "factor_profile": {{
    "size": "大盘|中盘|小盘",
    "style": "成长|价值|周期|红利",
    "volatility": "高Beta|低波动|中等",
    "expected_return": "收益预期特征描述"
  }},
  "consensus_vs_non_consensus": {{
    "market_consensus": "市场已price-in的共识观点",
    "our_alpha": "我们看到的预期差/非共识观点"
  }},
  "the_call": "一句话最终操作指令",
  "stock_archetype": "Cyclical|Growth|Dividend|Consumer/Moat|Financial|Biotech",
  "catalyst_calendar": [
    {{"event": "事件描述", "date": "时间节点", "impact_logic": "影响逻辑"}}
  ],
  "wacc_breakdown": {{
    "rf": "无风险利率", "beta": "贝塔系数", "erp": "股权风险溢价",
    "kd": "债务成本", "tc": "所得税率", "d_v": "负债占比", "e_v": "权益占比",
    "wacc": "加权平均资本成本", "source": "数据来源", "sensitivity": "敏感性分析"
  }},
  "kill_switch": {{
    "condition": "防伪红线条件(基本面+技术面双维度)",
    "status": "SAFE|TRIGGERED"
  }},
  "market_wind_control": {{
    "lockup_date": "限售股解禁信息",
    "lockup_impact": "解禁冲击评估",
    "reduction_plan": "减持计划/进度",
    "crowding_level": "机构持仓拥挤度"
  }},
  "trading_discipline": {{
    "left_side_condition": "左侧建仓条件",
    "right_side_trigger": "右侧买入触发点",
    "max_drawdown_limit": "最大回撤熔断线(如-8%)",
    "thesis_invalidation_trigger": "逻辑证伪退出条件"
  }},
  "data_completeness": {{
    "score": 0-100,
    "missing": ["缺失数据项1", "缺失数据项2"],
    "impact": "缺失数据对结论的影响"
  }},
  "peer_comparison": [
    {{"name": "公司名", "symbol": "代码", "pe": 15.2, "pb": 3.1, "roe": 18.5, "margin": 22.3, "marketCap": "3200亿", "vs_target": "对比结论"}}
  ],
  "summary": "2-3句话的执行摘要，总结整体投资逻辑和核心结论",
  "moat_summary": "至少3-5句话的基本面护城河深度解析段落，包含竞争壁垒、行业地位、资源禀赋、定价权等具体分析",
  "moat_points": ["护城河要素1", "护城河要素2"],
  "macro_summary": "至少3-5句话的宏观环境与资金技术面剖析段落，包含行业供需格局、政策环境、资金流向、技术形态等具体分析",
  "macro_points": ["宏观要素1", "宏观要素2"],
  "trading_plan": "至少3-5句话的交易策略总述段落，包含整体操作思路、仓位管理原则、风控止损框架",
  "trading_steps": [
    {{"level": "第一层", "price": "价格", "weight": "仓位", "logic": "逻辑"}}
  ],
  "risks_points": ["风险1", "风险2"],
  "upside": ["看涨驱动1", "看涨驱动2"],
  "downside": ["看跌风险1", "看跌风险2"],
  "scenarios": [
    {{"case": "Bull", "probability": 30, "targetPrice": "目标价", "logic": "驱动逻辑"}},
    {{"case": "Base", "probability": 50, "targetPrice": "目标价", "logic": "驱动逻辑"}},
    {{"case": "Bear", "probability": 20, "targetPrice": "目标价", "logic": "驱动逻辑"}}
  ],
  "net_profit": "最近净利润(如48.18亿元)",
  "net_profit_deduct": "扣非净利润",
  "revenue_qoq": "营收环比增长",
  "net_profit_yoy": "净利润同比增长",
  "net_profit_qoq": "净利润环比增长",
  "net_profit_deduct_yoy": "扣非净利润同比",
  "net_profit_deduct_qoq": "扣非净利润环比",
  "capex": "资本开支",
  "pe_percentile": "PE历史百分位",
  "asset_turnover": "总资产周转率",
  "inventory_turnover": "存货周转率"
}}
```

# BAD OUTPUT EXAMPLES (DO NOT DO THIS)
❌ `"verdict": ""` — Empty critical field
❌ `"verdict": "Now I have comprehensive data"` — LLM thinking text leaked
❌ `"investment_thesis": "Based on my analysis..."` — Process text, not conclusion
❌ `"tagline": "002532 投资分析报告"` — Generic, no insight
❌ `"scenarios": [{{"probability": "30%"}}]` — String with %, must be integer 30
❌ `"net_profit": "N/A"` — Use null, not "N/A"

# GOOD OUTPUT EXAMPLES
✅ `"verdict": "铝价高位叠加产能天花板，但大股东48亿套现压制估值扩张"` 
✅ `"tagline": "天山铝业：全产业链一体化铝业龙头的周期博弈"` 
✅ `"investment_thesis": "电解铝产能4500万吨刚性约束下的供需错配逻辑"` 

Now extract from the following discussion:
"""
        # Append search context if available to help fill missing fundamental data
        search_ctx = snapshot.get("financials", {}).get("searchContext", "")
        if search_ctx:
            prompt += f"\n\nFINANCIAL SEARCH CONTEXT (Use this to extract missing financial metrics):\n{search_ctx}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use passed model or fall back to env var default
                if not model:
                    provider = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek").lower()
                    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro") if provider == "deepseek" else os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

                # Preprocess discussion: strip markdown formatting noise for cleaner extraction
                discussion_clean = self._preprocess_discussion_for_extraction(discussion)

                # Smart truncation: take beginning (context) + end (conclusions) for extremely long discussions
                # Modern models (Gemini/DeepSeek) have large context windows, so we raise the limit to 300,000 characters (approx 150k tokens)
                if len(discussion_clean) > 300000:
                    # First 100000 chars: stock overview, key data from early experts
                    # Last 200000 chars: final conclusions, recommendations from later experts
                    discussion_safe = discussion_clean[:100000] + "\n\n... [中间内容已省略] ...\n\n" + discussion_clean[-200000:]
                else:
                    discussion_safe = discussion_clean

                # Add retry-specific instruction to prevent lazy copying
                retry_hints = ""
                if attempt > 0:
                    retry_hints = (
                        "\n\n⚠️ PREVIOUS ATTEMPT FAILED. You MUST output ONLY a valid JSON object. "
                        "DO NOT copy the discussion text into any field. "
                        "Each text field must be a SHORT summary (≤50 words), not the full discussion."
                    )

                res = await llm_gateway.generate_content(
                    prompt + f"\n\nEXPERT DISCUSSION (Trailing context):\n{discussion_safe}{retry_hints}",
                    model=model, deepseek_api_key=deepseek_api_key, gemini_api_key=gemini_api_key, openrouter_api_key=openrouter_api_key
                )

                # Robust JSON extraction:
                # 1) Strip DeepSeek thinking blocks (<think>...</think>) — the reasoning
                #    prefix is NOT part of the structured output and usually contains
                #    '{' fragments (the model plans the JSON in its thinking), which
                #    previously hijacked the first-brace scan and broke parsing.
                cleaned = re.sub(r'<think>.*?</think>', '', res, flags=re.DOTALL)
                cleaned = re.sub(r'```(?:json)?\s*\n?', '', cleaned)
                cleaned = re.sub(r'\n?```\s*$', '', cleaned)
                cleaned = cleaned.strip()

                # 2) Try each '{' position and keep the MOST COMPLETE object (most
                #    keys). Prose may still contain small JSON-like fragments such as
                #    {"x": 1} before the real document; the full schema object wins.
                json_str = ""
                best_candidate = ""
                best_key_count = -1
                for brace_pos in (m.start() for m in re.finditer(r'\{', cleaned)):
                    candidate = self._extract_balanced_json(cleaned[brace_pos:])
                    if not candidate:
                        continue
                    try:
                        key_count = len(json.loads(candidate))
                    except (json.JSONDecodeError, TypeError):
                        key_count = 0
                    if key_count > best_key_count:
                        best_key_count = key_count
                        best_candidate = candidate
                    if key_count >= 15:
                        break  # schema-sized object found, stop scanning
                json_str = best_candidate
                if not json_str:
                    # Regex fallback: find first {...} block
                    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                    if match:
                        json_str = match.group(0)

                if json_str:
                    # Robust JSON parsing with repair for common LLM output issues
                    try:
                        result = json.loads(json_str)
                        if isinstance(result, dict) and result:
                            return result
                    except json.JSONDecodeError:
                        # Fix common LLM JSON issues: trailing commas
                        fixed = re.sub(r',(\s*[}\]])', r'\1', json_str)
                        try:
                            result = json.loads(fixed)
                            if isinstance(result, dict) and result:
                                return result
                        except json.JSONDecodeError:
                            # Try ast.literal_eval if LLM returned python dict format
                            try:
                                result = ast.literal_eval(json_str)
                                if isinstance(result, dict) and result:
                                    return result
                            except Exception:
                                pass

                print(f"UI Data Expert Pass Attempt {attempt+1} Failed to parse JSON. Result: {res[:100]}...")
                last_exception = ValueError(f"Failed to parse JSON. Result preview: {res[:100]}...")
            except Exception as e:
                print(f"UI Data Expert Pass Attempt {attempt+1} Failed Exception: {e}")
                last_exception = e

            await asyncio.sleep(2) # short backoff before retry

        print("UI Data Expert Pass exhausted all retries. Falling back...")
        return {}

    def _preprocess_discussion_for_extraction(self, discussion: str) -> str:
        """Clean up discussion text to improve LLM extraction quality.

        Removes markdown formatting noise that confuses JSON extraction:
        - HTML tags (from rendered markdown)
        - Excessive whitespace / blank lines
        - Table pipe characters that break JSON parsing
        - Code block markers
        """
        if not discussion:
            return discussion

        text = discussion

        # Remove HTML tags (from rendered markdown in discussion)
        text = re.sub(r'<[^>]+>', '', text)

        # Remove markdown code block markers
        text = re.sub(r'```(?:json|python|py)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*', '', text)

        # Remove inline code backticks
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Collapse excessive blank lines (3+ → 2)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove trailing whitespace per line
        text = '\n'.join(line.rstrip() for line in text.split('\n'))

        return text.strip()

    # --- Thinking prefix patterns common in DeepSeek/LLM outputs ---
    _THINKING_PREFIXES = [
        # English patterns (sentence-bound or line-bound)
        r"^Now I (?:have|need|will|should|can|am going)[^.\n]*(?:\.|\n+)",
        r"^(?:OK|Okay|Alright|Right)[,.]?\s*(?:let me|I'll|I will|I need|now)[^.\n]*(?:\.|\n+)",
        r"^Let me (?:think|consider|analyze|review|proceed|compile|write|start|check|reconsider|also consider)[^.\n]*(?:\.|\n+)",
        r"^Based on (?:my|the|this) (?:analysis|review|data|findings|research)[^.\n]*(?:\.|\n+)",
        r"^I (?:have|need to|should|will|can|am going to) (?:now|also|first|proceed|comprehensive)[^.\n]*(?:\.|\n+)",
        r"^Actually,? let me[^.\n]*(?:\.|\n+)",
        r"^(?:Here are|The following|Below)[^.\n]*(?:findings|results|analysis|key)[^.\n]*(?::|\n+)",
        
        # Chinese patterns (sentence-bound or line-bound)
        r"^(?:现在我已|我已|现在我)[^。\n]*(?:掌握|获取|获取到|搜集到|已掌握|完成|拥有)[^。\n]*(?:。|\n+)",
        r"^(?:好的|好的，|收到|收到，|首先)[^。\n]*(?:我将|让我|开始|进行|分析)[^。\n]*(?:。|\n+)",
        r"^(?:让我|让我先|先让我|现在让我)[^。\n]*(?:分析|思考|陈述|总结|写出|开始|进行|输出|撰写|整理)[^。\n]*(?:。|\n+)",
        r"^(?:根据|基于)[^。\n]*(?:分析|讨论|研究|数据|讨论结果)[^。\n]*(?:。|\n+)",
        r"^(?:以下是|下面是|根据我的|结合上述|基于上述|综上所述)[^。\n]*(?:分析|报告|结论|裁决|意见|报告内容|综合|最终)[^。\n]*(?:。|：|:\n+|\n+)",
        r"^(?:数据收集|数据获取|数据采集|工具调用|分析准备|所有核心计算|所有核心计算工具|计算工具)[^。\n]*(?:完成|完毕|结束|就绪|调用完成|已完成)[^。\n]*(?:。|\n+)",
        r"^(?:现在让我|让我|我将|接下来我)[^。\n]*(?:分析|思考|撰写|陈述|总结|写出|输出|整理|编写)[^。\n]*(?:。|\n+)",
    ]

    def _strip_thinking_prefix(self, content: Any) -> Any:
        """Remove LLM thinking/reasoning prefixes from discussion content.
        These are visible model outputs that read like internal monologue rather than analysis."""
        if not content:
            return content
        if not isinstance(content, str):
            if isinstance(content, list):
                content = "\n".join([str(x) for x in content])
            else:
                return content
        stripped = content.strip()

        # Remove DeepSeek thinking blocks (<think>...</think>) — the model's hidden
        # reasoning is prepended to the visible answer when thinking mode is enabled.
        if "<think>" in stripped:
            stripped = re.sub(r'<think>.*?</think>', '', stripped, flags=re.DOTALL).strip()

        # Iteratively strip thinking prefixes (model may chain multiple thinking sentences)
        max_passes = 10
        for _ in range(max_passes):
            changed = False
            for pattern in self._THINKING_PREFIXES:
                new = re.sub(pattern, '', stripped, count=1, flags=re.IGNORECASE | re.MULTILINE)
                if new != stripped:
                    stripped = new.lstrip()
                    changed = True
                    break
            if not changed:
                break

        # If stripping removed everything or too much (>90% removed), return original
        if not stripped or (len(stripped) < 50 and len(stripped) < len(content.strip()) * 0.1):
            return content.strip()
        return stripped

    @staticmethod
    def _preprocess_chinese_bold(text: str) -> str:
        """Normalize '**bold**' markers BEFORE markdown2 conversion.

        markdown2's smart emphasis pairs '**' incorrectly around CJK text —
        '**+104%**，其中**美国…**' becomes '<strong>，其中</strong>' with the
        outer markers left dangling, producing nested garbage in the report.
        Replace bold markers with unambiguous placeholder tokens first, then
        restore them to <strong> after conversion.
        """
        if not text or '**' not in text:
            return text
        return re.sub(r'\*\*([^*\n]+?)\*\*', '◖STR◗\\1◖/STR◗', text)

    @staticmethod
    def _postprocess_markdown(html_out: str) -> str:
        """Post-process markdown2 output for LLM-generated Chinese content.

        - markdown2's smart emphasis uses \w word boundaries, which do NOT match
          CJK characters — so '**中文加粗**' adjacent to Chinese stays unrendered
          and leaks literal '**' into the report. Convert those leftovers, while
          protecting already-generated HTML tags from being re-matched.
        - Strip <structured_data>...</structured_data> JSON blocks (LLM artifacts),
          matching both raw and safe_mode-escaped forms.
        """
        if not html_out:
            return html_out
        if '◖STR◗' in html_out:
            html_out = html_out.replace('◖STR◗', '<strong>').replace('◖/STR◗', '</strong>')
        if 'structured' in html_out and ('<structured' in html_out or '&lt;structured' in html_out):
            html_out = re.sub(
                r'&?lt;structured[\\_]?data&gt;.*?&?lt;/structured[\\_]?data&gt;',
                '<em>[结构化数据已折叠]</em>',
                html_out, flags=re.DOTALL | re.IGNORECASE,
            )
        if '**' in html_out:
            # Protect existing HTML tags so '**' only matches literal text
            tags = []
            def _save(m):
                tags.append(m.group(0))
                return f'__MDTAG{len(tags) - 1}__'
            protected = re.sub(r'<[^>]+>', _save, html_out)
            protected = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', protected)
            for i, t in enumerate(tags):
                protected = protected.replace(f'__MDTAG{i}__', t)
            html_out = protected
        return html_out

    def _looks_like_markdown_dump(self, val: Any) -> bool:
        """Detect raw markdown documents (headers/tables) leaked into a field.

        Structured fields must be short prose; a value containing markdown
        headings or table pipes spanning multiple lines is a document dump
        (e.g. the model copied the whole expert report into a field)."""
        if not val or not isinstance(val, str):
            return False
        stripped = val.strip()
        # Markdown heading marker (e.g. '# 🔬 昭衍新药…' or '06127: # 🔬 …') is
        # never a valid structured-field value
        if re.search(r'#{1,6}\s', stripped):
            return True
        lines = [l.strip() for l in stripped.replace('\\n', '\n').split('\n') if l.strip()]
        if len(lines) < 2:
            # A single table row (e.g. '| 风险项 | 说明 |') is still a dump for
            # display purposes — it renders as raw pipes in plain-text slots.
            if lines and lines[0].startswith('|') and lines[0].endswith('|'):
                return True
            return False
        header_lines = sum(1 for l in lines if re.match(r'^#{1,6}\s', l))
        table_lines = sum(1 for l in lines if '|' in l)
        separator_lines = sum(1 for l in lines if re.match(r'^-{3,}$', l))
        return (header_lines >= 1 and len(lines) >= 3) or table_lines >= 2 or (separator_lines >= 1 and len(lines) >= 3)

    def _render_prose(self, value: Any, max_len: int = 300) -> str:
        """Render an LLM-derived display string as clean plain text.

        Defense-in-depth at render time: if a value is a raw markdown document
        (e.g. a whole expert report dumped into a field), reduce it to plain
        prose; otherwise strip only emphasis/backtick markers that would display
        verbatim in plain-text interpolation spots."""
        if not value or not isinstance(value, str):
            return str(value) if value is not None else ""
        v = value.strip()
        if self._looks_like_markdown_dump(v):
            return self._sanitize_markdown_field(v, max_len=max_len)
        if '|' in v:
            # Table-shaped fragments (>=2 pipes or a leading pipe) are stripped
            # entirely; a single stray pipe is converted to a safe separator.
            if v.count('|') >= 2 or v.lstrip().startswith('|'):
                return self._sanitize_markdown_field(v, max_len=max_len)
            v = v.replace('|', '、')
        if '**' in v or '`' in v or v[:1] in (">", "-", "*", "•"):
            v = re.sub(r'\*\*([^*]+)\*\*', r'\1', v)
            v = re.sub(r'`([^`]+)`', r'\1', v)
            v = re.sub(r'^>\s?', '', v)
            v = re.sub(r'^[-*•▪◆]\s+', '', v)
            if '**' in v or v[:1] == '*':
                v = v.replace('*', '').strip()
        if len(v) > max_len:
            v = v[:max_len] + "..."
        return v

    def _sanitize_markdown_field(self, text: str, max_len: int = 500) -> str:
        """Reduce raw markdown (full expert reports) to plain prose for structured fields.

        When expert outputs leak into structured fields (e.g. the fallback path), raw
        '#', '|', '**' markers would be HTML-escaped and displayed verbatim in the
        rendered report. This strips document formatting and keeps only substantive text.
        """
        if not text or not isinstance(text, str):
            return text
        lines = text.replace('\\n', '\n').split('\n')
        out_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Drop markdown headers entirely (titles/section headers are noise here)
            if re.match(r'^#{1,6}\s', stripped):
                continue
            # Remove heading markers that appear mid-line (e.g. '06127: # 🔬 标题')
            stripped = re.sub(r'#{1,6}\s+', '', stripped)
            # Drop separators, table rows, and code fences
            if re.match(r'^-{3,}$|^\*{3,}$|^_{3,}$', stripped):
                continue
            if '|' in stripped:
                continue
            if stripped.startswith('```'):
                continue
            # Remove emphasis/list markers
            stripped = re.sub(r'\*\*([^*]+)\*\*', r'\1', stripped)
            stripped = re.sub(r'\*([^*]+)\*', r'\1', stripped)
            stripped = re.sub(r'^\s*[-*•▪◆]\s+', '', stripped)
            stripped = re.sub(r'^\s*\d+[.、)]\s+', '', stripped)
            stripped = re.sub(r'^>\s?', '', stripped)
            stripped = stripped.strip()
            if stripped:
                out_lines.append(stripped)
        text_clean = ' '.join(out_lines)
        text_clean = re.sub(r'\s{2,}', ' ', text_clean).strip()
        if len(text_clean) > max_len:
            cut = text_clean[:max_len]
            last_break = max(cut.rfind('。'), cut.rfind('；'), cut.rfind('，'))
            text_clean = (cut[:last_break + 1] if last_break > max_len * 0.5 else cut) + "..."
        return text_clean

    # Provenance labels that indicate a financial figure was sourced from the model's
    # own parametric memory rather than API/tool data. These are forbidden by the
    # analysis prompts; this backstop guarantees they never reach the rendered report
    # as an acceptable source — they are forced to 'data missing'.
    _FABRICATED_PROVENANCE_PATTERNS = [
        ("自有知识库/联网搜索补充", "数据缺失（API/工具未提供）"),
        ("基于自有知识库", "数据缺失（API/工具未提供）"),
        ("自有知识库", "数据缺失（API/工具未提供）"),
        ("训练知识", "数据缺失（API/工具未提供）"),
        ("based on own knowledge", "data missing (API/tool unavailable)"),
        ("supplemented from own knowledge", "data missing (API/tool unavailable)"),
        ("own knowledge / web search", "data missing (API/tool unavailable)"),
        ("own knowledge", "data missing (API/tool unavailable)"),
        ("training knowledge", "data missing (API/tool unavailable)"),
        ("parametric memory", "data missing (API/tool unavailable)"),
    ]

    def _redact_fabricated_provenance(self, text):
        """Neutralize 'own knowledge / training data' provenance labels.

        Returns (redacted_text, found: bool). When the model tagged a figure as
        coming from its own parametric memory, we rewrite it to 'data missing' so
        no fabricated financial value is ever presented as a sourced fact.
        """
        if not text or not isinstance(text, str):
            return text, False
        found = False
        out = text
        for pat, repl in self._FABRICATED_PROVENANCE_PATTERNS:
            if pat.lower() in out.lower():
                out = re.sub(re.escape(pat), repl, out, flags=re.IGNORECASE)
                found = True
        return out, found

    def _is_low_quality_ui_data(self, ui_data: dict) -> bool:
        """Detect garbage/low-quality UI data extracted by LLM that should trigger fallback.

        Returns True if the extracted data is too poor to use, even though the dict is non-empty.
        This prevents markdown separators, overly long dumps, and empty critical fields
        from reaching the HTML renderer.
        """
        if not ui_data or not isinstance(ui_data, dict):
            return True

        GARBAGE_VALUES = {"---", "—", "N/A", "n/a", "TBD", "tbd", "TODO", "todo", "None", "null", ""}

        # Check verdict: must be substantive, not a separator or placeholder
        # Minimum 3 chars: Chinese like "买入" or "观望" is valid
        verdict = str(ui_data.get("verdict", "")).strip()
        if not verdict or verdict in GARBAGE_VALUES or len(verdict) < 3:
            return True

        # Check investment_thesis: must be concise (≤500 chars), not a full document dump
        thesis = str(ui_data.get("investment_thesis", "")).strip()
        if not thesis or thesis in GARBAGE_VALUES:
            return True
        if len(thesis) > 500:
            return True

        # Check the_call: must be substantive (min 3 chars for Chinese)
        the_call = str(ui_data.get("the_call", "")).strip()
        if not the_call or the_call in GARBAGE_VALUES or len(the_call) < 3:
            return True

        # Check tagline: must be substantive (min 3 chars for Chinese)
        tagline = str(ui_data.get("tagline", "")).strip()
        if not tagline or tagline in GARBAGE_VALUES or len(tagline) < 3:
            return True

        # Check recommendation: must be valid
        rec = str(ui_data.get("recommendation", "")).strip().upper()
        if rec not in ("BUY", "HOLD", "SELL", "STRONG BUY", "STRONG SELL", "WATCH"):
            return True

        return False

    def _describe_ui_data_schema_failure(self, ui_data: dict) -> str:
        if not ui_data or not isinstance(ui_data, dict):
            return "missing_ui_data"

        missing = []
        for field in ("verdict", "investment_thesis", "the_call", "tagline", "recommendation"):
            if not str(ui_data.get(field, "")).strip():
                missing.append(field)

        recommendation = str(ui_data.get("recommendation", "")).strip().upper()
        if recommendation and recommendation not in ("BUY", "HOLD", "SELL", "STRONG BUY", "STRONG SELL", "WATCH"):
            missing.append("recommendation.invalid")

        if len(str(ui_data.get("investment_thesis", "")).strip()) > 500:
            missing.append("investment_thesis.too_long")

        return ",".join(missing) or "low_quality_ui_data"

    def _validate_and_backfill_ui_data(self, ui_data: dict, discussion_msgs: list, snapshot: dict):
        """Validate critical UI fields; backfill from discussion if LLM returned empty or thinking text."""
        GARBAGE_VALUES = {"---", "—", "N/A", "n/a", "TBD", "tbd", "TODO", "todo", "None", "null", ""}

        # Coerce list-shaped fields: an LLM may return null or a string where a
        # list is expected — normalize here so the backfills below can repair them.
        for _k in ("upside", "downside", "moat_points", "macro_points", "risks_points",
                   "trading_steps", "scenarios", "peer_comparison", "catalyst_calendar"):
            if not isinstance(ui_data.get(_k), list):
                ui_data[_k] = []

        # Clean thinking prefixes from structured fields
        for field in ["investment_thesis", "tagline", "verdict", "action_stance", "the_call"]:
            if ui_data.get(field):
                ui_data[field] = self._strip_thinking_prefix(ui_data[field])

        # Check for thinking text that leaked into structured fields
        thinking_indicators = [
            "Now I have", "Let me ", "Based on my analysis", "OK, let me", "I will ", "I'll ",
            "现在我已", "让我", "根据分析", "好的，", "好的 ", "收到，", "收到 "
        ]

        def _is_thinking_text(val: str) -> bool:
            if not val or not isinstance(val, str):
                return False
            return any(val.strip().startswith(prefix) for prefix in thinking_indicators)

        # Normalize recommendation via the shared signal taxonomy so every
        # consumer (analysis verdict mapping, report UI data) agrees on
        # Strong Buy / Underweight / 中文评级 etc. Output keeps the BUY/SELL/HOLD
        # display convention (watch degrades to HOLD for display purposes).
        rec_raw = str(ui_data.get("recommendation", "")).strip()
        ui_data["recommendation"] = _ACTION_DISPLAY.get(normalize_action(rec_raw), "HOLD")

        # Fix consensus fields if they contain raw markdown documents
        cons = ui_data.get("consensus_vs_non_consensus")
        if isinstance(cons, dict):
            for _ck in ("market_consensus", "our_alpha"):
                _cv = cons.get(_ck)
                if isinstance(_cv, str) and self._looks_like_markdown_dump(_cv):
                    cons[_ck] = self._sanitize_markdown_field(_cv, max_len=300) or None

        # Ensure verdict exists — try to extract from discussion.
        # NOTE: when backfill fails the field is BLANKED so the previous (garbage)
        # value can never leak into the rendered report.
        verdict = str(ui_data.get("verdict", "")).strip()
        if not verdict or verdict in GARBAGE_VALUES or len(verdict) < 3 or _is_thinking_text(verdict) or self._looks_like_markdown_dump(verdict):
            ui_data["verdict"] = ""
            verdict = self._extract_verdict_from_discussion(discussion_msgs)
            if verdict and verdict not in GARBAGE_VALUES and not self._looks_like_markdown_dump(verdict):
                ui_data["verdict"] = verdict
            elif ui_data.get("summary"):
                # Summary may still be a raw markdown dump at this point — sanitize
                # before deriving the first sentence from it.
                s_first = self._sanitize_markdown_field(str(ui_data["summary"]), max_len=200).split("。")[0].strip()
                if (len(s_first) >= 3 and '|' not in s_first and not s_first.startswith('#')
                        and not self._looks_like_markdown_dump(s_first)):
                    ui_data["verdict"] = s_first[:60]

        # Fix investment_thesis if empty, garbage, thinking text, markdown dump, or too long
        thesis = str(ui_data.get("investment_thesis", "")).strip()
        if not thesis or thesis in GARBAGE_VALUES or _is_thinking_text(thesis) or self._looks_like_markdown_dump(thesis):
            # Prefer a keyword-bearing analytical sentence; otherwise reduce the
            # dumped markdown to plain prose so no raw '#'/'|' markup is rendered.
            sanitized = self._sanitize_markdown_field(thesis, max_len=500)
            extracted = self._extract_first_substantive_sentence(discussion_msgs)
            if not extracted or extracted.startswith("请参考"):
                extracted = sanitized
            thesis = extracted or str(ui_data.get("verdict", ""))
        if len(thesis) > 500:
            thesis = thesis[:495] + "..."
        ui_data["investment_thesis"] = thesis

        # Ensure tagline exists
        tagline = str(ui_data.get("tagline", "")).strip()
        if not tagline or tagline in GARBAGE_VALUES or len(tagline) < 3 or _is_thinking_text(tagline) or self._looks_like_markdown_dump(tagline):
            symbol = snapshot.get("quote", {}).get("symbol", "股票")
            first_sent = ui_data.get("investment_thesis", "").split("。")[0].split("！")[0].split("?")[0].strip()
            first_sent = first_sent.split("\n")[0].strip() # Avoid capturing multiline markdown
            if 5 < len(first_sent) < 40 and '|' not in first_sent:
                ui_data["tagline"] = f"{symbol}: {first_sent}"
            else:
                ui_data["tagline"] = f"{symbol} 深度投资分析报告"

        # Ensure action_stance exists
        action_stance = str(ui_data.get("action_stance", "")).strip()
        if not action_stance or action_stance in GARBAGE_VALUES or len(action_stance) < 3 or _is_thinking_text(action_stance) or self._looks_like_markdown_dump(action_stance):
            rec = ui_data.get("recommendation", "WATCH")
            ui_data["action_stance"] = f"当前建议 {rec}，详见专家研讨记录中的交易计划"

        # Ensure the_call exists and is substantive
        the_call = str(ui_data.get("the_call", "")).strip()
        if not the_call or the_call in GARBAGE_VALUES or len(the_call) < 3 or _is_thinking_text(the_call) or self._looks_like_markdown_dump(the_call):
            ui_data["the_call"] = (
                ui_data.get("action_stance")
                or ui_data.get("verdict")
                or f"建议对该标的关注{ui_data.get('recommendation', 'HOLD')}机会"
            )
        if len(ui_data["the_call"]) > 200:
            ui_data["the_call"] = ui_data["the_call"][:195] + "..."

        # Backfill lists if they are empty
        if not ui_data.get("upside"):
            ui_data["upside"] = self._extract_items_by_keywords_dual("upside", ["看涨", "看多", "多头", "利好", "上行", "催化剂", "Catalyst", "Upside", "Bull", "机遇", "优势", "核心竞争力", "核心论点"], discussion_msgs)
        if not ui_data.get("downside"):
            ui_data["downside"] = self._extract_items_by_keywords_dual("downside", ["看跌", "看空", "空头", "利空", "下行", "风险", "Risk", "Downside", "Bear", "压制", "威胁", "一致性偏差", "被忽视", "盲区", "Consensus Bias"], discussion_msgs)
        if not ui_data.get("moat_points"):
            ui_data["moat_points"] = self._extract_items_by_keywords_dual("moat", ["护城河", "Moat", "壁垒", "竞争优势"], discussion_msgs)
        if not ui_data.get("macro_points"):
            ui_data["macro_points"] = self._extract_items_by_keywords_dual("macro", ["宏观", "技术面", "资金面", "Technical", "Macro"], discussion_msgs)
        if not ui_data.get("risks_points"):
            ui_data["risks_points"] = self._extract_items_by_keywords_dual("risks", ["证伪", "失效", "止损", "Invalidation", "风险预警"], discussion_msgs)

        def _is_truncated_narrative(val) -> bool:
            """Detect LLM output cut off mid-sentence (e.g. ends with '：' or no
            sentence terminator) — a truncated field must be treated as missing."""
            v = str(val or "").strip()
            return bool(v) and len(v) >= 30 and not v.rstrip().endswith(("。", "！", "？", "…", ".", "!", "?", '"', "”", "'", "’"))

        # Backfill narrative summary fields — these MUST be substantive paragraphs, not placeholders
        narrative_backfill_map = {
            "moat_summary": (["护城河", "Moat", "壁垒", "竞争优势", "基本面", "Fundamental"], ["moat", "competitive", "fundamental"]),
            "macro_summary": (["宏观", "技术面", "资金面", "Technical", "Macro", "行业格局", "供给", "需求"], ["macro", "technical", "supply", "demand"]),
            "trading_plan": (["交易计划", "操作步骤", "Trading Plan", "建仓", "仓位", "止损", "风控", "Execution", "入场", "目标价"], ["trading", "execution", "position", "stop"]),
        }
        for field, (keywords, _) in narrative_backfill_map.items():
            val = ui_data.get(field, "")
            if not val or len(str(val).strip()) < 30 or self._looks_like_markdown_dump(val) or _is_truncated_narrative(val):
                # Exclude the moat text when re-extracting macro so the two
                # narrative sections never render identical content.
                exclude = [ui_data.get("moat_summary", "")] if field == "macro_summary" else None
                extracted = self._extract_narrative_section(field, keywords, discussion_msgs, exclude_texts=exclude)
                if extracted:
                    ui_data[field] = extracted
                elif val and self._looks_like_markdown_dump(val):
                    # Extraction found nothing useful — at least strip the raw
                    # markdown so the field renders as plain prose, not markup.
                    ui_data[field] = self._sanitize_markdown_field(val, max_len=500)

        # Guard: fundamental & macro narratives must never render identical content
        m_s = str(ui_data.get("moat_summary", "") or "").strip()
        x_s = str(ui_data.get("macro_summary", "") or "").strip()
        if m_s and x_s and (m_s == x_s or (len(m_s) > 100 and m_s in x_s) or (len(x_s) > 100 and x_s in m_s)):
            re_extracted = self._extract_narrative_section(
                "macro_summary",
                ["宏观", "技术面", "资金面", "Technical", "Macro", "行业格局", "供给", "需求"],
                discussion_msgs, exclude_texts=[m_s],
            )
            if re_extracted and re_extracted.strip() != m_s:
                ui_data["macro_summary"] = re_extracted

        # Backfill structured trading steps from discussion tables when the LLM
        # extraction returned nothing (common — the plan lives in markdown tables).
        if not ui_data.get("trading_steps"):
            steps = self._extract_trading_steps_from_discussion(discussion_msgs)
            if steps:
                ui_data["trading_steps"] = steps

        # Backfill summary if too short or if it is a raw markdown dump
        summary_val = ui_data.get("summary", "")
        if not summary_val or len(str(summary_val).strip()) < 30 or self._looks_like_markdown_dump(summary_val):
            extracted_summary = self._extract_narrative_section("summary", ["核心", "投资", "估值", "thesis", "core", "conclusion", "总结", "结论"], discussion_msgs)
            if extracted_summary:
                ui_data["summary"] = extracted_summary
            elif summary_val and self._looks_like_markdown_dump(summary_val):
                ui_data["summary"] = self._sanitize_markdown_field(summary_val, max_len=500)

        # Ensure data_completeness is populated
        dc = ui_data.get("data_completeness")
        if not dc or not isinstance(dc, dict) or dc.get("score") is None:
            # Estimate from N/A count in fundamentals-related fields
            na_fields = [k for k in ["net_profit", "capex", "revenue_qoq", "net_profit_yoy",
                                      "pe_percentile", "asset_turnover"] if not ui_data.get(k)]
            score = max(30, 100 - len(na_fields) * 10)
            ui_data["data_completeness"] = {"score": score, "missing": na_fields[:5],
                                             "impact": "部分指标缺失可能影响估值精度" if na_fields else ""}

    def _extract_first_substantive_sentence(self, discussion_msgs: list) -> str:
        """Extract the first substantive analytical sentence from discussion."""
        for m in discussion_msgs:
            content = m.get("content", "").strip()
            # Skip very short or thinking-prefixed content
            if len(content) < 100:
                continue
            # Try to find a sentence that looks like analysis (contains stock/financial terms)
            content_normalized = content.replace('\\n', '\n')
            lines = content_normalized.split('\n')
            for line in lines:
                line = line.strip().lstrip('- *#>')
                if '|' in line:
                    continue  # skip markdown table rows
                # Skip report title lines ('…深度研究…' / '…审计报告…') — a title
                # is not an analytical sentence and reads badly as a verdict.
                if re.search(r'(深度研究|研究报告|分析报告|审计报告|评审报告|裁决报告|风险管理报告|技术分析)', line):
                    continue
                line = re.sub(r'\*\*', '', line)
                if 20 < len(line) < 150 and any(kw in line for kw in ["核心", "投资", "估值", "盈利", "增长", "周期",
                                                                  "thesis", "core", "valuation", "profit"]):
                    return line
        return "请参考下方详细深度研报..."

    def _extract_narrative_section(self, field: str, keywords: list, discussion_msgs: list, exclude_texts: list = None) -> str:
        """Extract a narrative paragraph from expert discussion for a given semantic field.

        Scans discussion messages for sections that discuss the given topic and
        returns the most substantive paragraph found (structured analysis, not bullet lists).
        `exclude_texts`: paragraphs to ignore — used to prevent two narrative fields
        (e.g. moat_summary / macro_summary) from being backfilled with identical text.
        """
        exclude_texts = [str(t).strip() for t in (exclude_texts or []) if str(t).strip()]
        section_candidates: List[str] = []
        para_candidates: List[str] = []
        for m in discussion_msgs:
            content = m.get("content", "").strip()
            if len(content) < 100:
                continue
            content_normalized = content.replace('\\n', '\n')
            lines = content_normalized.split('\n')

            in_section = False
            section_buffer = []
            section_kws: set = set()

            def _flush_section():
                nonlocal section_buffer, section_kws
                full_text = ' '.join(section_buffer).strip()
                if len(full_text) > 50:
                    # Backfilled narratives render as plain prose: strip ALL bold
                    # markers (unpaired '**' would leak through markdown2) and
                    # leading blockquote markers.
                    full_text = re.sub(r'\*\*', '', full_text)
                    full_text = re.sub(r'^>\s?', '', full_text, flags=re.MULTILINE)
                    section_candidates.append((section_kws, full_text))
                section_buffer = []
                section_kws = set()

            for line in lines:
                stripped = line.strip()

                # Detect section headers that match our keywords
                is_header = stripped.startswith('#')
                is_bold = stripped.startswith('**') and stripped.endswith('**')

                if is_header or is_bold:
                    clean_header = stripped.lstrip('#').strip().strip('*').strip()
                    matched_header_kws = {kw for kw in keywords if kw.lower() in clean_header.lower()}
                    if matched_header_kws:
                        # Consecutive matching headers: flush the previous section
                        # first (e.g. '6️⃣ 交易计划' → '7️⃣ 分步建仓计划' both match)
                        if in_section and section_buffer:
                            _flush_section()
                        in_section = True
                        section_buffer = []
                        section_kws = matched_header_kws
                    elif in_section:
                        # Section ended — flush buffer if substantial
                        _flush_section()
                        in_section = False
                    continue

                if in_section:
                    if stripped.startswith('---') or stripped.startswith('==='):
                        continue
                    if not stripped:
                        if section_buffer:
                            section_buffer.append('')
                        continue
                    # Key-value table rows (label | content) carry the substantive
                    # analysis in LLM reports (e.g. 入场策略 | ①左侧：21.0~21.5元…).
                    # Convert 2-column rows into prose so the narrative is not lost.
                    if '|' in stripped:
                        row = stripped.strip('|').strip()
                        cells = [c.strip().strip('*').strip() for c in row.split('|')]
                        if len(cells) == 2 and 0 < len(cells[0]) <= 24 and len(cells[1]) > 12:
                            section_buffer.append(f"{cells[0]}：{cells[1]}")
                        continue
                    # Collect non-bullet prose lines
                    if not re.match(r'^\s*[-*•▪◆\d.)]+\s', stripped):
                        # Skip lines that look like JSON or data fragments
                        if not re.match(r'^[\d.,\-+%]+$|^N/?A$', stripped):
                            section_buffer.append(stripped)

            # Flush remaining buffer
            if in_section:
                _flush_section()

            # Paragraph-based fallback: look for any paragraph containing multiple keywords
            paragraphs = re.split(r'\n\s*\n', content_normalized)
            for para in paragraphs:
                para = para.strip()
                # Skip headers, bullets, tables, code blocks
                if para.startswith('#') or para.startswith('```') or '|' in para:
                    continue
                matched_kws = sum(1 for kw in keywords if kw.lower() in para.lower())
                if matched_kws >= 2 and len(para) > 60:
                    # Clean up markdown formatting
                    para_clean = re.sub(r'\*\*', '', para)
                    para_candidates.append(para_clean[:800])

        def _excluded(text: str) -> bool:
            return any(ex in text or text in ex for ex in exclude_texts)

        def _score(text: str, header_kws: set = None) -> tuple:
            # Prefer candidates matching MORE distinct keywords (header + text);
            # longer text breaks ties
            text_kws = {kw for kw in keywords if kw.lower() in text.lower()}
            return (len((header_kws or set()) | text_kws), len(text))

        # Drop candidates already claimed by another field (e.g. the audit's
        # '技术面与基本面背离调和' section must not fill BOTH moat and macro)
        section_candidates = [c for c in section_candidates if not _excluded(c[1])]
        para_candidates = [c for c in para_candidates if not _excluded(c)]

        if section_candidates:
            section_candidates.sort(key=lambda c: _score(c[1], c[0]), reverse=True)
            return section_candidates[0][1][:800]
        if para_candidates:
            para_candidates.sort(key=_score, reverse=True)
            return para_candidates[0][:800]

        return ""

    def _extract_verdict_from_discussion(self, discussion_msgs: list) -> str:
        """Try to extract a verdict-like sentence from the discussion content."""
        # Look for patterns that indicate a verdict/conclusion
        verdict_patterns = [
            r'(?:结论|核心观点|投资建议|最终判定|Overall|Verdict|Conclusion)[：:\s]*([^\n]{10,60})',
            r'(?:综合评估|总体判断|综上)[：:\s]*([^\n]{10,60})',
        ]
        all_text = "\n".join([m.get("content", "").replace('\\n', '\n') for m in discussion_msgs])
        for pattern in verdict_patterns:
            for match in re.finditer(pattern, all_text, re.IGNORECASE):
                cand = match.group(1).strip()
                # Reject table rows, headings, and other markdown artifacts —
                # the pattern can span a newline and capture a table header
                # like '| 风险项 | 说明 |' right after a '…结论' section title.
                if not cand or '|' in cand or cand.startswith('#') or self._looks_like_markdown_dump(cand):
                    continue
                # Strip bold-marker remnants ('**：xxx') and a leading colon
                cand = cand.replace('*', '').strip()
                cand = re.sub(r'^[：:]\s*', '', cand)
                if len(cand) >= 6:
                    return cand[:60]
        return ""

    @staticmethod
    def _clean_extracted_item(text: str) -> str:
        """Strip markdown noise (bold, blockquote, list markers) from extracted list items."""
        t = re.sub(r'\*\*([^*]+)\*\*', r'\1', str(text))
        t = re.sub(r'^>\s?', '', t)
        t = re.sub(r'^[-*•▪◆]\s+', '', t)
        return t.strip()

    def _extract_strings_from_dict(self, d_val: dict, category: str) -> List[str]:
        strs = []
        for dk, dv in d_val.items():
            if category in ("moat", "upside"):
                if any(x in dk.lower() for x in ["disadvantage", "risk", "shortcoming", "weakness", "threat", "bear"]):
                    continue
            if isinstance(dv, str) and len(dv) > 5:
                strs.append(dv)
            elif isinstance(dv, dict):
                strs.extend(self._extract_strings_from_dict(dv, category))
            elif isinstance(dv, list):
                for item in dv:
                    if isinstance(item, str) and len(item) > 5:
                        strs.append(item)
        return strs

    @staticmethod
    def _item_passes_category(text: str, category: str) -> bool:
        """Filter extracted items so the bull list only gets bull-ish lines and vice versa.

        Prevents bearish/technical statements (e.g. '均线呈箱体收敛而非多头发散')
        from leaking into the 看涨驱动 list when a header merely mentions 多头.
        """
        if category not in ("upside", "downside"):
            return True
        pos_kws = ("看涨", "看多", "多头", "利好", "上行", "催化", "Upside", "Bull", "机遇", "优势", "增长空间")
        neg_kws = ("看跌", "看空", "空头", "利空", "下行", "风险", "Downside", "Bear", "压制", "威胁", "证伪", "侵蚀")
        has_pos = any(k in text for k in pos_kws)
        has_neg = any(k in text for k in neg_kws)
        if category == "upside":
            if not has_pos or has_neg:
                return False
            # Skip pure technical-chart noise (均线/MA/KDJ/MACD lines)
            return not re.search(r'MA\d|KDJ|MACD|RSI|均线|DIF|DEA|OBV', text)
        # downside: must contain a negative keyword and no positive one
        return has_neg and not has_pos

    def _extract_items_by_keywords_dual(self, category: str, keywords: List[str], discussion_msgs: List[Dict[str, Any]], limit: int = 5) -> List[str]:
        # Category key mappings for JSON extraction
        category_keys = {
            "upside": ["upside", "opportunities", "bull_thesis", "catalysts", "key_opps", "upside_points", "core_thesis"],
            "downside": ["downside", "risks", "critical_risks", "risks_summary", "key_risks", "downside_points"],
            "moat": ["moat_points", "competitive_advantages", "moat", "competitive_positioning", "moat_summary"],
            "macro": ["macro_points", "macro", "technical_analysis", "macro_supply_demand", "macro_summary"],
            "risks": ["risks_points", "thesis_invalidation_trigger", "stop_loss_rules", "exit_mechanism", "risks", "risks_summary"]
        }

        # 1. Try JSON extraction first
        items = []
        for m in discussion_msgs:
            content = m.get("content", "").strip()
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    obj = json.loads(match.group(0))
                    target_keys = category_keys.get(category, [])
                    for tk in target_keys:
                        for k in obj.keys():
                            if k.lower() == tk.lower() or tk.lower() in k.lower() or k.lower() in tk.lower():
                                val = obj[k]
                                if isinstance(val, list):
                                    for item in val:
                                        if isinstance(item, str) and len(item) > 5:
                                            if item not in items:
                                                items.append(item)
                                elif isinstance(val, dict):
                                    for item in self._extract_strings_from_dict(val, category):
                                        if item not in items:
                                            items.append(item)
                                elif isinstance(val, str) and len(val) > 10:
                                    sentences = re.split(r'[。\n]+', val)
                                    for s in sentences:
                                        s_clean = s.strip()
                                        if len(s_clean) > 8:
                                            if s_clean not in items:
                                                items.append(s_clean)
                except Exception:
                    pass
        
        if len(items) >= 2:
            return items[:limit]

        # 2. Fallback to boundary-aware text scanner on normalized text
        for m in discussion_msgs:
            content = m.get("content", "")
            if not content:
                continue
            content_normalized = content.replace('\\n', '\n')
            lines = content_normalized.split('\n')
            in_section = False
            for line in lines:
                line_stripped = line.strip()
                
                # Check for header or bold label
                is_header = line_stripped.startswith('#')
                is_bold = line_stripped.startswith('**')
                is_bold_label = is_bold and any(kw.lower() in line_stripped.lower() for kw in keywords)
                
                if is_header:
                    if any(kw.lower() in line_stripped.lower() for kw in keywords):
                        in_section = True
                    else:
                        in_section = False
                    continue
                elif is_bold:
                    if is_bold_label:
                        in_section = True
                    else:
                        in_section = False
                    continue
                
                if in_section:
                    # Ignore table lines and dividers
                    if '|' in line_stripped or line_stripped.startswith('---') or line_stripped.startswith('==='):
                        continue
                    if not line_stripped:
                        continue
                        
                    m_bullet = re.match(r'^\s*[-*•▪◆\d.)]+\s*(.+)$', line_stripped)
                    if m_bullet:
                        clean = self._clean_extracted_item(m_bullet.group(1))
                        if len(clean) > 8 and not clean.startswith('#') and not clean.startswith('---'):
                            if self._item_passes_category(clean, category) and clean not in items:
                                items.append(clean)
                                if len(items) >= limit:
                                    break
                    elif line_stripped and not line_stripped.startswith('#') and len(line_stripped) > 15:
                        clean = self._clean_extracted_item(line_stripped)
                        if self._item_passes_category(clean, category) and clean not in items:
                            items.append(clean)
                            if len(items) >= limit:
                                break
            if len(items) >= limit:
                break

        # 3. Sentence-level fallback for thesis categories — the bull/bear content
        #    often lives in table rows or prose, not under matching headers. Split
        #    the raw text into fragments and keep keyword-bearing ones.
        if not items and category in ("upside", "downside"):
            for m in discussion_msgs:
                content = m.get("content", "") or ""
                content_normalized = content.replace('\\n', '\n')
                for frag in re.split(r'[。；;\n|]+', content_normalized):
                    frag = frag.strip()
                    if not (12 <= len(frag) <= 90):
                        continue
                    frag_clean = self._clean_extracted_item(frag)
                    if not frag_clean or frag_clean.startswith('#'):
                        continue
                    if self._item_passes_category(frag_clean, category) and frag_clean not in items:
                        items.append(frag_clean)
                    if len(items) >= limit:
                        return items[:limit]
        return items[:limit]

    _TRADING_STEP_HEADER_CELLS = {
        "交易方向", "触发条件", "量化参数", "层级", "触发价位", "仓位", "仓位%", "累计仓位",
        "触发逻辑", "逻辑", "情景", "触发", "目标区间", "概率", "场景", "入场价", "止损价",
        "止损距", "依据", "工具验证", "路径", "入场/止损", "风险/股", "1%风险对应仓位",
        "10%上限约束后", "实际单笔风险", "-8%减半仓", "-10%无条件平仓", "与结构位对照",
        "风险名称", "类别", "期望损失", "触发信号", "对冲策略", "压力场景", "恢复时间",
        "应对策略", "波动率", "指标", "数值", "建仓层级", "建仓", "价格", "触发价格",
        "仓位百分比", "权重", "占比", "累计",
    }

    def _extract_trading_steps_from_discussion(self, discussion_msgs: list) -> list:
        steps = []
        for m in discussion_msgs:
            content = m.get("content", "")
            if not content:
                continue
            content_normalized = content.replace('\\n', '\n')
            lines = content_normalized.split('\n')
            in_section = False
            for line in lines:
                line_stripped = line.strip()
                is_header = line_stripped.startswith('#')
                is_bold = line_stripped.startswith('**')
                is_plan_header = (is_header or is_bold) and any(kw in line_stripped for kw in ["建仓", "交易计划", "操作步骤", "Trading Plan", "Execution", "交易策略", "突破交易"])
                
                if is_header or is_bold:
                    if is_plan_header:
                        in_section = True
                    else:
                        in_section = False
                    continue
                
                if in_section and line_stripped.startswith('|') and line_stripped.endswith('|'):
                    parts = [p.strip() for p in line_stripped.split('|')[1:-1]]
                    if not parts or any('---' in p for p in parts):
                        continue
                    # Skip header rows (normalize cells like '量化参数（[✅ 工具确认]）')
                    norm_cells = [re.sub(r'[（(].*?[）)]', '', p).strip() for p in parts]
                    if any(p in self._TRADING_STEP_HEADER_CELLS for p in norm_cells[:3]):
                        continue
                    # Strip markdown emphasis from cells
                    parts = [self._clean_extracted_item(p) for p in parts]
                    if len(parts) >= 3:
                        if len(parts) == 3:
                            # 3-column tables: 方向 | 触发条件 | 量化参数 (no separate weight/logic)
                            steps.append({
                                "level": parts[0], "price": parts[1],
                                "weight": "自定", "logic": parts[2],
                            })
                        else:
                            steps.append({
                                "level": parts[0], "price": parts[1],
                                "weight": parts[2], "logic": parts[-1],
                            })
                        if len(steps) >= 4:
                            break
            if steps:
                break
        return steps

    def _build_fallback_ui_data(self, symbol: str, discussion_msgs: list, snapshot: dict) -> dict:
        """Build report data directly from discussion messages when LLM is unavailable."""
        # Try to parse the JSON blocks from discussion messages to extract structured data
        parsed_json_objs = []
        for m in discussion_msgs:
            content = m.get("content", "").strip()
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    obj = json.loads(match.group(0))
                    parsed_json_objs.append(obj)
                except Exception:
                    pass

        # Extract summary (prefer core_thesis)
        summary_text = ""
        for obj in parsed_json_objs:
            if "core_thesis" in obj and obj["core_thesis"]:
                summary_text = obj["core_thesis"]
                break
            elif "audit_officer_report" in obj and isinstance(obj["audit_officer_report"], dict):
                summary_text = obj["audit_officer_report"].get("audit_findings_summary")
                if summary_text: break
            elif "reviewer_report" in obj and isinstance(obj["reviewer_report"], dict):
                summary_text = obj["reviewer_report"].get("overall_assessment")
                if summary_text: break

        if not summary_text:
            # Fallback to text-based extraction — sanitize markdown so raw
            # '# 🔬 …' report dumps never reach the structured fields.
            for m in discussion_msgs:
                content = m.get("content", "").strip()
                if len(content) > 100:
                    clean = re.sub(r'<[｜|]*DSML[｜|]*[^>]*>.*?</[｜|]*DSML[｜|]*[^>]*>', '', content, flags=re.DOTALL)
                    clean = re.sub(r'```json.*?```', '', clean, flags=re.DOTALL)
                    clean = self._sanitize_markdown_field(clean, max_len=500)
                    if clean:
                        summary_text = clean
                        break
        if not summary_text:
            summary_text = f"{symbol} 分析报告 — 基于多轮专家研讨生成"

        # Clean thinking prefix
        summary_text = self._strip_thinking_prefix(summary_text)

        # Extract recommendation
        rating_val = None
        for obj in parsed_json_objs:
            if "rating" in obj and obj["rating"]:
                rating_val = obj["rating"]
                break
            elif "reviewer_report" in obj and isinstance(obj["reviewer_report"], dict) and obj["reviewer_report"].get("rating"):
                rating_val = obj["reviewer_report"]["rating"]
                break
        
        rec = "WATCH"
        if rating_val:
            r_upper = str(rating_val).upper()
            if any(k in r_upper for k in ("BUY", "STRONG BUY", "买入", "增持", "OVERWEIGHT", "长多")):
                rec = "BUY"
            elif any(k in r_upper for k in ("SELL", "STRONG SELL", "REDUCE", "AVOID", "卖出", "减持", "UNDERPERFORM", "看空", "避险")):
                rec = "SELL"
            elif any(k in r_upper for k in ("HOLD", "WATCH", "NEUTRAL", "中性", "观望")):
                rec = "HOLD"

        # Construct tagline
        tagline = ""
        for obj in parsed_json_objs:
            if "reviewer_report" in obj and isinstance(obj["reviewer_report"], dict):
                tagline = obj["reviewer_report"].get("report_title")
                if tagline: break
            elif "audit_officer_report" in obj and isinstance(obj["audit_officer_report"], dict):
                tagline = obj["audit_officer_report"].get("report_title")
                if tagline: break
        
        if tagline:
            tagline = self._strip_thinking_prefix(tagline)
            tagline = tagline.split('\n')[0].strip()[:50]
        else:
            first_sent = summary_text.split("。")[0].split("！")[0].split("?")[0].strip()
            first_sent = first_sent.split('\n')[0].strip()
            # Skip lines that are still markdown-ish (titles, table fragments)
            if (5 < len(first_sent) < 50 and not first_sent.startswith('#') and '|' not in first_sent):
                tagline = f"{symbol}: {first_sent}"
            else:
                tagline = f"{symbol} 深度投资分析报告"

        # Extract verdict
        verdict = ""
        for obj in parsed_json_objs:
            if "rating_rationale" in obj and obj["rating_rationale"]:
                verdict = obj["rating_rationale"].split("。")[0][:40]
                if verdict: break
        if verdict:
            verdict = self._strip_thinking_prefix(verdict)
            verdict = verdict.split('\n')[0].strip()[:60]
        else:
            # Prefer a keyword-bearing analytical sentence over the raw opening line
            # (which may still be a report title or emoji header after sanitization).
            v_cand = self._extract_first_substantive_sentence(discussion_msgs)
            if not v_cand:
                v_cand = summary_text.split("。")[0]
            v_cand = v_cand.split('\n')[0].strip()[:60]
            if v_cand and not v_cand.startswith('#') and '|' not in v_cand:
                verdict = v_cand
            else:
                verdict = "分析完成，详细结论请查看报告正文"

        # Extract action_stance
        action_stance = ""
        for obj in parsed_json_objs:
            if "reviewer_report" in obj and isinstance(obj["reviewer_report"], dict):
                action_stance = obj["reviewer_report"].get("final_action_directive")
                if action_stance: break
            elif "final_mandate_to_chief_strategist" in obj and obj["final_mandate_to_chief_strategist"]:
                action_stance = obj["final_mandate_to_chief_strategist"]
                if action_stance: break
        if action_stance:
            action_stance = self._strip_thinking_prefix(action_stance)
        else:
            action_stance = f"根据研讨分析结论，当前建议对该标的采取 {rec} 评级指导意见"

        # Extract lists using the new dual method
        upside = self._extract_items_by_keywords_dual("upside", ["看涨", "看多", "多头", "利好", "上行", "催化剂", "Catalyst", "Upside", "Bull", "机遇", "优势", "核心竞争力", "核心论点"], discussion_msgs)
        downside = self._extract_items_by_keywords_dual("downside", ["看跌", "看空", "空头", "利空", "下行", "风险", "Risk", "Downside", "Bear", "压制", "威胁", "一致性偏差", "被忽视", "盲区", "Consensus Bias"], discussion_msgs)
        moat_points = self._extract_items_by_keywords_dual("moat", ["护城河", "Moat", "壁垒", "竞争优势"], discussion_msgs)
        macro_points = self._extract_items_by_keywords_dual("macro", ["宏观", "技术面", "资金面", "Technical", "Macro"], discussion_msgs)
        risks_points = self._extract_items_by_keywords_dual("risks", ["证伪", "失效", "止损", "Invalidation", "风险预警"], discussion_msgs)

        # Build trading steps
        trading_steps = self._extract_trading_steps_from_discussion(discussion_msgs)
        if not trading_steps:
            trading_lines = self._extract_items_by_keywords_dual("risks", ["交易计划", "操作步骤", "Trading Plan", "Execution", "交易策略"], discussion_msgs)
            trading_steps = []
            for i, line in enumerate(trading_lines[:4]):
                trading_steps.append({
                    "level": f"步骤 {i+1}",
                    "price": "价格见研讨",
                    "weight": "自定",
                    "logic": line[:150]
                })

        # Extract narrative summaries from discussion instead of hardcoded placeholders
        moat_summary = self._extract_narrative_section("moat", ["护城河", "Moat", "壁垒", "竞争优势", "基本面", "Fundamental"], discussion_msgs)
        macro_summary = self._extract_narrative_section("macro", ["宏观", "技术面", "资金面", "Technical", "Macro", "行业格局", "供给", "需求"], discussion_msgs)
        trading_plan_summary = self._extract_narrative_section("trading", ["交易计划", "操作步骤", "Trading Plan", "建仓", "仓位", "止损", "风控", "Execution", "入场", "目标价"], discussion_msgs)

        investment_thesis = (summary_text[:490] if len(summary_text) > 490 else summary_text) or verdict
        the_call = action_stance[:100] if action_stance else (verdict[:100] if verdict else f"关注{symbol}后续信号")

        return {
            "summary": summary_text,
            "moat_summary": moat_summary or "暂无基本面护城河深度解析数据",
            "moat_points": moat_points,
            "macro_summary": macro_summary or "暂无宏观与资金技术面剖析数据",
            "macro_points": macro_points,
            "trading_plan": trading_plan_summary or "暂无交易执行步骤与风险防线数据",
            "trading_steps": trading_steps,
            "risks_points": risks_points,
            "upside": upside,
            "downside": downside,
            "scenarios": self._default_scenarios(),
            "score": 75,
            "recommendation": rec,
            "tagline": tagline,
            "verdict": verdict,
            "action_stance": action_stance,
            "investment_thesis": investment_thesis,
            "the_call": the_call,
        }

    def _extract_thesis_from_discussion(self, discussion_msgs: list) -> dict:
        """Extract bull/bear thesis points from expert discussion text using pattern matching."""
        upside = self._extract_items_by_keywords_dual("upside", ["看涨", "利好", "上行", "催化剂", "Catalyst", "Upside", "机遇", "优势", "核心竞争力", "核心论点"], discussion_msgs)
        downside = self._extract_items_by_keywords_dual("downside", ["看跌", "利空", "下行", "风险", "Risk", "Downside", "压制", "威胁", "一致性偏差", "被忽视", "盲区", "Consensus Bias"], discussion_msgs)
        
        # Fallback: if still empty, try to extract from table rows in Risk Manager content
        if not downside:
            for m in discussion_msgs:
                if m.get("role") == "Risk Manager":
                    content = m.get("content", "")
                    content_normalized = content.replace('\\n', '\n')
                    risk_matches = re.findall(r'\|\s*\*\*(.+?)\*\*\s*[-—–|]', content_normalized)
                    downside = [r.strip() for r in risk_matches if len(r.strip()) > 5][:5]
                    break

        return {"upside": upside, "downside": downside}

    def _markdown_to_html_fallback(self, content: str) -> str:
        """Convert markdown to HTML without LLM, used when API is unavailable."""
        stripped = content.strip()
        if not stripped:
            return "<p><em>(无内容)</em></p>"
        # Strip DSML tokens
        stripped = re.sub(r'<[｜|]*DSML[｜|]*[^>]*>', '', stripped)
        stripped = re.sub(r'</[｜|]*DSML[｜|]*[^>]*>', '', stripped)
        stripped = re.sub(r'<think>.*?</think>', '', stripped, flags=re.DOTALL)
        # Strip structured-data JSON blocks (LLM artifacts) before conversion
        stripped = re.sub(r'<structured[\\_]?data>.*?</structured[\\_]?data>', '', stripped, flags=re.DOTALL | re.IGNORECASE)
        stripped = re.sub(r'\\n{3,}', '\\n\\n', stripped).strip()
        if not stripped:
            return "<p><em>(Tool-calling round — no text content)</em></p>"
        # Also handle Python reprs and escape underscores before markdown conversion
        stripped = self._replace_python_reprs_in_text(stripped)
        try:
            return self._postprocess_markdown(markdown2.markdown(self._preprocess_chinese_bold(stripped), extras=["fenced-code-blocks", "tables", "header-ids"], safe_mode="escape"))
        except Exception:
            return f"<pre>{stripped}</pre>"

    async def _normalize_log_style(self, content: str, model: str = None, deepseek_api_key: str = None, gemini_api_key: str = None, openrouter_api_key: str = None) -> str:
        stripped = content.strip()

        # Strip DeepSeek thinking blocks (<think>...</think>) — hidden reasoning is
        # never meant for the reader of the expert log.
        if '<think>' in stripped:
            stripped = re.sub(r'<think>.*?</think>', '', stripped, flags=re.DOTALL).strip()
        # Strip structured-data JSON blocks (LLM artifacts)
        stripped = re.sub(r'<structured[\\_]?data>.*?</structured[\\_]?data>', '', stripped, flags=re.DOTALL | re.IGNORECASE)

        # Strip DeepSeek DSML tokens (native tool call markup that may leak)
        if 'DSML' in stripped:
            stripped = re.sub(r'<[｜|]*DSML[｜|]*[^>]*>', '', stripped)
            stripped = re.sub(r'</[｜|]*DSML[｜|]*[^>]*>', '', stripped)
            stripped = re.sub(r'\n{3,}', '\n\n', stripped).strip()
            if not stripped:
                return "<p><em>(Tool-calling round — no text content)</em></p>"

        # Detect raw tool-call data fragments (mostly numbers/N/A without prose)
        # Only discard if it's PURELY data with ZERO prose — keep if there's ANY analysis text
        lines = stripped.split('\n')
        non_empty_lines = [l.strip() for l in lines if l.strip()]
        if non_empty_lines:
            data_lines = sum(1 for l in non_empty_lines if re.match(
                r'^[\d.,\-+%]+$|^N/?A$|^[\d]+\.\d+$|^\d{6}$', l
            ))
            # Only discard if ≥90% data AND total is very short (≤10 non-empty lines)
            # This preserves expert rounds that have both data tables and prose analysis
            if len(non_empty_lines) <= 10 and len(non_empty_lines) > 0 and data_lines / len(non_empty_lines) > 0.9:
                return "<p><em>(数据查询轮次 — 无分析文本)</em></p>"

        # Detect JSON-containing content — use LLM to convert to 1️⃣2️⃣ styled markdown
        has_json = stripped.startswith("{") or stripped.startswith("```json")
        
        # Also detect trailing JSON block (markdown text followed by JSON at the end)
        trailing_json_md = ""
        if not has_json:
            json_clean = None
            json_start_pos = -1

            # 1) Any ```json ... ``` fenced block (schema-agnostic)
            for fence_match in re.finditer(r'```json\s*\n', stripped):
                fence_start = fence_match.end()
                candidate = self._extract_balanced_json(stripped[fence_start:])
                if candidate and candidate.count('"') >= 2:
                    json_clean = candidate
                    json_start_pos = fence_match.start()
                    break

            # 2) No fenced block — find first bare {...} object with at least one key
            if not json_clean:
                for brace_pos in (m.start() for m in re.finditer(r'\{', stripped)):
                    candidate = self._extract_balanced_json(stripped[brace_pos:])
                    if candidate and '":' in candidate and len(candidate) > 40:
                        json_clean = candidate
                        json_start_pos = brace_pos
                        break
            
            if json_clean:
                text_part = stripped[:json_start_pos].strip()
                # Any trailing text after JSON block
                end_pos = json_start_pos + stripped[json_start_pos:].find(json_clean) + len(json_clean)
                rest = stripped[end_pos:].strip()
                # Skip closing ``` fence
                if rest.startswith('```'):
                    rest = rest[3:].strip()
                
                local_md = self._json_to_markdown(json_clean)
                if local_md:
                    if rest:
                        local_md += f"\n\n{rest}"
                    trailing_json_md = self._postprocess_markdown(markdown2.markdown(self._preprocess_chinese_bold(local_md), extras=["tables", "fenced-code-blocks"], safe_mode="escape"))
                    stripped = text_part
                    if not stripped:
                        return trailing_json_md
        
        if has_json:
            # Try local JSON-to-markdown first (faster, more reliable)
            local_md = self._json_to_markdown(stripped)
            if local_md:
                return self._postprocess_markdown(markdown2.markdown(self._preprocess_chinese_bold(local_md), extras=["tables", "fenced-code-blocks"], safe_mode="escape"))
            # Fallback to LLM conversion
            prompt = f"""Convert this analyst output to professional markdown using '1️⃣ Title', '2️⃣ Title' style.

STRICT RULES:
1. PRESERVE ALL numerical values, prices, percentages, and data EXACTLY as-is.
2. DO NOT add, remove, or modify any factual content — only reformat.
3. Convert JSON fields to markdown tables or bullet lists as appropriate.
4. NO conversational openings. Output starts directly with the report content.

CONTENT:
{stripped[:12000]}
"""
            try:
                if not model:
                    provider = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek").lower()
                    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro") if provider == "deepseek" else os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
                res = await llm_gateway.generate_content(prompt, model=model, temperature=0.2, deepseek_api_key=deepseek_api_key, gemini_api_key=gemini_api_key, openrouter_api_key=openrouter_api_key)
                if res and len(res) > 100:
                    return self._postprocess_markdown(markdown2.markdown(self._preprocess_chinese_bold(res.strip()), extras=["tables", "fenced-code-blocks"], safe_mode="escape"))
            except Exception as e:
                print(f"JSON-to-markdown conversion failed: {e}")

        # Templates already enforce clean format — use fast local cleanup.
        # Apply Python repr → markdown conversion before rendering
        stripped = self._replace_python_reprs_in_text(stripped)

        # Use fast local regex to remove chatter instead of blocking on LLM calls
        stripped = self._strip_thinking_prefix(stripped)
        
        result = self._postprocess_markdown(markdown2.markdown(self._preprocess_chinese_bold(stripped), extras=["tables", "fenced-code-blocks"], safe_mode="escape"))
        return result + trailing_json_md if trailing_json_md else result

    def _extract_balanced_json(self, text: str) -> str:
        """Extract a balanced JSON object from the start of text by counting braces."""
        if not text or text[0] != '{':
            return ""
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[:i+1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        fixed = re.sub(r',(\s*[}\]])', r'\1', candidate)
                        try:
                            json.loads(fixed)
                            return fixed
                        except json.JSONDecodeError:
                            return ""
        return ""

    def _replace_python_reprs_in_text(self, text: str) -> str:
        """Find Python dict/list repr strings in text and convert them to markdown tables/lists.

        Uses a balanced-brace-scanner approach that is more robust than regex for
        nested or multi-line structures. Also escapes underscores in the output so
        markdown2 doesn't corrupt technical terms (e.g. market_cap_billion→market<em>cap</em>billion).
        """
        if not text:
            return text

        # Step 1: Save code blocks and inline code so we don't touch them
        code_blocks = []
        def _save_block(m):
            code_blocks.append(m.group(0))
            return f"__CB{len(code_blocks)-1}__"
        result = re.sub(r'```[\s\S]*?```', _save_block, text)
        result = re.sub(r'`[^`]+`', _save_block, result)

        def _try_convert(block: str) -> str:
            """Try to parse a block as Python literal and convert to markdown."""
            try:
                obj = ast.literal_eval(block)
                if isinstance(obj, dict) and len(obj) >= 2:
                    md = ReportGeneratorService._python_repr_to_markdown(block)
                    # Escape underscores in the generated markdown to prevent
                    # markdown2 from treating them as italics markers
                    return self._escape_technical_underscores(md)
                elif isinstance(obj, list) and len(obj) >= 2:
                    md = ReportGeneratorService._python_repr_to_markdown(block)
                    return self._escape_technical_underscores(md)
            except (ValueError, SyntaxError, MemoryError):
                pass
            return ""

        # Step 2: Find balanced {...} blocks (braces only — no nested braces inside)
        # These are simple single-level dicts: {'key': val, 'key2': val2}
        for m in re.finditer(r'\{([^{}]*)\}', result):
            block = m.group(0)
            # Must contain at least one single-quoted key to be a Python dict repr
            if "'" not in block or ":" not in block:
                continue
            md = _try_convert(block)
            if md:
                # Check context: is this inline after a label (e.g., "- **Key**: {dict}")
                before = result[max(0, m.start()-3):m.start()]
                after_label = before.rstrip().endswith(':') or before.rstrip().endswith('=')
                if after_label:
                    # Replace inline: keep the label context, add newlines for table
                    result = result[:m.start()] + '\n\n' + md + '\n\n' + result[m.end():]
                else:
                    result = result[:m.start()] + '\n' + md + '\n' + result[m.end():]

        # Step 3: Find balanced [...] blocks (simple lists of dicts or strings)
        pos = 0
        while pos < len(result):
            if result[pos] != '[':
                pos += 1
                continue
            end = self._find_matching_bracket(result, pos)
            if end == -1:
                pos += 1
                continue
            block = result[pos:end+1]
            # Skip if inside protected code block
            before_ctx = result[max(0, pos-20):pos]
            if '__CB' in before_ctx:
                pos = end + 1
                continue
            md = _try_convert(block)
            if md:
                before = result[max(0, pos-3):pos]
                after_label = before.rstrip().endswith(':') or before.rstrip().endswith('=')
                if after_label:
                    result = result[:pos] + '\n\n' + md + '\n\n' + result[end+1:]
                else:
                    result = result[:pos] + '\n' + md + '\n' + result[end+1:]
            pos = end + 1

        # Step 4: Handle remaining Python list reprs of strings: ['a', 'b']
        for m in re.finditer(r'\[((?:[\'\"][^\'\"]*[\'\"]\s*(?:,\s*)?)+)\]', result):
            block = m.group(0)
            before_ctx = result[max(0, m.start()-50):m.start()]
            if '__CB' in before_ctx:
                continue
            md = _try_convert(block)
            if md:
                try:
                    obj = ast.literal_eval(block)
                    if isinstance(obj, list) and len(obj) >= 2 and all(isinstance(x, str) for x in obj):
                        before = result[max(0, m.start()-3):m.start()]
                        after_label = before.rstrip().endswith(':') or before.rstrip().endswith('=')
                        if after_label:
                            result = result[:m.start()] + '\n\n' + md + '\n\n' + result[m.end():]
                        else:
                            result = result[:m.start()] + '\n' + md + '\n' + result[m.end():]
                except (ValueError, SyntaxError, MemoryError):
                    pass

        # Step 5: Escape remaining underscores in non-converted technical terms
        # that markdown2 would otherwise corrupt (market_cap_billion → market<em>cap</em>billion)
        result = self._escape_residual_underscores(result)

        # Restore code blocks
        for i, block in reversed(list(enumerate(code_blocks))):
            result = result.replace(f"__CB{i}__", block)
        return result

    def _find_matching_bracket(self, text: str, start: int) -> int:
        """Find the position of the matching closing bracket for text[start].
        Handles nested braces/brackets and strings. Returns -1 if not found."""
        if start >= len(text):
            return -1
        open_ch = text[start]
        close_map = {'[': ']', '{': '}'}
        if open_ch not in close_map:
            return -1
        close_ch = close_map[open_ch]
        depth = 0
        in_string = False
        string_char = None
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch in ('"', "'") and not escape:
                if not in_string:
                    in_string = True
                    string_char = ch
                elif ch == string_char:
                    in_string = False
                continue
            if in_string:
                continue
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        return -1

    def _escape_technical_underscores(self, md_text: str) -> str:
        """Escape underscores that look like technical identifiers (snake_case)
        so markdown2 doesn't convert them to <em> tags. Preserves markdown syntax
        like **bold** and *italic*."""
        # Only escape underscores in words that look like identifiers:
        # lowercase_with_underscores (at least one underscore with word chars on both sides)
        def _escape_id(m):
            word = m.group(0)
            # Don't escape if it's already escaped or inside markdown formatting
            return word.replace('_', '\\_')
        # Match snake_case identifiers (letter_letter pattern) using lookarounds to handle Chinese/non-ascii boundaries
        md_text = re.sub(r'(?<![a-zA-Z0-9])[a-z]+_[a-z][a-z_]*(?![a-zA-Z0-9])', _escape_id, md_text)
        return md_text

    def _escape_residual_underscores(self, text: str) -> str:
        """Escape underscores in remaining Python-repr-like fragments that look like
        snake_case identifiers, to prevent markdown2 corruption. Does NOT touch
        underscores that are part of markdown formatting (*italic*, **bold**, etc.)"""
        # Escape underscores between lowercase letters (snake_case identifiers)
        # that markdown2 would interpret as italics markers
        def _escape_snake(m):
            word = m.group(0)
            return word.replace('_', '\\_')
        # Only match genuine snake_case using lookarounds to avoid boundary issues with non-ascii chars
        result = re.sub(r'(?<![\\*a-zA-Z0-9])[a-z]+_[a-z][a-z_]*(?![a-zA-Z0-9])', _escape_snake, text)
        return result

    def _json_to_markdown(self, text: str) -> str:
        """Convert structured JSON analyst output to readable markdown locally (no LLM needed)."""
        try:
            clean = text.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.endswith("```"):
                clean = clean[:-3]
            data = json.loads(clean.strip())
        except (json.JSONDecodeError, ValueError):
            return ""

        # Readable labels for common expert-JSON keys (avoids raw snake_case in report)
        key_labels = {
            "core_thesis": "🎯 核心论点", "key_metrics_extracted": "📊 关键指标",
            "risks": "⚠️ 风险提示", "rating": "🏅 评级",
            "recommendation": "💡 操作建议", "minervini_stage": "📈 趋势阶段",
            "summary": "📝 摘要", "conclusion": "✅ 结论",
            "analysis": "🔍 分析", "verdict": "⚖️ 裁决",
            "key_findings": "🔑 核心发现", "catalysts": "🚀 催化剂",
            "valuation": "💰 估值", "thesis": "📋 论点",
            "score": "📊 评分", "confidence": "🎚️ 置信度",
        }

        def _humanize(k: str) -> str:
            if k in key_labels:
                return key_labels[k]
            # Replace separators; escape underscores to avoid markdown italics
            return re.sub(r'[_]+', ' ', k).strip().title()

        def _format_field(label: str, val: Any) -> str:
            field_lines = []
            if isinstance(val, str):
                field_lines.append(f"### {label}\n\n{val}\n")
            elif isinstance(val, dict):
                if "rows" in val:
                    # Structured table rendering
                    title = val.get("title", label)
                    field_lines.append(f"### {title}\n")
                    rows = val["rows"]
                    headers = val.get("headers")
                    if isinstance(rows, list) and rows:
                        if not headers:
                            if isinstance(rows[0], dict):
                                headers = list(rows[0].keys())
                            elif isinstance(rows[0], list):
                                headers = [f"Col {i+1}" for i in range(len(rows[0]))]
                        
                        if headers:
                            field_lines.append("| " + " | ".join(_humanize(h) for h in headers) + " |")
                            field_lines.append("|" + "|".join("------" for _ in headers) + "|")
                            for r in rows:
                                if isinstance(r, dict):
                                    row_vals = []
                                    for h in headers:
                                        v = r.get(h)
                                        if v is None:
                                            for rk, rv in r.items():
                                                if rk.lower().replace('_', ' ') == h.lower().replace('_', ' '):
                                                    v = rv
                                                    break
                                        if v is None and len(r) == len(headers):
                                            idx = headers.index(h)
                                            v = list(r.values())[idx]
                                        row_vals.append(ReportGeneratorService._format_py_value(v))
                                    field_lines.append("| " + " | ".join(row_vals) + " |")
                                elif isinstance(r, list):
                                    row_vals = [ReportGeneratorService._format_py_value(x) for x in r]
                                    field_lines.append("| " + " | ".join(row_vals) + " |")
                            field_lines.append("")
                        else:
                            for r in rows:
                                field_lines.append(f"- {ReportGeneratorService._format_py_value(r)}")
                            field_lines.append("")
                    else:
                        field_lines.append("- *(空)*\n")
                else:
                    field_lines.append(f"### {label}\n")
                    for dk, dv in val.items():
                        if isinstance(dv, list):
                            field_lines.append(f"- **{_humanize(dk)}**:")
                            for item in dv:
                                field_lines.append(f"  - {ReportGeneratorService._format_py_value(item)}")
                        elif isinstance(dv, dict):
                            field_lines.append(f"- **{_humanize(dk)}**:")
                            for sub_k, sub_v in dv.items():
                                field_lines.append(f"  - **{_humanize(sub_k)}**: {ReportGeneratorService._format_py_value(sub_v)}")
                        else:
                            field_lines.append(f"- **{_humanize(dk)}**: {ReportGeneratorService._format_py_value(dv)}")
                    field_lines.append("")
            elif isinstance(val, list):
                if val and all(isinstance(item, dict) for item in val):
                    field_lines.append(f"### {label}\n")
                    field_lines.append(ReportGeneratorService._format_list_of_dicts(val))
                    field_lines.append("")
                else:
                    field_lines.append(f"### {label}\n")
                    for item in val:
                        if isinstance(item, dict):
                            field_lines.append(f"- {' | '.join(str(v) for v in item.values())}")
                        else:
                            field_lines.append(f"- {item}")
                    field_lines.append("")
            else:
                field_lines.append(f"### {label}\n\n{val}\n")
            return "\n".join(field_lines)

        lines = []
        labels = {
            "tagline": "📌 核心论点",
            "investmentThesis": "📋 投资论题",
            "sentiment": "🎯 投资建议",
            "masterVariable": "🔑 核心变量",
            "coreContradiction": "⚡ 核心矛盾",
            "credibilityScore": "📊 可信度评分",
        }
        for key, label in labels.items():
            if key in data:
                lines.append(_format_field(label, data[key]))

        if "expectedPrice" in data and isinstance(data["expectedPrice"], dict):
            ep = data["expectedPrice"]
            lines.append("### 💰 预期价格计算\n")
            lines.append(f"- **计算公式**: {ep.get('calculation', 'N/A')}")
            lines.append(f"- **预期价格**: ${ep.get('result', 'N/A')}")
            lines.append(f"- **vs当前价格**: {ep.get('vsCurrentPrice', ep.get('currentPrice', 'N/A'))}")
            lines.append(f"- **预期回报**: {ep.get('expectedReturn', 'N/A')}")
            if ep.get('decisionRuleCheck'):
                lines.append(f"- **决策规则校验**: {ep.get('decisionRuleCheck')}")
            lines.append("")

        # Exit Mechanism / Disciplines
        em = data.get("exit_mechanism") or data.get("exitMechanism") or {}
        if em:
            lines.append("### 🚪 退出机制\n")
            if "takeProfit" in em:
                lines.append("**止盈:**")
                for item in em["takeProfit"]:
                    lines.append(f"- {item}")
            if "stopLoss" in em:
                lines.append("\n**止损:**")
                for item in em["stopLoss"]:
                    lines.append(f"- {item}")
            if "thesisFalsification" in em or "thesisInvalidation" in em:
                lines.append("\n**论题证伪条件:**")
                for item in em.get("thesisFalsification", em.get("thesisInvalidation", [])):
                    lines.append(f"- {item}")
            lines.append("")

        if "criticalRisks" in data and isinstance(data["criticalRisks"], list):
            lines.append("### ⚠️ 关键风险\n")
            for risk in data["criticalRisks"]:
                lines.append(f"- {risk}")
            lines.append("")

        if "falsificationRedlines" in data and isinstance(data["falsificationRedlines"], list):
            lines.append("### 🚨 证伪红线\n")
            lines.append("| 条件 | 窗口 | 行动 |\n|------|------|------|")
            for item in data["falsificationRedlines"]:
                if isinstance(item, dict):
                    lines.append(f"| {item.get('condition','')} | {item.get('window','')} | {item.get('action','')} |")
                elif isinstance(item, str):
                    lines.append(f"- {item}")
            lines.append("")

        if "keyRevisionsToPriorAnalyses" in data and isinstance(data["keyRevisionsToPriorAnalyses"], dict):
            lines.append("### 📝 关键修正\n")
            for rk, rv in data["keyRevisionsToPriorAnalyses"].items():
                lines.append(f"- **{_humanize(rk)}**: {rv}")
            lines.append("")

        # Formatting anything else
        handled = set(labels.keys()) | {"expectedPrice", "tradingPlan", "kellyPosition", "timeHorizon", "buildPlan", "exitMechanism", "criticalRisks", "falsificationRedlines", "keyRevisionsToPriorAnalyses"}
        for key, val in data.items():
            if key not in handled:
                label = _humanize(key)
                if isinstance(val, str):
                    lines.append(f"### {label}\n\n{val}\n")
                elif isinstance(val, dict):
                    lines.append(f"### {label}\n")
                    for dk, dv in val.items():
                        lines.append(f"- **{_humanize(dk)}**: {dv}")
                    lines.append("")
                elif isinstance(val, list):
                    lines.append(f"### {label}\n")
                    for item in val:
                        if isinstance(item, dict):
                            lines.append(f"- {' | '.join(str(v) for v in item.values())}")
                        else:
                            lines.append(f"- {item}")
                    lines.append("")

        raw_md = "\n".join(lines) if lines else ""
        return self._escape_technical_underscores(raw_md)

    @staticmethod
    def _python_repr_to_markdown(text: str) -> str:
        """Convert Python dict/list repr strings (single-quoted) to markdown tables/lists.

        Handles the common LLM output pattern where structured data leaks as Python repr
        rather than JSON. Uses ast.literal_eval for safe parsing."""
        if not text:
            return ""
        # Try to find a Python repr in the text
        # Look for dict {...} or list [...] patterns (not inside markdown code blocks)
        # Strip surrounding markdown code fences if present
        cleaned = text.strip()
        # Remove leading ```python or ``` markers
        cleaned = re.sub(r'^```(?:python|py)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

        # Try to parse as Python literal
        try:
            obj = ast.literal_eval(cleaned)
        except (ValueError, SyntaxError):
            return ""

        if isinstance(obj, list):
            return ReportGeneratorService._format_py_list(obj)
        elif isinstance(obj, dict):
            return ReportGeneratorService._format_py_dict(obj)
        return ""

    @staticmethod
    def _format_py_dict(d: dict) -> str:
        """Format a Python dict as a markdown key-value table."""
        if not d:
            return ""
        lines = []
        lines.append("| 字段 | 值 |")
        lines.append("|------|-----|")
        for k, v in d.items():
            # Humanize key: replace underscores with spaces, title-case
            key_display = k.replace('_', ' ').strip().title()
            val_str = ReportGeneratorService._format_py_value(v)
            lines.append(f"| {key_display} | {val_str} |")
        return "\n".join(lines)

    @staticmethod
    def _format_py_list(lst: list) -> str:
        """Format a Python list as markdown. List of dicts → table; list of scalars → bullets."""
        if not lst:
            return ""
        # If list of dicts, render as table
        if all(isinstance(item, dict) for item in lst):
            return ReportGeneratorService._format_list_of_dicts(lst)
        # Otherwise render as bullet list
        lines = []
        for item in lst:
            if isinstance(item, dict):
                # Mixed types — flatten to key: value bullets
                for k, v in item.items():
                    lines.append(f"- **{k.replace('_', ' ').title()}**: {ReportGeneratorService._format_py_value(v)}")
            elif isinstance(item, (list, tuple)):
                lines.append(f"- {', '.join(str(x) for x in item)}")
            else:
                # Skip items that are already full sentences (likely not data)
                s = str(item)
                if len(s) > 200 and ('。' in s or '.' in s):
                    lines.append(f"- {s}")
                else:
                    lines.append(f"- {s}")
        return "\n".join(lines)

    @staticmethod
    def _format_list_of_dicts(lst: list) -> str:
        """Format a list of dicts as a markdown table using keys as headers."""
        if not lst:
            return ""
        # Collect all keys across all dicts (preserving order of first dict, then adding others)
        first_keys = list(lst[0].keys())
        all_keys = list(first_keys)
        for d in lst[1:]:
            for k in d.keys():
                if k not in all_keys:
                    all_keys.append(k)

        # Humanize headers
        def humanize_key(k: str) -> str:
            return k.replace('_', ' ').strip().title()

        lines = []
        header = "| " + " | ".join(humanize_key(k) for k in all_keys) + " |"
        sep = "|" + "|".join("------" for _ in all_keys) + "|"
        lines.append(header)
        lines.append(sep)

        for d in lst:
            vals = []
            for k in all_keys:
                v = d.get(k, "")
                vals.append(ReportGeneratorService._format_py_value(v))
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)

    @staticmethod
    def _format_py_value(v) -> str:
        """Format a single Python value for display in a markdown table cell."""
        if v is None:
            return "—"
        if isinstance(v, bool):
            return "✅" if v else "❌"
        if isinstance(v, (list, tuple)):
            # Short lists: join; long lists: truncate
            items = [str(x) for x in v]
            joined = ", ".join(items)
            if len(joined) > 120:
                return joined[:117] + "..."
            return joined
        if isinstance(v, dict):
            # Flatten small dicts inline
            parts = [f"{k.replace('_', ' ')}: {ReportGeneratorService._format_py_value(v2)}" for k, v2 in v.items()]
            joined = "; ".join(parts)
            if len(joined) > 150:
                return joined[:147] + "..."
            return joined
        return str(v)

    @staticmethod
    def _format_sensitivity_table(sensitivity_str: str) -> str:
        """Convert WACC sensitivity Python repr like [{'wacc': 5.4, 'g': 1.0, 'value': 27.83}, ...]
        into a compact sensitivity matrix markdown table."""
        try:
            data = ast.literal_eval(sensitivity_str)
        except (ValueError, SyntaxError):
            # Try as JSON
            try:
                data = json.loads(sensitivity_str)
            except (json.JSONDecodeError, ValueError):
                return sensitivity_str  # Can't parse, return as-is

        if not isinstance(data, list) or not data:
            return sensitivity_str

        # Build table: columns = unique g values, rows = unique wacc values
        if all(isinstance(d, dict) and 'wacc' in d and 'value' in d for d in data):
            lines = []
            lines.append("| WACC | g | 每股价值 |")
            lines.append("|------|---|----------|")
            for d in data:
                wacc = d.get('wacc', 'N/A')
                g = d.get('g', 'N/A')
                value = d.get('value', 'N/A')
                lines.append(f"| {wacc} | {g} | {value} |")
            return "\n".join(lines)
        return sensitivity_str

    def _render_evidence_taxonomy(self, d: dict, info: dict, thesis: str, verdict: str, recommendation: str, the_call: str) -> str:
        import html

        def esc(value: Any) -> str:
            return html.escape(str(value)) if value is not None else ""

        data_completeness = d.get("data_completeness") if isinstance(d.get("data_completeness"), dict) else {}
        score = data_completeness.get("score", 100)
        missing = data_completeness.get("missing") or []
        missing_text = "、".join([str(item) for item in missing[:3]]) if missing else "未标记关键缺口"
        consensus = d.get("consensus_vs_non_consensus") if isinstance(d.get("consensus_vs_non_consensus"), dict) else {}
        # Defense-in-depth: every prose slot must be plain text. Values here can
        # originate from the fallback path or an LLM field that escaped the
        # validation pass — strip any raw markdown ('#', '**', table pipes)
        # before HTML-escaping so no document dump is ever displayed verbatim.
        thesis = self._render_prose(thesis, max_len=500) or ""
        verdict = self._render_prose(verdict, max_len=200) or ""
        the_call = self._render_prose(the_call, max_len=200) or ""
        summary = d.get("summary") if isinstance(d.get("summary"), str) else ""
        summary = self._render_prose(summary, max_len=200) or ""
        our_alpha = consensus.get("our_alpha")
        our_alpha = self._render_prose(our_alpha, max_len=300) if isinstance(our_alpha, str) else ""
        cards = [
            (
                "fact",
                "事实 Fact",
                f"{info.get('symbol', 'UNKNOWN')} 最新价格 {info.get('price', 'N/A')} {info.get('currency', '')}；数据完整度 {score}%，缺口：{missing_text}。",
            ),
            (
                "inference",
                "推理 Inference",
                thesis or our_alpha or "基于多专家讨论形成的因果链仍需结合原始日志复核。",
            ),
            (
                "opinion",
                "观点 Opinion",
                verdict or summary or "暂无可发布观点。",
            ),
            (
                "recommendation",
                "建议 Recommendation",
                f"评级：{recommendation or 'WATCH'}；操作口径：{the_call or '等待进一步确认'}。",
            ),
        ]
        rendered = "".join(
            f'<div class="claim-card claim-{kind}" data-claim-type="{kind}">'
            f'<div class="claim-label">{label}</div>'
            f'<div class="claim-text">{esc(text)}</div>'
            "</div>"
            for kind, label, text in cards
        )
        return f'<section class="evidence-taxonomy" aria-label="facts inference opinions recommendations">{rendered}</section>'

    def _get_locale(self, market: str) -> dict:
        """Return localized labels based on market."""
        if market == "US-Share":
            return {
                "page_title": "Deep Research Report",
                "executive_summary": "Executive Summary",
                "deep_fundamentals": "Deep Fundamental Data",
                "core_variables": "Core Variables",
                "bull_thesis": "Bull Thesis",
                "bear_thesis": "Bear Thesis",
                "moat_section": "Fundamental & Moat Analysis",
                "key_moat": "Key Moat Factors",
                "macro_section": "Technical & Macro Analysis",
                "trading_plan": "Trading Plan",
                "risk_warning": "Invalidation Risks",
                "scenario_title": "Scenario Analysis & Target Price",
                "scenario_case": "Scenario",
                "scenario_prob": "Probability",
                "scenario_target": "Target Price",
                "scenario_logic": "Key Driver",
                "discussion_log": "Expert Deliberation Log",
                "layer1_title": "Layer 1: Core Decision Package (1-Pager CIO Dashboard)",
                "layer2_title": "Layer 2: Investment Case & Data Evidence",
                "layer3_title": "Layer 3: Execution Plan & Risk Discipline",
                "appendix_title": "Appendix: Internal Research Debate Log",
                "card_factor_profile": "🎯 Factor Profile",
                "card_consensus": "⚖️ Consensus vs. Non-Consensus",
                "card_the_call": "📣 The Call (Action Directive)",
                "card_scenarios": "📉 Scenario Analysis & Price Forecast",
                "card_valuation": "🔍 Valuation Engine & Model Audit",
                "card_archetype_label": "Stock Archetype",
                "card_kill_switch": "🚨 Kill Switch (Falsification Redline)",
                "card_wacc": "WACC Model Disaggregation",
                "card_trading_steps": "📈 Trading Execution Steps",
                "card_wind_control": "⚠️ Market Event & Funding Control",
                "card_lr_signal": "🚦 Left/Right Side Signal Conditions",
                "card_drawdown": "🛡️ Drawdown Control & Thesis Invalidation",
                "card_flow_positioning": "💰 Flow & Positioning (资金面与筹码)",
                "label_northbound_hold": "Northbound Hold %:",
                "label_northbound_5d": "5-Day Net Inflow:",
                "label_northbound_trend": "5-Day Trend:",
                "label_baijiu_price": "飞天茅台批价:",
                "label_no_northbound": "No northbound data available",
                "label_no_baijiu": "Baijiu wholesale data unavailable",
                "label_thesis_narrative": "Investment Thesis Narrative",
                "label_size": "Size:",
                "label_style": "Style:",
                "label_volatility": "Volatility:",
                "label_expected_return": "Expected Return:",
                "label_market_consensus": "Market Consensus (Priced-in)",
                "label_our_alpha": "Alpha Edge (Our thesis)",
                "label_left_side": "Left-Side Support Entry:",
                "label_right_side": "Right-Side Breakout Trigger:",
                "label_max_drawdown": "Max Single-Stock Drawdown:",
                "label_invalidation": "Core Thesis Invalidation Trigger:",
                "label_unclassified": "Unclassified",
                "label_no_expectation": "No expected return profile specified",
                "label_no_consensus": "No consensus identified",
                "label_no_alpha": "No alpha edge identified",
                "label_no_left": "No left-side entry defined",
                "label_no_right": "No right-side trigger defined",
                "label_default_drawdown": "-8% to -10%",
                "label_no_invalidation": "No thesis invalidation trigger set",
                "disclaimer": "Disclaimer: This report is autonomously generated by ALSA Multi-Agent Matrix for reference only. Not investment advice.",
                "copyright": "© 2026 ALSA Intelligent Analysis System",
                "signal_healthy": "Healthy",
                "signal_neutral": "Neutral / Watch",
                "signal_risk": "Risk / Poor",
                "signal_na": "N/A",
                "cat_valuation": "Valuation",
                "cat_profitability": "Profitability",
                "cat_growth": "Growth",
                "cat_financial_health": "Financial Health",
                "cat_cashflow": "Cash Flow & Dividends",
                "cat_ownership": "Ownership",
                "cat_efficiency": "Operating Efficiency",
                "cat_market": "Market Context",
            }
        return {
            "page_title": "深度研究报告",
            "executive_summary": "核心投研摘要 (Executive Summary)",
            "deep_fundamentals": "深度基本面指标 (Deep Fundamental Data)",
            "core_variables": "核心博弈变量 (Core Variables)",
            "bull_thesis": "看涨逻辑驱动 (Bull Thesis)",
            "bear_thesis": "风险与压制因素 (Bear Thesis)",
            "moat_section": "基本面护城河深度解析 (Fundamental & Moat)",
            "key_moat": "关键护城河要素 (Key Moat Factors)",
            "macro_section": "宏观与资金技术面剖析 (Technical & Macro)",
            "trading_plan": "交易操作计划 (Trading Plan)",
            "risk_warning": "策略核心失效风险预警 (Invalidation Risks)",
            "scenario_title": "情景分析与目标价预测",
            "scenario_case": "演练情景",
            "scenario_prob": "概率",
            "scenario_target": "目标价",
            "scenario_logic": "核心驱动逻辑",
            "discussion_log": "专家研讨深度记录 (Expert Deliberation Log)",
                "layer1_title": "第一层：核心决策包 (1-Pager CIO Dashboard)",
                "layer2_title": "第二层：逻辑链条与数据实证 (Investment Case)",
                "layer3_title": "第三层：交易执行单与风险防线 (Execution Plan & Risk Discipline)",
                "appendix_title": "附录：内部投研辩论日志 (Debate Log & Model Audit)",
                "card_factor_profile": "🎯 因子雷达 (Factor Profile)",
                "card_consensus": "⚖️ 多空共识差 (Consensus vs. Non-Consensus)",
                "card_the_call": "📣 一句话决断 (The Call)",
                "card_scenarios": "📉 情景演练及期望价格预测",
                "card_valuation": "🔍 估值引擎与模型审计 (Valuation Engine & Model Audit)",
                "card_archetype_label": "标的分类属性 (Stock Archetype)",
                "card_kill_switch": "🚨 防伪红线 (Kill Switch)",
                "card_wacc": "WACC 贴现模型白箱审计 (WACC Model Disaggregation)",
                "card_trading_steps": "📈 交易操作步骤 (Trading Execution Steps)",
                "card_wind_control": "⚠️ 市场原生事件与筹码风控 (Event & Funding Control)",
                "card_lr_signal": "🚦 左右侧交易信号条件",
                "card_drawdown": "🛡️ 回撤风控与逻辑证伪出局",
                "card_flow_positioning": "💰 资金面与筹码 (Flow & Positioning)",
                "label_northbound_hold": "北向持仓占比：",
                "label_northbound_5d": "5日净流入：",
                "label_northbound_trend": "5日趋势：",
                "label_baijiu_price": "飞天茅台批价：",
                "label_no_northbound": "暂无北向资金数据",
                "label_no_baijiu": "白酒批发价数据暂不可用",
                "label_thesis_narrative": "核心定调 (Investment Thesis Narrative)",
                "label_size": "市值:",
                "label_style": "风格:",
                "label_volatility": "波动:",
                "label_expected_return": "收益预期特征：",
                "label_market_consensus": "市场共识 (Priced-in)",
                "label_our_alpha": "Alpha 预期差 (Our edge)",
                "label_left_side": "左侧支撑买入：",
                "label_right_side": "右侧放量突破：",
                "label_max_drawdown": "单票回撤上限：",
                "label_invalidation": "核心逻辑证伪触发器：",
                "label_unclassified": "未分类",
                "label_no_expectation": "未明确预期特征",
                "label_no_consensus": "未明确共识",
                "label_no_alpha": "未明确预期差",
                "label_no_left": "未规定左侧买点",
                "label_no_right": "未规定右侧买点",
                "label_default_drawdown": "-8% 到 -10%",
                "label_no_invalidation": "未设定逻辑止损触发器",
            "disclaimer": "免责声明：本报告由 ALSA 多代理矩阵自主生成，仅供参考，不构成投资建议。",
            "copyright": "© 2026 ALSA 智能分析系统",
            "signal_healthy": "健康",
            "signal_neutral": "中性/关注",
            "signal_risk": "风险/较差",
            "signal_na": "无数据/不适用",
            "cat_valuation": "估值定价 (Valuation)",
            "cat_profitability": "获利能力 (Profitability)",
            "cat_growth": "成长动力 (Growth)",
            "cat_financial_health": "财务稳健 (Financial Health)",
            "cat_cashflow": "现金流与分红 (Cash Flow)",
            "cat_ownership": "股东结构 (Ownership)",
            "cat_efficiency": "运营效率 (Efficiency)",
            "cat_market": "市场环境 (Market Context)",
        }

    # ── Factor Scoring & Chart Helpers ─────────────────────────────

    def _compute_factor_scores(self, snapshot: dict) -> dict:
        """Compute 5-factor scores (0-100) deterministically from snapshot.

        Axes: 价值(Value), 质量(Quality), 成长(Growth), 动量(Momentum), 波动(Volatility)
        """
        scores: dict = {}
        if not isinstance(snapshot, dict):
            return scores

        v = snapshot.get("valuation") or {}
        f = snapshot.get("financials") or {}
        q = snapshot.get("quote") or {}

        def _get(*keys):
            sources = [v, f, q]
            for k in keys:
                for s in sources:
                    val = s.get(k)
                    if val is not None:
                        return val
            return None

        def _clip(v, lo=0, hi=100):
            if v is None:
                return 50
            return max(lo, min(hi, round(v)))

        # 1. Value (价值) — lower PE/PB = higher score
        pe = _get("trailingPE", "pe", "forwardPE")
        pb = _get("priceToBook", "pb")
        pe_score = 50
        if pe is not None and isinstance(pe, (int, float)) and pe > 0:
            if pe < 10:
                pe_score = 95
            elif pe < 15:
                pe_score = 80
            elif pe < 20:
                pe_score = 65
            elif pe < 30:
                pe_score = 45
            elif pe < 50:
                pe_score = 25
            else:
                pe_score = 10
        pb_score = 50
        if pb is not None and isinstance(pb, (int, float)) and pb > 0:
            if pb < 1:
                pb_score = 95
            elif pb < 2:
                pb_score = 80
            elif pb < 3:
                pb_score = 60
            elif pb < 5:
                pb_score = 40
            elif pb < 10:
                pb_score = 20
            else:
                pb_score = 10
        scores["value"] = _clip((pe_score + pb_score) / 2)

        # 2. Quality (质量) — high ROE + high net margin
        roe = _get("returnOnEquity", "roe")
        nm = _get("profitMargins", "profitMargin", "netMargin")
        roe_score = 50
        if roe is not None and isinstance(roe, (int, float)):
            roe_pct = roe * 100 if abs(roe) < 1 else roe
            if roe_pct > 25:
                roe_score = 95
            elif roe_pct > 20:
                roe_score = 80
            elif roe_pct > 15:
                roe_score = 65
            elif roe_pct > 10:
                roe_score = 45
            elif roe_pct > 5:
                roe_score = 25
            else:
                roe_score = 10
        nm_score = 50
        if nm is not None and isinstance(nm, (int, float)):
            nm_pct = nm * 100 if abs(nm) < 1 else nm
            if nm_pct > 20:
                nm_score = 95
            elif nm_pct > 15:
                nm_score = 80
            elif nm_pct > 10:
                nm_score = 60
            elif nm_pct > 5:
                nm_score = 40
            elif nm_pct > 2:
                nm_score = 20
            else:
                nm_score = 10
        scores["quality"] = _clip((roe_score + nm_score) / 2)

        # 3. Growth (成长) — revenue YoY + net profit YoY
        rev_g = _get("revenueYoY_annual", "revenueYoY", "revenueGrowth")
        np_g = _get("netProfitYoY", "earningsGrowth", "netProfitGrowth")
        rev_score = 50
        if rev_g is not None and isinstance(rev_g, (int, float)):
            rev_pct = rev_g * 100 if abs(rev_g) < 1 else rev_g
            if rev_pct > 30:
                rev_score = 95
            elif rev_pct > 20:
                rev_score = 80
            elif rev_pct > 10:
                rev_score = 65
            elif rev_pct > 5:
                rev_score = 45
            elif rev_pct > 0:
                rev_score = 25
            else:
                rev_score = 10
        np_score = 50
        if np_g is not None and isinstance(np_g, (int, float)):
            np_pct = np_g * 100 if abs(np_g) < 1 else np_g
            if np_pct > 30:
                np_score = 95
            elif np_pct > 20:
                np_score = 80
            elif np_pct > 10:
                np_score = 65
            elif np_pct > 5:
                np_score = 45
            elif np_pct > 0:
                np_score = 25
            else:
                np_score = 10
        scores["growth"] = _clip((rev_score + np_score) / 2)

        # 4. Momentum (动量) — recent price change
        chg = _get("changePercent")
        mom_score = 50
        if chg is not None and isinstance(chg, (int, float)):
            if chg > 10:
                mom_score = 95
            elif chg > 5:
                mom_score = 80
            elif chg > 2:
                mom_score = 65
            elif chg > 0:
                mom_score = 50
            elif chg > -5:
                mom_score = 35
            elif chg > -10:
                mom_score = 20
            else:
                mom_score = 10
        scores["momentum"] = _clip(mom_score)

        # 5. Volatility (波动) — lower beta = higher score (stability preference)
        beta = _get("beta")
        vol_score = 50
        if beta is not None and isinstance(beta, (int, float)):
            if beta < 0.5:
                vol_score = 95
            elif beta < 0.8:
                vol_score = 80
            elif beta < 1.0:
                vol_score = 65
            elif beta < 1.2:
                vol_score = 50
            elif beta < 1.5:
                vol_score = 35
            elif beta < 2.0:
                vol_score = 20
            else:
                vol_score = 10
        scores["volatility"] = _clip(vol_score)

        return scores

    @staticmethod
    def _svg_radar(scores: dict, size: int = 200) -> str:
        """Generate inline SVG radar chart for 5 factor scores.

        scores keys: value, quality, growth, momentum, volatility
        """
        import math

        axes = [
            ("价值", "value"),
            ("质量", "quality"),
            ("成长", "growth"),
            ("动量", "momentum"),
            ("波动", "volatility"),
        ]
        cx, cy = size / 2, size / 2
        r = size * 0.35
        label_r = size * 0.44

        grid_color = "#e2e8f0"
        fill_color = "rgba(37, 99, 235, 0.25)"
        stroke_color = "#2563eb"
        text_color = "#334155"

        n = len(axes)
        angles = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]

        parts = [
            f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" style="max-width:220px; width:100%;">'
        ]

        # Grid pentagons at 20% intervals
        for level in range(1, 6):
            lr = r * level / 5
            pts = []
            for a in angles:
                x = cx + lr * math.cos(a)
                y = cy + lr * math.sin(a)
                pts.append(f"{x:.1f},{y:.1f}")
            fill = "none"
            sw = "0.5" if level < 5 else "1"
            parts.append(
                f'<polygon points="{" ".join(pts)}" fill="{fill}" stroke="{grid_color}" stroke-width="{sw}"/>'
            )

        # Axis lines
        for a in angles:
            x = cx + r * math.cos(a)
            y = cy + r * math.sin(a)
            parts.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{grid_color}" stroke-width="0.5"/>'
            )

        # Data polygon
        data_pts = []
        for i, (_label, key) in enumerate(axes):
            score = scores.get(key, 50)
            score = max(5, min(100, score))
            a = angles[i]
            dr = r * score / 100
            x = cx + dr * math.cos(a)
            y = cy + dr * math.sin(a)
            data_pts.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polygon points="{" ".join(data_pts)}" fill="{fill_color}" stroke="{stroke_color}" stroke-width="1.5"/>'
        )

        # Data points (dots) + score labels
        for i, (_label, key) in enumerate(axes):
            score = scores.get(key, 50)
            score = max(5, min(100, score))
            a = angles[i]
            dr = r * score / 100
            x = cx + dr * math.cos(a)
            y = cy + dr * math.sin(a)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{stroke_color}"/>')
            sx = cx + (dr + 12) * math.cos(a)
            sy = cy + (dr + 12) * math.sin(a)
            parts.append(
                f'<text x="{sx:.1f}" y="{sy:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="9" fill="{text_color}" font-family="Inter,Outfit,sans-serif">{int(score)}</text>'
            )

        # Axis labels
        for i, (label, _key) in enumerate(axes):
            a = angles[i]
            lx = cx + label_r * math.cos(a)
            ly = cy + label_r * math.sin(a)
            parts.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="11" fill="{text_color}" font-family="Inter,Outfit,sans-serif" font-weight="600">{label}</text>'
            )

        parts.append("</svg>")
        return "\n".join(parts)

    @staticmethod
    def _svg_hbars(items: list, title: str = "", unit_str: str = "", label_key: str = "label", value_key: str = "value") -> str:
        """Generate modern inline SVG horizontal bar chart from items list."""
        if not items:
            return ""

        import uuid
        uid = str(uuid.uuid4())[:8]

        bar_h = 24
        gap = 12
        left_margin = 130
        right_margin = 80
        chart_w = 400

        n = len(items)
        svg_h = n * (bar_h + gap) + gap + 40
        svg_w = left_margin + chart_w + right_margin

        vals = [item.get(value_key, 0) for item in items if isinstance(item.get(value_key), (int, float))]
        if not vals:
            return ""
        max_val = max(max(vals), 1)

        text_color = "#1e293b"
        label_color = "#475569"
        
        parts = [
            f'<svg viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%; display:block; background:#ffffff; border-radius:12px; border:1px solid #e2e8f0; padding: 10px; margin: 15px 0;">',
            '<defs>',
            f'  <linearGradient id="barGradient_{uid}" x1="0%" y1="0%" x2="100%" y2="0%">',
            '    <stop offset="0%" stop-color="#818CF8" />',
            '    <stop offset="100%" stop-color="#4F46E5" />',
            '  </linearGradient>',
            f'  <filter id="shadow_{uid}" x="-5%" y="-10%" width="120%" height="130%">',
            '    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#4F46E5" flood-opacity="0.15"/>',
            '  </filter>',
            '</defs>'
        ]

        y_offset = gap + 10
        if title:
            parts.append(
                f'<text x="{svg_w / 2:.0f}" y="20" text-anchor="middle" font-size="14" font-weight="700" fill="{text_color}" font-family="Inter,Outfit,sans-serif">{title}</text>'
            )
            y_offset += 24

        for i, item in enumerate(items):
            val = item.get(value_key, 0)
            if not isinstance(val, (int, float)):
                continue
            label = str(item.get(label_key, ""))[:18]
            y = y_offset + i * (bar_h + gap)

            bar_w = max(val / max_val * chart_w, 4) if max_val > 0 else 4

            # Label
            parts.append(
                f'<text x="{left_margin - 12}" y="{y + bar_h / 2 + 4:.0f}" text-anchor="end" font-size="12" font-weight="500" fill="{label_color}" font-family="Inter,Outfit,sans-serif">{label}</text>'
            )
            
            # Background track
            parts.append(
                f'<rect x="{left_margin}" y="{y:.0f}" width="{chart_w}" height="{bar_h}" rx="6" fill="#f1f5f9" />'
            )
            
            # The Bar
            parts.append(
                f'<rect x="{left_margin}" y="{y:.0f}" width="{bar_w:.1f}" height="{bar_h}" rx="6" fill="url(#barGradient_{uid})" filter="url(#shadow_{uid})">'
            )
            parts.append(
                f'  <animate attributeName="width" from="0" to="{bar_w:.1f}" dur="1s" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1" keyTimes="0;1"/>'
            )
            parts.append('</rect>')
            
            # Value text
            val_str = f"{int(val)}" if val == int(val) else f"{val:.2f}"
            parts.append(
                f'<text x="{left_margin + bar_w + 10:.0f}" y="{y + bar_h / 2 + 4:.0f}" font-size="12" fill="{text_color}" font-family="Inter,Outfit,sans-serif" font-weight="700">{val_str}</text>'
            )

        parts.append("</svg>")
        return "\n".join(parts)

    @staticmethod
    def _svg_vbars(items: list, title: str = "", unit_str: str = "", label_key: str = "label", value_key: str = "value") -> str:
        """Generate modern inline SVG vertical bar chart from items list."""
        if not items:
            return ""

        import uuid
        uid = str(uuid.uuid4())[:8]

        bar_w = 32
        gap = 32
        bottom_margin = 60
        top_margin = 60
        left_margin = 40
        right_margin = 40
        chart_h = 200

        n = len(items)
        svg_w = n * (bar_w + gap) + left_margin + right_margin - gap
        svg_h = top_margin + chart_h + bottom_margin

        vals = [item.get(value_key, 0) for item in items if isinstance(item.get(value_key), (int, float))]
        if not vals:
            return ""
        max_val = max(max(vals), 1)

        text_color = "#1e293b"
        label_color = "#475569"
        
        parts = [
            f'<svg viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%; display:block; background:#ffffff; border-radius:12px; border:1px solid #e2e8f0; padding: 10px; margin: 15px 0;">',
            '<defs>',
            f'  <linearGradient id="barGradient_{uid}" x1="0%" y1="100%" x2="0%" y2="0%">',
            '    <stop offset="0%" stop-color="#818CF8" />',
            '    <stop offset="100%" stop-color="#4F46E5" />',
            '  </linearGradient>',
            f'  <filter id="shadow_{uid}" x="-10%" y="-5%" width="130%" height="120%">',
            '    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#4F46E5" flood-opacity="0.15"/>',
            '  </filter>',
            '</defs>'
        ]

        if title:
            parts.append(
                f'<text x="{svg_w / 2:.0f}" y="25" text-anchor="middle" font-size="14" font-weight="700" fill="{text_color}" font-family="Inter,Outfit,sans-serif">{title}</text>'
            )

        x_offset = left_margin
        base_y = top_margin + chart_h

        for i, item in enumerate(items):
            val = item.get(value_key, 0)
            if not isinstance(val, (int, float)):
                continue
            
            # For x-axis labels, limit characters
            label = str(item.get(label_key, ""))
            if len(label) > 6:
                label = label[:5] + ".."
            
            x = x_offset + i * (bar_w + gap)

            bar_h_scaled = max(val / max_val * chart_h, 4) if max_val > 0 else 4
            y = base_y - bar_h_scaled

            # Label on X-axis (rotated if needed, but here simple horizontal or slight offset)
            parts.append(
                f'<text x="{x + bar_w / 2:.0f}" y="{base_y + 20:.0f}" text-anchor="middle" font-size="12" font-weight="500" fill="{label_color}" font-family="Inter,Outfit,sans-serif">{label}</text>'
            )
            
            # Background track
            parts.append(
                f'<rect x="{x:.0f}" y="{top_margin:.0f}" width="{bar_w}" height="{chart_h}" rx="6" fill="#f1f5f9" />'
            )
            
            # The Bar
            parts.append(
                f'<rect x="{x:.0f}" y="{y:.0f}" width="{bar_w}" height="{bar_h_scaled:.1f}" rx="6" fill="url(#barGradient_{uid})" filter="url(#shadow_{uid})">'
            )
            parts.append(
                f'  <animate attributeName="height" from="0" to="{bar_h_scaled:.1f}" dur="1s" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1" keyTimes="0;1"/>'
            )
            parts.append(
                f'  <animate attributeName="y" from="{base_y:.1f}" to="{y:.1f}" dur="1s" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1" keyTimes="0;1"/>'
            )
            parts.append('</rect>')
            
            # Value text
            val_str = f"{int(val)}" if val == int(val) else f"{val:.1f}"
            parts.append(
                f'<text x="{x + bar_w / 2:.0f}" y="{y - 8:.0f}" text-anchor="middle" font-size="12" fill="{text_color}" font-family="Inter,Outfit,sans-serif" font-weight="700">{val_str}</text>'
            )

        parts.append("</svg>")

    @staticmethod
    def _scenario_expected_price(scenarios) -> Optional[float]:
        """Probability-weighted target price from Bull/Base/Bear scenarios.

        Mirrors the renderer's expected-return math so the DCF deviation
        guard compares against the same blended target the report shows.
        """
        if not isinstance(scenarios, list) or not scenarios:
            return None
        exp_price = 0.0
        tot_prob = 0.0
        try:
            for s in scenarios:
                if not isinstance(s, dict):
                    continue
                p_str = str(s.get("probability", "0")).replace("%", "").strip()
                prob = float(p_str) if p_str else 0.0
                t_str = (str(s.get("targetPrice", "0"))
                         .replace("元", "").replace("HKD", "").replace("USD", "")
                         .replace("¥", "").replace("CNY", "").strip())
                if "-" in t_str:
                    parts = t_str.split("-")
                    t_val = (float(parts[0]) + float(parts[1])) / 2.0
                else:
                    t_val = float(t_str) if t_str else 0.0
                exp_price += t_val * (prob / 100.0)
                tot_prob += prob
            if tot_prob > 0 and exp_price > 0:
                if abs(tot_prob - 100) > 1:
                    exp_price = exp_price / (tot_prob / 100.0)
                return exp_price
        except (TypeError, ValueError):
            return None
        return None

    def _compute_valuation(self, snapshot: dict, info: dict) -> dict:
        """Compute WACC and DCF target price from snapshot fundamentals.

        合理性边界（触发条件 → 行为）：
          β 输入 <0.2 或 >3.0        → 钳制到 [0.2, 3.0]，记入 sanity_warnings
          Rf                         → 优先 snapshot 实时 rf（provider 同源），缺省用市场默认并标注来源
          WACC < max(Rf+2%, 5%)      → 钳制到下限并标注"WACC 低于合理性下限，已钳制"
          g                          → min(5%默认, Rf, WACC−2%)；WACC−2% ≤ 0 时拒绝 DCF
          WACC − g < 2%（防御守卫）    → 拒绝输出 DCF（dcf_skip_reason），绝不用 clamp 硬算出爆炸值
          DCF vs 综合目标价偏离 >2 倍  → deviation_warning 警示字段随估值输出渲染

        Returns dict with keys: rf, beta, erp, kd, tc, d_v, e_v, wacc,
        source, sensitivity, sanity_warnings, and optionally dcf_target /
        dcf_skip_reason / deviation_warning.
        Returns empty dict if critical inputs are missing.
        """
        if not isinstance(snapshot, dict):
            return {}

        v: dict = snapshot.get("valuation") or {}
        f: dict = snapshot.get("financials") or {}
        q: dict = snapshot.get("quote") or {}

        def _get(*keys):
            sources = [v, f, q]
            for k in keys:
                for s in sources:
                    val = s.get(k)
                    if val is not None:
                        return val
            return None

        sanity_warnings: List[str] = []

        # Risk-free rate — prefer the provider's real-time rf (financials.rf,
        # written by a_stock_direct next to its own WACC estimate) so both
        # layers share one source. A-Share fallback renders the LIVE China
        # 10Y yield (same provider function, TTL-cached) instead of a stale
        # hardcoded constant; US/HK use market-benchmark defaults.
        rf_val = _get("riskFreeRate", "rf")
        if rf_val is not None and isinstance(rf_val, (int, float)):
            rf = rf_val / 100 if rf_val > 1 else rf_val
            rf_label = "provider 实时"
        else:
            market = info.get("market", "US-Share")
            if market in ("US-Share", "us"):
                rf = US_RISK_FREE_DEFAULT
                rf_label = "市场基准默认"
            elif market in ("HK-Share", "hk"):
                rf = HK_RISK_FREE_DEFAULT
                rf_label = "市场基准默认"
            else:
                # A-Share：直取 provider 的实时中债 10Y（TTL 缓存）；网络失败
                # 时函数内部回退配置兑底值，此处再防御一次取值合理性。
                try:
                    rf = float(_get_cn_risk_free_rate())
                    rf_label = "provider 实时（渲染层直取）"
                except Exception:
                    rf = CN_RISK_FREE_FALLBACK
                    rf_label = "市场基准默认"
                if not (isinstance(rf, float) and 0 < rf < 0.10):
                    rf = CN_RISK_FREE_FALLBACK
                    rf_label = "市场基准默认"

        # Beta — clamp to a sane equity-beta range before CAPM. The provider
        # already applies Blume shrinkage; this is defense-in-depth for stale
        # caches or snapshots from other providers.
        beta_val = _get("beta")
        if beta_val is not None and isinstance(beta_val, (int, float)) and beta_val > 0:
            beta = float(beta_val)
        else:
            beta = 1.1  # default equity beta
        if beta < _VALUATION_BETA_FLOOR:
            sanity_warnings.append(
                f"输入 β={beta:.2f} 低于合理下限，已钳制为 {_VALUATION_BETA_FLOOR:.1f}")
            beta = _VALUATION_BETA_FLOOR
        elif beta > _VALUATION_BETA_CEILING:
            sanity_warnings.append(
                f"输入 β={beta:.2f} 高于合理上限，已钳制为 {_VALUATION_BETA_CEILING:.1f}")
            beta = _VALUATION_BETA_CEILING

        # β provenance disclosure (provider-side Blume adjustment / confidence)
        beta_raw_val = _get("beta_raw")
        beta_note = ""
        if (isinstance(beta_raw_val, (int, float))
                and abs(float(beta_raw_val) - beta) >= 0.005):
            beta_note = f"原始回归 {float(beta_raw_val):.2f}，经 Blume 调整与下限保护"
        if _get("beta_low_confidence"):
            beta_note = (beta_note + "，低置信") if beta_note else "低置信（回归质量不足）"

        # ERP (equity risk premium) — single definition point shared with the
        # provider-side WACC estimate (data_providers/a_stock_direct).
        erp = EQUITY_RISK_PREMIUM

        # Ke = Rf + beta * ERP
        ke = rf + beta * erp

        # Cost of debt
        kd_val = _get("costOfDebt", "kd")
        if kd_val is not None and isinstance(kd_val, (int, float)):
            kd = kd_val / 100 if kd_val > 1 else kd_val
        else:
            kd = DEFAULT_COST_OF_DEBT  # 4%：与 provider 侧 WACC 估算同源（valuation_config）

        # Tax rate
        tc_val = _get("taxRate", "tc")
        if tc_val is not None and isinstance(tc_val, (int, float)):
            tc = tc_val / 100 if tc_val > 1 else tc_val
        else:
            market_str = info.get("market", "US-Share")
            if market_str in ("US-Share", "us"):
                tc = 0.21
            elif market_str in ("HK-Share", "hk"):
                tc = 0.165
            else:
                tc = 0.25  # China statutory rate

        # D/V and E/V
        total_debt = _get("totalDebt")
        market_cap = _get("marketCap")
        d_v_label = "默认假设 (无资产负债表明细)"
        if (
            total_debt is not None
            and isinstance(total_debt, (int, float))
            and total_debt > 0
            and market_cap is not None
            and isinstance(market_cap, (int, float))
            and market_cap > 0
        ):
            ev = market_cap + total_debt
            d_v = total_debt / ev
            e_v = market_cap / ev
            d_v_label = f"从资产负债推导 (D≈{total_debt/1e8:.1f}亿, E≈{market_cap/1e8:.1f}亿)"
        else:
            d_v = 0.3
            e_v = 0.7

        # WACC — floored to a commercially sane level: a discount rate below
        # max(Rf + 2%, 5%) makes the Gordon terminal value explode.
        wacc_raw = e_v * ke + d_v * kd * (1 - tc)
        wacc = wacc_raw
        wacc_floor = max(rf + _VALUATION_WACC_FLOOR_MARGIN, _VALUATION_WACC_FLOOR_ABS)
        if wacc < wacc_floor:
            sanity_warnings.append(
                f"计算 WACC={wacc_raw*100:.2f}% 低于合理性下限 {wacc_floor*100:.1f}%，已钳制")
            wacc = wacc_floor

        # DCF target price
        fcf = _get("freeCashflow")
        if fcf is None or not isinstance(fcf, (int, float)):
            ocf = _get("operatingCashflow")
            capex = _get("capitalExpenditure")
            if ocf is not None and capex is not None and isinstance(ocf, (int, float)) and isinstance(capex, (int, float)):
                fcf = ocf - abs(capex) if ocf > 0 else None

        dcf_target = None
        dcf_skip_reason = None
        g = None
        if fcf is not None and isinstance(fcf, (int, float)) and fcf > 0 and wacc > 0:
            # Perpetual growth must respect: the long-run nominal cap (5%),
            # Rf (nominal growth anchor) and a minimum WACC−g spread of 2%.
            g_ceiling = wacc - _VALUATION_MIN_SPREAD
            if g_ceiling <= 0:
                dcf_skip_reason = "输入参数不满足 DCF 合理性约束（WACC-g 利差不足），已跳过 DCF 估值"
            else:
                g = min(0.05, rf, g_ceiling)
                if wacc - g < _VALUATION_MIN_SPREAD:
                    # Defensive: unreachable while g ≤ wacc − spread, but never
                    # clamp-override into an exploding Gordon terminal value.
                    dcf_skip_reason = "输入参数不满足 DCF 合理性约束（WACC-g 利差不足），已跳过 DCF 估值"
                    g = None
                else:
                    try:
                        intrinsic_value = fcf * (1 + g) / (wacc - g)
                    except ZeroDivisionError:
                        intrinsic_value = None
                    if intrinsic_value is not None:
                        shares = _get("sharesOutstanding", "shares", "impliedShares")
                        price = q.get("price") or info.get("price")
                        if shares is not None and isinstance(shares, (int, float)) and shares > 0:
                            dcf_target = intrinsic_value / shares
                        elif market_cap is not None and price is not None and isinstance(price, (int, float)) and price > 0:
                            dcf_target = intrinsic_value / market_cap * price
                        if dcf_target is not None:
                            dcf_target = round(dcf_target, 2)

        # Deviation guard: DCF target vs the report's probability-weighted
        # target price (scenarios) — flag >2x divergence instead of silently
        # publishing an exploding DCF number next to a sane blended target.
        deviation_warning = None
        ref_target = info.get("ref_target_price")
        if dcf_target is not None and isinstance(ref_target, (int, float)) and ref_target > 0:
            ratio = dcf_target / float(ref_target)
            if ratio > 2 or ratio < 0.5:
                deviation_warning = (
                    f"⚠ DCF 估值 {dcf_target:.2f} 与综合目标价 {ref_target:.2f} 偏离超 2 倍"
                    f"（{ratio:.1f}x），请核查参数假设")

        source_parts = [
            f"Rf={rf*100:.1f}% ({rf_label})",
            f"β={beta:.2f}" + (f"（{beta_note}）" if beta_note else ""),
            f"ERP={erp*100:.1f}%",
            f"Ke=Rf+β×ERP={ke*100:.1f}%",
            f"Kd={kd*100:.1f}%",
            f"Tc={tc*100:.0f}%",
            f"D/V={d_v*100:.0f}% ({d_v_label})",
            f"E/V={e_v*100:.0f}%",
            f"WACC=E/V×Ke+D/V×Kd×(1-Tc)={wacc*100:.2f}%",
        ]
        if g is not None:
            source_parts.append(f"g={g*100:.2f}% (≤min(5%, Rf, WACC-2%))")
        # 口径披露：本表为报告层独立复算，与数据源快照的 provider WACC 估算
        # （时点/资本结构口径可能不同）并列披露，两套数值永不静默混用。
        wacc_basis = "口径：本表为报告层独立复算 WACC"
        provider_wacc = _get("wacc")
        if isinstance(provider_wacc, (int, float)):
            pw = provider_wacc / 100 if provider_wacc > 1 else float(provider_wacc)
            if 0 < pw < 0.5:
                wacc_basis += f"；数据源快照 WACC 估算={pw*100:.2f}%（口径/时点可能不同）"
        source_parts.append(wacc_basis)

        result: dict = {
            "rf": f"{rf*100:.2f}%",
            "beta": f"{beta:.2f}",
            "erp": f"{erp*100:.1f}%",
            "kd": f"{kd*100:.1f}%",
            "tc": f"{tc*100:.0f}%",
            "d_v": f"{d_v*100:.1f}%",
            "e_v": f"{e_v*100:.1f}%",
            "wacc": f"{wacc*100:.2f}%",
            "source": "; ".join(source_parts),
            "sensitivity": "",
            "sanity_warnings": sanity_warnings,
        }

        if dcf_skip_reason:
            result["dcf_skip_reason"] = dcf_skip_reason
        if deviation_warning:
            result["deviation_warning"] = deviation_warning
        if dcf_target is not None:
            currency = info.get("currency", "CNY")
            result["dcf_target"] = f"{dcf_target} {currency}"

        return result

    def _render_html(self, d: dict) -> str:
        info = d["info"]
        fund = d["fund"]
        chg = info["changePercent"]
        chg_color = "#ef4444" if chg < 0 else "#10b981"
        chg_sign = "+" if chg > 0 else ""
        locale = self._get_locale(info.get("market", "A-Share"))

        def md(t): return self._postprocess_markdown(markdown2.markdown(self._preprocess_chinese_bold(t), safe_mode="escape")) if t else ""
        import html
        def esc(t): return html.escape(str(t)) if t else ""
        cur = info.get("currency", "CNY")
        def money_v(val, c=None):
            cu = c or cur
            if val is None or not isinstance(val, (int, float)): return "N/A"
            if abs(val) >= 1e12: return f"{round(val/1e12, 2)}万亿 {cu}"
            if abs(val) >= 1e8: return f"{round(val/1e8, 2)}亿 {cu}"
            if abs(val) >= 1e6: return f"{round(val/1e6, 2)}百万 {cu}"
            return f"{round(val, 2)} {cu}"

        # Raw variable extractions with safe defaults
        GARBAGE_VALUES = {"---", "—", "N/A", "n/a", "TBD", "tbd", "TODO", "todo", "None", "null", ""}

        # ── Render-time markdown-dump defense ──
        # LLM fields may still contain raw markdown documents (the model copying a
        # whole expert report into a field). Strip dumps to plain prose so no raw
        # '# 🔬 …' / table markup is ever interpolated into the HTML.
        d = dict(d)  # shallow copy: do not mutate the caller's dict
        for _f in ("key_opps", "key_risks", "moat_points", "macro_points", "risks_points", "trading_steps"):
            if not isinstance(d.get(_f), list):
                d[_f] = []
        for _f in ("key_opps", "key_risks", "moat_points", "macro_points", "risks_points"):
            _items = d.get(_f)
            if isinstance(_items, list):
                d[_f] = [self._render_prose(str(i), max_len=200) if isinstance(i, str) else i for i in _items]
        for _f in ("moat_summary", "macro_summary", "trading_plan", "summary", "investment_thesis"):
            _v = d.get(_f)
            if isinstance(_v, str) and self._looks_like_markdown_dump(_v):
                d[_f] = self._sanitize_markdown_field(_v, max_len=800)

        tagline = self._render_prose(d.get("tagline") or f"{info.get('name', '')} ({info.get('symbol', '')}) 投资分析报告", max_len=120)
        if str(tagline).strip() in GARBAGE_VALUES or len(str(tagline).strip()) < 5:
            tagline = f"{info.get('name', '')} ({info.get('symbol', '')}) 深度投资分析报告"

        verdict = self._render_prose(d.get("verdict", ""), max_len=120)
        if str(verdict).strip() in GARBAGE_VALUES or len(str(verdict).strip()) < 5:
            verdict = ""

        rec = d.get("recommendation", "WATCH")
        rec_lower = rec.lower() if rec else "hold"
        rec_class = "buy" if rec_lower in ("buy", "strong buy") else ("sell" if rec_lower in ("sell", "strong sell") else "hold")
        verdict_html = ""
        if verdict:
            verdict_html = f'<div class="verdict-banner"><span class="verdict-text">{esc(verdict)}</span><span class="verdict-rec {rec_class}">{esc(rec)}</span></div>'
        
        action_stance = self._render_prose(d.get("action_stance", ""), max_len=200)
        action_html = f'<div class="action-stance">{esc(action_stance)}</div>' if action_stance else ""

        # 1-Pager Dashboard Elements
        thesis_raw = d.get("investment_thesis") or d.get("summary") or "分析整理中..."
        # Safety net: truncate thesis if still too long (prevents markdown document dumps)
        if len(thesis_raw) > 500:
            # Take first 500 chars and find a sentence boundary
            truncated = thesis_raw[:500]
            last_period = max(truncated.rfind('。'), truncated.rfind('. '), truncated.rfind('！'), truncated.rfind('?'))
            thesis = truncated[:last_period + 1] if last_period > 100 else truncated + "..."
        else:
            thesis = thesis_raw
        thesis = self._render_prose(thesis, max_len=500)
        factor = d.get("factor_profile") or {}
        factor_scores = d.get("factor_scores") or {}
        factor_radar_html = self._svg_radar(factor_scores) if factor_scores else ""
        consensus = d.get("consensus_vs_non_consensus") or {}
        if isinstance(consensus, dict):
            consensus = {k: self._render_prose(v, max_len=300) for k, v in consensus.items() if isinstance(v, str)}
        the_call_raw = d.get("the_call") or verdict or "暂无明确决断建议"
        the_call = the_call_raw if str(the_call_raw).strip() not in GARBAGE_VALUES and len(str(the_call_raw).strip()) >= 5 else "暂无明确决断建议"
        the_call = self._render_prose(the_call, max_len=200)
        evidence_taxonomy_html = self._render_evidence_taxonomy(d, info, thesis, verdict, rec, the_call)
        
        # Catalyst Calendar
        catalysts = d.get("catalyst_calendar") or []
        catalyst_html = ""
        if catalysts and isinstance(catalysts, list):
            cat_rows = "".join([
                f'<tr><td><span class="calendar-date">{esc(self._render_prose(c.get("date", "N/A"), 60))}</span></td><td><strong>{esc(self._render_prose(c.get("event", "N/A"), 120))}</strong></td><td>{esc(self._render_prose(c.get("impact_logic", ""), 200))}</td></tr>'
                for c in catalysts if isinstance(c, dict)
            ])
            if cat_rows:
                catalyst_html = f'''
                <div class="dashboard-card calendar-card">
                    <h3 class="card-title">📅 催化剂事件日历 (Catalyst Calendar)</h3>
                    <table class="calendar-table">
                        <thead><tr><th>预计时间</th><th>事件描述</th><th>对策略影响逻辑</th></tr></thead>
                        <tbody>{cat_rows}</tbody>
                    </table>
                </div>
                '''

        # Data completeness warning
        dc = d.get("data_completeness", {})
        dc_score = dc.get("score", 100) if isinstance(dc, dict) else 100
        dc_missing = dc.get("missing", []) if isinstance(dc, dict) else []
        dc_impact = dc.get("impact", "") if isinstance(dc, dict) else ""
        data_warning_html = ""
        if dc_score < 100 and dc_missing:
            bar_class = "high" if dc_score >= 80 else ("medium" if dc_score >= 60 else "low")
            missing_str = "、".join(dc_missing[:5])
            data_warning_html = f'''<div class="data-warning">
                <div class="data-warning-header">数据完整度: {dc_score}%</div>
                <div class="data-bar"><div class="data-bar-fill {bar_class}" style="width:{dc_score}%"></div></div>
                <div>缺失关键数据: {missing_str}</div>
                {f'<div style="margin-top:4px;color:#b45309;">影响: {dc_impact}</div>' if dc_impact else ''}
            </div>'''

        integrity_warn = d.get("data_integrity_warning", "")
        integrity_html = ""
        if integrity_warn:
            integrity_html = f'<div class="integrity-warning" style="background:#fef2f2;border:1px solid #ef4444;color:#b91c1c;padding:10px 14px;border-radius:8px;margin:8px 0;font-weight:600;">{esc(integrity_warn)}</div>'

        # Adaptive Valuation Panel
        archetype = d.get("stock_archetype") or ""
        archetype_zh = {
            "Cyclical": "强周期型 (Cyclical)",
            "Growth": "高成长型 (Growth)",
            "Dividend": "稳健红利型 (Dividend)",
            "Consumer/Moat": "消费/护城河型 (Consumer/Moat)",
            "Financial": "金融股 (Financial)",
            "Biotech": "创新药/生物科技 (Biotech)"
        }.get(archetype, archetype or "通用分析型")
        
        kill_switch = d.get("kill_switch") or {}
        ks_condition = esc(self._render_prose(kill_switch.get("condition") or "分析师未配置具体防伪红线条件", 200))
        ks_status = kill_switch.get("status") or "SAFE"
        ks_class = "triggered" if ks_status.upper() in ("TRIGGERED", "WARN", "触发") else "safe"
        ks_status_zh = "已触发预警 (TRIGGERED)" if ks_class == "triggered" else "安全 (SAFE)"
        
        # WACC Breakdown Table
        wacc_data = d.get("wacc_breakdown") or {}
        wacc_table_html = ""
        if wacc_data and isinstance(wacc_data, dict) and wacc_data.get("wacc"):
            # 显著警示框（不依赖 Reviewer 文本兜底）：β/WACC 极端值、DCF 拒绝、
            # DCF 与综合目标价偏离 >2x —— 估值模块自身在报告内强制显著提示。
            _val_alerts = [str(w) for w in (wacc_data.get("sanity_warnings") or [])]
            if wacc_data.get("dcf_skip_reason"):
                _val_alerts.append(str(wacc_data["dcf_skip_reason"]))
            if wacc_data.get("deviation_warning"):
                _val_alerts.append(str(wacc_data["deviation_warning"]))
            _val_alert_html = ""
            if _val_alerts:
                _val_alert_items = "".join(f"<li>{esc(a)}</li>" for a in _val_alerts)
                _val_alert_html = (
                    '<div class="valuation-alert-box" role="alert">'
                    '<div class="valuation-alert-title">⚠ 估值合理性警示</div>'
                    f'<ul>{_val_alert_items}</ul>'
                    '</div>'
                )
            wacc_table_html = f'''
            {_val_alert_html}
            <table class="wacc-table">
                <thead>
                    <tr>
                        <th>Rf (无风险利率)</th>
                        <th>Beta (贝塔系数)</th>
                        <th>ERP (股权溢价)</th>
                        <th>Kd (债务成本)</th>
                        <th>Tc (所得税率)</th>
                        <th>D/V (负债比)</th>
                        <th>E/V (权益比)</th>
                        <th>WACC (贴现率)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>{wacc_data.get("rf", "N/A")}</td>
                        <td>{wacc_data.get("beta", "N/A")}</td>
                        <td>{wacc_data.get("erp", "N/A")}</td>
                        <td>{wacc_data.get("kd", "N/A")}</td>
                        <td>{wacc_data.get("tc", "N/A")}</td>
                        <td>{wacc_data.get("d_v", "N/A")}</td>
                        <td>{wacc_data.get("e_v", "N/A")}</td>
                        <td><strong>{wacc_data.get("wacc", "N/A")}</strong></td>
                    </tr>
                    <tr>
                        <td colspan="8" class="wacc-source"><strong>WACC 参数来源与逻辑：</strong> {wacc_data.get("source", "未披露")}</td>
                    </tr>
                    {"<tr><td colspan='8' class='wacc-source'><strong>敏感性分析：</strong></td></tr><tr><td colspan='8' class='wacc-source'>" + markdown2.markdown(self._format_sensitivity_table(wacc_data.get("sensitivity", "")), extras=["tables"]) + "</td></tr>" if wacc_data.get("sensitivity") else ""}
                    {"<tr><td colspan='8' class='wacc-source'><strong>DCF 每股目标价：</strong> " + esc(str(wacc_data.get("dcf_target", "N/A"))) + (" <span style='color:#ef4444; font-weight:600;'>" + esc(str(wacc_data.get("deviation_warning"))) + "</span>" if wacc_data.get("deviation_warning") else "") + "</td></tr>" if wacc_data.get("dcf_target") else ""}
                    {"<tr><td colspan='8' class='wacc-source' style='color:#ef4444;'><strong>" + esc(str(wacc_data.get("dcf_skip_reason"))) + "</strong></td></tr>" if wacc_data.get("dcf_skip_reason") else ""}
                    {"<tr><td colspan='8' class='wacc-source' style='color:#b45309;'><strong>合理性警示：</strong> " + esc("；".join(wacc_data.get("sanity_warnings") or [])) + "</td></tr>" if wacc_data.get("sanity_warnings") else ""}
                </tbody>
            </table>
            '''
        else:
            wacc_table_html = '<div class="no-data-msg">本期分析未应用DCF模型折现，或WACC参数由评审专家判定为不适用/未披露。</div>'

        # Peer comparison table
        peers = d.get("peer_comparison", [])
        peer_section_html = ""
        peer_chart_html = ""
        flow_section_html = ""
        # Fundamentals live inside the snapshot, not in the top-level data dict.
        _snapshot = d.get("snapshot", {}) or {}
        financials = _snapshot.get("financials", {}) or {}
        valuation = _snapshot.get("valuation", {}) or {}
        quote = _snapshot.get("quote", {}) or {}
        
        if peers and isinstance(peers, list) and len(peers) > 0:
            target_name = info.get("longName") or info.get("shortName") or "本公司"
            def _cn(val):
                if isinstance(val, (int, float)): return val
                if isinstance(val, str):
                    try: return float(val.replace("%", "").replace(",", "").replace("亿", "").strip())
                    except: return val
                return val

            t_roe = _cn(financials.get("roe") or valuation.get("roe") or valuation.get("ROE") or "N/A")
            if isinstance(t_roe, (int, float)) and -1.0 <= t_roe <= 1.0 and not valuation.get("ROE"): t_roe *= 100
            
            t_margin = _cn(financials.get("net_margin") or financials.get("profitMargins") or "N/A")
            if isinstance(t_margin, (int, float)) and -1.0 <= t_margin <= 1.0: t_margin *= 100

            t_mc = _cn(financials.get("marketCap") or valuation.get("market_cap") or valuation.get("总市值") or quote.get("marketCap") or info.get("marketCap") or "N/A")
            if isinstance(t_mc, (int, float)) and t_mc > 1e7: t_mc /= 1e8

            target_peer = {
                "name": f"🌟 {target_name}",
                "symbol": info.get("symbol", ""),
                "pe": _cn(financials.get("pe") or valuation.get("pe") or valuation.get("市盈率(动)") or valuation.get("PE") or quote.get("trailingPE") or info.get("trailingPE") or "N/A"),
                "pb": _cn(financials.get("pb") or valuation.get("pb") or valuation.get("市净率") or valuation.get("PB") or quote.get("pb") or info.get("priceToBook") or "N/A"),
                "roe": t_roe,
                "margin": t_margin,
                "marketCap": t_mc,
                "vs_target": "当前分析标的 (Target)"
            }
            
            def _normalize_sym(s):
                if not s: return ""
                return str(s).upper().replace(".HK", "").replace(".SZ", "").replace(".SH", "").replace(".SS", "").replace(".US", "").strip()
                
            target_sym_norm = _normalize_sym(info.get("symbol"))
            peers = [target_peer] + [p for p in peers if _normalize_sym(p.get("symbol")) != target_sym_norm]

            peer_rows = ""
            def _fv(v, suffix=""):
                if v is None or v == "N/A": return "N/A"
                return f"{v}{suffix}"
            def _alt(p, *keys):
                # Accept multiple key spellings (LLM emits descriptive names like
                # net_margin_pct / market_cap_cny_bn / roe_fy2025_pct / pe_ttm)
                for k in keys:
                    v = p.get(k)
                    if v is not None and str(v).strip().upper() not in ["N/A", "NONE", "NULL"]:
                        return v
                return None
            for p in peers:
                if not isinstance(p, dict): continue
                mc = _alt(p, "marketCap", "market_cap_cny_bn", "market_cap")
                if isinstance(mc, (int, float)):
                    mc = f"{mc}亿"  # market_cap_cny_bn is in 亿元
                
                s_name = p.get("name") or p.get("company")
                s_sym = p.get("symbol")
                s_vs = p.get("vs_target") or p.get("rationale")
                
                peer_rows += f'''<tr>
                    <td>{esc(self._render_prose(s_name if s_name else "N/A", 40))}</td>
                    <td>{esc(self._render_prose(s_sym if s_sym else "N/A", 30))}</td>
                    <td>{_fv(_alt(p, "pe", "pe_ttm"))}</td>
                    <td>{_fv(_alt(p, "pb"))}</td>
                    <td>{_fv(_alt(p, "roe", "roe_fy2025_pct"), "%")}</td>
                    <td>{_fv(_alt(p, "margin", "net_margin_pct", "net_margin"), "%")}</td>
                    <td>{_fv(mc)}</td>
                    <td>{esc(self._render_prose(s_vs if s_vs else "N/A", 150))}</td>
                </tr>'''
            peer_section_html = f'''
            <div class="comps-wrapper">
                <h3 class="comps-title">📊 行业可比公司对标 (Comps Peer Comparison)</h3>
                <div class="comps-desc">注：可比公司中位数已执行离群值（如亏损公司及极端估值）剔除过滤</div>
                <table class="peer-table">
                    <thead><tr><th>公司</th><th>代码</th><th>PE</th><th>PB</th><th>ROE</th><th>净利率</th><th>市值</th><th>对标评价</th></tr></thead>
                    <tbody>{peer_rows}</tbody>
                </table>
            </div>'''
            # Peer chart
            chart_items = []
            for p in peers:
                if not isinstance(p, dict):
                    continue
                name = p.get("name") or p.get("company", "N/A")
                roe_val = _alt(p, "roe", "roe_fy2025_pct")
                if roe_val is not None and isinstance(roe_val, (int, float)):
                    chart_items.append({"label": str(name), "value": float(roe_val)})
                else:
                    pe_val = _alt(p, "pe", "pe_ttm")
                    if pe_val is not None and isinstance(pe_val, (int, float)):
                        chart_items.append({"label": str(name), "value": float(pe_val)})
            if chart_items:
                peer_chart_html = self._svg_vbars(chart_items, title="可比公司 ROE/PE 对比")

        # Flow & Positioning card (北向资金 + 茅台批价)
        nb = d.get("northbound") or {}
        bp = d.get("baijiu_price") or {}
        has_nb = isinstance(nb, dict) and nb.get("latest_hold_pct") is not None
        has_bp = isinstance(bp, dict) and bp.get("price") is not None
        if has_nb or has_bp:
            flow_rows = ""
            if has_nb:
                hold_pct = nb.get("latest_hold_pct")
                if hold_pct is not None and isinstance(hold_pct, (int, float)):
                    flow_rows += f'<tr><td>{locale["label_northbound_hold"]}</td><td><strong>{round(float(hold_pct), 2)}%</strong></td></tr>'
                inflow_5d = nb.get("five_day_net_inflow")
                if inflow_5d is not None and isinstance(inflow_5d, (int, float)):
                    sign = "+" if inflow_5d > 0 else ""
                    flow_rows += f'<tr><td>{locale["label_northbound_5d"]}</td><td><strong style="color:{"#10b981" if inflow_5d > 0 else "#ef4444"}">{sign}{money_v(inflow_5d)}</strong></td></tr>'
                trend = nb.get("five_day_trend")
                if trend:
                    trend_color = "#10b981" if "流入" in str(trend) else "#ef4444"
                    flow_rows += f'<tr><td>{locale["label_northbound_trend"]}</td><td><strong style="color:{trend_color}">{esc(trend)}</strong></td></tr>'
            if has_bp:
                bp_price = bp.get("price")
                bp_unit = bp.get("unit", "")
                bp_as_of = bp.get("as_of", "")
                if bp_price is not None:
                    bp_str = f"{bp_price} {bp_unit}" if bp_unit else str(bp_price)
                    if bp_as_of:
                        bp_str += f" <span style='font-size:11px;color:#94a3b8;'>({esc(bp_as_of)})</span>"
                    flow_rows += f'<tr><td>{locale["label_baijiu_price"]}</td><td><strong>{bp_str}</strong></td></tr>'
            if not flow_rows:
                flow_rows = f'<tr><td colspan="2" style="color:#94a3b8;font-style:italic;">{locale["label_no_northbound"]}</td></tr>'
            flow_section_html = f'''
        <section class="section">
            <h2 class="section-title">{locale["card_flow_positioning"]}</h2>
            <div class="dashboard-grid">
                <div class="dashboard-card full-width">
                    <table class="fund-table">
                        <thead><tr><th>指标</th><th>数值</th></tr></thead>
                        <tbody>{flow_rows}</tbody>
                    </table>
                </div>
            </div>
        </section>'''

        # Categorized Metrics
        categories = [
            {
                "title": locale["cat_valuation"],
                "metrics": [
                    ("总市值", "Market Cap"),
                    ("企业价值 (EV)", "含债务的真实估值"),
                    ("净利润", "最近一期净利润"),
                    ("扣非净利润", "剔除非经常损益后净利润"),
                    ("市盈率 (PE)", "TTM市盈率"),
                    ("市净率 (PB)", "资产价格倍数"),
                    ("PEG", "判断估值是否被成长性消化"),
                    ("市销率 (PS)", "对亏损或周期行业很关键"),
                    ("EV/EBITDA", "比PE更抗财务操纵")
                ]
            },
            {
                "title": locale["cat_profitability"],
                "metrics": [
                    ("净资产收益率 (ROE)", "股东核心报酬率"),
                    ("总资产收益率 (ROA)", "资产利用效率"),
                    ("毛利率", "产品竞争力"),
                    ("营业利润率", "主营获利能力"),
                    ("净利率", "最终盈利水平"),
                    ("每股收益 (EPS)", "单股盈利额")
                ]
            },
            {
                "title": locale["cat_growth"],
                "metrics": [
                    ("营业总收入", "绝对收入规模"),
                    ("营收同比增长 (YoY)", "收入扩张速度"),
                    ("营收同比-单季 (YoY-Q)", "近期经营动能"),
                    ("营收环比增长 (QoQ)", "近期经营动能"),
                    ("净利润同比增长 (YoY)", "盈利增长速度"),
                    ("净利润环比增长 (QoQ)", "近期盈利弹性"),
                    ("扣非净利润同比增长 (YoY)", "核心业务增长"),
                    ("扣非净利润环比增长 (QoQ)", "核心业务动能"),
                    ("营收3年复合增长 (CAGR)", "长期成长稳定性"),
                    ("净利润3年复合增长 (CAGR)", "长期获利稳定性")
                ]
            },
            {
                "title": locale["cat_financial_health"],
                "metrics": [
                    ("资产负债率", "财务杠杆水平"),
                    ("流动比率", "短期偿债能力"),
                    ("速动比率", "极致变现偿债能力"),
                    ("总有息负债", "刚性债务负担"),
                    ("净现金", "现金减债后的缓冲垫")
                ]
            },
            {
                "title": locale["cat_cashflow"],
                "metrics": [
                    ("总现金(含短投)", "账面现金弹药"),
                    ("经营现金流", "主营吸金能力"),
                    ("自由现金流 (FCF)", "可分配现金"),
                    ("资本开支 (CAPEX)", "再投资力度"),
                    ("分红率", "股东回报慷慨度"),
                    ("股息率", "现金收益率")
                ]
            },
            {
                "title": locale["cat_ownership"],
                "metrics": [
                    ("大股东持股", "管理层利益绑定"),
                    ("机构持仓", "聪明钱认可度")
                ]
            },
            {
                "title": locale["cat_efficiency"],
                "metrics": [
                    ("总资产周转率", "资产变现速度"),
                    ("存货周转率", "库存周转效率")
                ]
            },
            {
                "title": locale["cat_market"],
                "metrics": [
                    ("股价百分位 (52周)", "当前价格在年度区间的位次"),
                    ("PE百分位", "当前估值在历史区间的位次"),
                    ("贝塔系数 (β)", "相对市场的波动弹性"),
                    ("WACC (估算)", "加权平均资本成本"),
                    ("涨跌幅", "当日涨跌幅")
                ]
            }
        ]

        detailed_fund_html = ""
        for cat in categories:
            items_html = "".join([
                self._render_fund_item(k, desc, fund.get(k, "N/A"))
                for k, desc in cat["metrics"]
                if k in fund and str(fund.get(k)) not in ("N/A", "", "None")  # Skip missing
            ])
            if items_html:
                detailed_fund_html += f"""
                <div class="fund-category">
                    <div class="fund-category-title">{cat['title']}</div>
                    <div class="fund-category-grid">{items_html}</div>
                </div>"""

        # Scenarios
        scenarios = d.get("scenarios", [])
        if not isinstance(scenarios, list) or (len(scenarios) > 0 and not isinstance(scenarios[0], dict)):
            scenarios = self._default_scenarios()

        sc_rows = "".join([
            f'<tr><td><strong>{esc(self._render_prose(s.get("case", "N/A"), 40))}</strong></td><td>{str(s.get("probability", 0)).rstrip("%")}%</td><td><strong>{esc(self._render_prose(s.get("targetPrice", "N/A"), 40))}</strong></td><td>{esc(self._render_prose(s.get("logic", ""), 200))}</td></tr>'
            for s in scenarios
        ])

        expected_return_html = ""
        try:
            current_price = d.get("snapshot", {}).get("quote", {}).get("price")
            if current_price and current_price > 0:
                exp_price = 0.0
                tot_prob = 0.0
                for s in scenarios:
                    p_str = str(s.get("probability", "0")).replace("%", "").strip()
                    prob = float(p_str) if p_str else 0.0
                    
                    t_str = str(s.get("targetPrice", "0")).replace("元", "").replace("HKD", "").replace("USD", "").replace("¥", "").strip()
                    if "-" in t_str:
                        parts = t_str.split("-")
                        t_val = (float(parts[0]) + float(parts[1])) / 2.0
                    else:
                        t_val = float(t_str) if t_str else 0.0
                        
                    exp_price += t_val * (prob / 100.0)
                    tot_prob += prob
                
                if tot_prob > 0 and exp_price > 0:
                    if abs(tot_prob - 100) > 1:
                        exp_price = exp_price / (tot_prob / 100.0)
                    exp_ret = (exp_price / current_price - 1.0) * 100
                    color = "var(--bull)" if exp_ret > 0 else "var(--bear)"
                    expected_return_html = f'<div style="margin-top: 10px; font-weight: bold; font-size: 14px; text-align: right;">概率加权期望目标价: {exp_price:.2f} 现价({current_price}) 期望回报: <span style="color: {color};">{exp_ret:+.2f}%</span></div>'
        except Exception as e:
            print(f"Error calculating expected return: {e}")

        # Scenario chart generation removed as per user request

        # Trading Plan Grid
        trading_steps = d.get("trading_steps", [])
        if not isinstance(trading_steps, list) or (len(trading_steps) > 0 and not isinstance(trading_steps[0], dict)):
            trading_steps = []

        trading_steps_html = ""
        for s in trading_steps:
            if not isinstance(s, dict): continue
            trading_steps_html += f"""
            <div class="trade-card">
                <div class="trade-level">{esc(self._render_prose(s.get('level', '仓位'), 40))}</div>
                <div class="trade-price">{esc(self._render_prose(s.get('price', 'N/A'), 60))}</div>
                <div class="trade-weight">占比: {esc(self._render_prose(s.get('weight', 'N/A'), 40))}</div>
                <div class="trade-logic">{esc(self._render_prose(s.get('logic', ''), 200))}</div>
            </div>"""
        if not trading_steps_html:
            trading_steps_html = '<div class="no-data-msg">未提取到分级交易步骤卡片，请参阅上方交易计划总述与专家研讨日志。</div>'

        # Market wind control and disciplines
        wind_control = d.get("market_wind_control") or {}
        discipline = d.get("trading_discipline") or {}

        moat_list = "".join([f'<li>{esc(p)}</li>' for p in d.get("moat_points", [])]) or '<li style="color:#94a3b8;font-style:italic;">暂无护城河要点数据</li>'
        macro_list = "".join([f'<li>{esc(p)}</li>' for p in d.get("macro_points", [])]) or '<li style="color:#94a3b8;font-style:italic;">暂无宏观与技术面要点数据</li>'
        risk_points_html = "".join([f'<li>{esc(p)}</li>' for p in d.get("risks_points", [])]) or '<li style="color:#94a3b8;font-style:italic;">暂无失效风险清单数据</li>'
        bull_list_html = "".join([f"<li>{esc(p)}</li>" for p in d.get("key_opps", [])]) or '<li style="color:#94a3b8;font-style:italic;">暂无明确看涨驱动，请参考上方核心逻辑</li>'
        bear_list_html = "".join([f"<li>{esc(p)}</li>" for p in d.get("key_risks", [])]) or '<li style="color:#94a3b8;font-style:italic;">暂无明确下行风险</li>'

        log_html = "".join([
            f'<div class="log-msg"><div class="log-role" style="display:flex; align-items:center; gap:8px;"><span>{m["role"]}</span>'
            f'<span style="background:var(--bg); color:var(--text-light); border:1px solid var(--border); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:500; text-transform:none; letter-spacing:normal;">{m.get("model", "AI")}</span></div>'
            f'<div class="log-body">{m["content"]}</div></div>'
            for m in d["discussion"]
        ])

        # Determine market and render specific wind control HTML
        market_str = info.get("market") or ""
        if market_str == "A-Share" or market_str.lower() in ("cn", "ashare", "a-share"):
            wind_control_html = f"""
                    <div class="wind-card">
                        <div class="wind-card-title">📅 限售股解禁日历</div>
                        <div class="wind-card-body">
                            <strong>解禁信息：</strong> {esc(self._render_prose(wind_control.get("lockup_date") or "无近三个月大额解禁信息", 120))}<br>
                            <strong>解禁冲击：</strong> {esc(self._render_prose(wind_control.get("lockup_impact") or "解禁冲击评估为低/无", 200))}
                        </div>
                    </div>
                    <div class="wind-card">
                        <div class="wind-card-title">📢 减持公告与拥挤度</div>
                        <div class="wind-card-body">
                            <strong>减持情况：</strong> {esc(self._render_prose(wind_control.get("reduction_plan") or "无未完成减持公告", 200))}<br>
                            <strong>机构拥挤：</strong> {esc(self._render_prose(wind_control.get("crowding_level") or "机构仓位拥挤度适中", 120))}
                        </div>
                    </div>"""
        elif market_str == "HK-Share" or market_str.lower() in ("hk", "hkshare", "hk-share"):
            wind_control_html = f"""
                    <div class="wind-card">
                        <div class="wind-card-title">📅 基石/主要股东禁售解禁</div>
                        <div class="wind-card-body">
                            <strong>禁售解禁：</strong> {esc(self._render_prose(wind_control.get("lockup_date") or "无近三个月大额禁售解禁信息", 120))}<br>
                            <strong>减持/解禁冲击：</strong> {esc(self._render_prose(wind_control.get("lockup_impact") or "解禁及减持冲击低/无", 200))}
                        </div>
                    </div>
                    <div class="wind-card">
                        <div class="wind-card-title">📢 港股通持股与大股东质押</div>
                        <div class="wind-card-body">
                            <strong>港股通持股：</strong> {esc(self._render_prose(wind_control.get("crowding_level") or "南向资金持股变动稳健", 120))}<br>
                            <strong>股份质押/减持：</strong> {esc(self._render_prose(wind_control.get("reduction_plan") or "大股东及质押风险为安全/无", 200))}
                        </div>
                    </div>"""
        else: # US-Share
            wind_control_html = f"""
                    <div class="wind-card">
                        <div class="wind-card-title">📅 内部人交易 Form 4</div>
                        <div class="wind-card-body">
                            <strong>内部人交易：</strong> {esc(self._render_prose(wind_control.get("lockup_date") or "无大额内部人买卖交易记录", 120))}<br>
                            <strong>10b5-1 计划：</strong> {esc(self._render_prose(wind_control.get("lockup_impact") or "无正在执行的10b5-1大额减持计划", 200))}
                        </div>
                    </div>
                    <div class="wind-card">
                        <div class="wind-card-title">📢 空头头寸与机构持仓</div>
                        <div class="wind-card-body">
                            <strong>空头占比：</strong> {esc(self._render_prose(wind_control.get("reduction_plan") or "空头头寸占比 (Short Interest) 处于安全低位", 200))}<br>
                            <strong>机构持仓：</strong> {esc(self._render_prose(wind_control.get("crowding_level") or "13F 机构持仓未见踩踏或大幅抛售", 200))}
                        </div>
                    </div>"""

        # Data completeness warning
        data_completeness = d.get("data_completeness", {})
        data_score = data_completeness.get("score", 100)
        data_warning_html = ""
        if data_score < 50:
            missing_items = ", ".join(data_completeness.get("missing", [])) or "关键财务及宏观数据"
            data_warning_html = f'''
            <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 16px; margin: 20px 0; border-radius: 4px;">
                <h4 style="color: #991b1b; margin: 0 0 8px 0; display: flex; align-items: center;"><span style="font-size: 18px; margin-right: 8px;">⚠️</span> 严重数据缺失警告 (完整度: {data_score}%)</h4>
                <p style="color: #b91c1c; margin: 0; font-size: 14px;">本报告因关键数据缺失（{missing_items}），结论仅供参考，不构成交易建议。建议在数据补齐后重新生成。</p>
            </div>
            '''

        return f"""<!DOCTYPE html>
<html lang="{'en' if info.get('market') == 'US-Share' else 'zh-CN'}">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{info["name"]} ({info["symbol"]}) - {locale["page_title"]}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@500;600;700;800&display=swap');
        :root {{
            --bg: #f8fafc;
            --primary: #0f172a;
            --primary-light: #1e293b;
            --accent: #2563eb;
            --accent-glow: rgba(37, 99, 235, 0.15);
            --text: #334155;
            --text-light: #64748b;
            --border: #e2e8f0;
            --card-bg: #ffffff;
            
            --bull: #10b981;
            --bull-bg: #ecfdf5;
            --bear: #ef4444;
            --bear-bg: #fef2f2;
            --warning: #f59e0b;
            --warning-bg: #fffbeb;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            color: var(--text);
            line-height: 1.6;
            margin: 0;
            background: var(--bg);
            -webkit-font-smoothing: antialiased;
        }}
        
        .report-page {{
            max-width: 1100px;
            margin: 40px auto;
            background: var(--card-bg);
            padding: 50px 70px;
            box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.05);
            border-radius: 12px;
            border: 1px solid var(--border);
        }}
        
        /* Layer Headers */
        .layer-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 24px;
            font-weight: 800;
            color: var(--primary);
            border-bottom: 2px solid var(--primary);
            padding-bottom: 12px;
            margin-top: 50px;
            margin-bottom: 25px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
        }}
        .layer-title::before {{
            content: '';
            display: inline-block;
            width: 6px;
            height: 24px;
            background: var(--accent);
            margin-right: 12px;
            border-radius: 3px;
        }}
        .layer-title .layer-num {{
            font-size: 14px;
            background: var(--accent-glow);
            color: var(--accent);
            padding: 2px 10px;
            border-radius: 20px;
            margin-left: 12px;
            font-weight: 700;
        }}
        
        /* Brand Header */
        .report-header {{
            border-bottom: 2px solid var(--primary);
            padding-bottom: 25px;
            margin-bottom: 45px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .brand-logo {{
            font-family: 'Outfit', sans-serif;
            font-size: 12px;
            font-weight: 800;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 3px;
            margin-bottom: 10px;
        }}
        .ticker-info h1 {{
            margin: 0;
            font-family: 'Outfit', sans-serif;
            font-size: 34px;
            font-weight: 800;
            color: var(--primary);
        }}
        .ticker-sub {{
            color: var(--text-light);
            font-size: 14px;
            font-weight: 500;
            margin-top: 5px;
        }}
        .price-box {{ text-align: right; }}
        .current-price {{
            font-family: 'Outfit', sans-serif;
            font-size: 38px;
            font-weight: 800;
            color: var(--primary);
            line-height: 1;
        }}
        .price-pct {{
            font-size: 18px;
            font-weight: 700;
            color: {chg_color};
            margin-top: 5px;
        }}
        
        /* Verdict Banners */
        .verdict-banner {{
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #fff;
            padding: 20px 30px;
            border-radius: 8px;
            margin-bottom: 25px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 15px rgba(15, 23, 42, 0.15);
        }}
        .verdict-text {{
            font-size: 18px;
            font-weight: 700;
            letter-spacing: 0.3px;
        }}
        .verdict-rec {{
            padding: 6px 18px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .verdict-rec.buy {{ background: rgba(16, 185, 129, 0.2); color: #6ee7b7; border: 1px solid #10b981; }}
        .verdict-rec.sell {{ background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid #ef4444; }}
        .verdict-rec.hold {{ background: rgba(245, 158, 11, 0.2); color: #fcd34d; border: 1px solid #f59e0b; }}
        
        .action-stance {{
            background: var(--warning-bg);
            border: 1px solid #fde68a;
            border-radius: 8px;
            padding: 15px 25px;
            margin-bottom: 30px;
            font-size: 14px;
            color: #92400e;
            font-weight: 600;
            display: flex;
            align-items: center;
        }}
        .action-stance::before {{ content: '🎯'; margin-right: 12px; font-size: 18px; }}


        .evidence-taxonomy {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 18px 0 30px; }}
        .claim-card {{ border: 1px solid var(--border); border-radius: 12px; padding: 16px; background: #fff; min-height: 130px; }}
        .claim-label {{ font-size: 12px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; margin-bottom: 8px; }}
        .claim-text {{ font-size: 13px; line-height: 1.6; color: #334155; }}
        .claim-fact {{ border-top: 4px solid #2563eb; }}
        .claim-inference {{ border-top: 4px solid #7c3aed; }}
        .claim-opinion {{ border-top: 4px solid #f59e0b; }}
        .claim-recommendation {{ border-top: 4px solid #10b981; }}

        /* Dashboard Container */
        .dashboard-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 25px;
            margin-bottom: 30px;
        }}
        .dashboard-card {{
            background: #fff;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 25px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
            transition: all 0.2s ease;
        }}
        .dashboard-card:hover {{
            box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.04);
            transform: translateY(-2px);
        }}
        .dashboard-card.full-width {{
            grid-column: 1 / -1;
        }}
        .card-title {{
            margin-top: 0;
            margin-bottom: 15px;
            font-family: 'Outfit', sans-serif;
            font-size: 16px;
            font-weight: 700;
            color: var(--primary);
            display: flex;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
        }}
        
        /* Profile Tags */
        .profile-tag-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 15px;
        }}
        .profile-tag {{
            background: var(--bg);
            border: 1px solid var(--border);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            color: var(--primary-light);
        }}
        .profile-tag span {{ color: var(--accent); margin-right: 4px; }}
        
        /* Consensus Splitting */
        .consensus-split {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .consensus-box {{
            padding: 15px;
            border-radius: 6px;
            font-size: 13px;
        }}
        .consensus-box.market {{
            background: #f1f5f9;
            border-left: 4px solid #94a3b8;
        }}
        .consensus-box.alpha {{
            background: var(--accent-glow);
            border-left: 4px solid var(--accent);
            color: #1e3a8a;
        }}
        .consensus-box-title {{
            font-weight: 700;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }}
        
        /* Calendar / Timelines */
        .calendar-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .calendar-table th {{
            text-align: left;
            padding: 10px 12px;
            font-weight: 700;
            color: var(--text-light);
            border-bottom: 2px solid var(--border);
        }}
        .calendar-table td {{
            padding: 12px;
            border-bottom: 1px solid var(--border);
        }}
        .calendar-date {{
            background: #e2e8f0;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 700;
            color: var(--primary-light);
        }}

        /* Valuation details */
        .valuation-top-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 25px;
            margin-bottom: 25px;
        }}
        .archetype-box {{
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .archetype-label {{ font-size: 13px; color: var(--text-light); font-weight: 500; }}
        .archetype-val {{ font-family: 'Outfit', sans-serif; font-size: 18px; font-weight: 800; color: var(--accent); }}
        
        .kill-switch-box {{
            border-radius: 8px;
            padding: 20px;
            border: 1px solid #fecaca;
            background: var(--bear-bg);
            color: #991b1b;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .kill-switch-box.safe {{
            border: 1px solid #a7f3d0;
            background: var(--bull-bg);
            color: #065f46;
        }}
        .ks-header-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        .ks-title {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }}
        .ks-status {{
            font-size: 11px;
            font-weight: 800;
            padding: 2px 8px;
            border-radius: 4px;
            color: #fff;
            background: var(--bear);
        }}
        .ks-status.safe {{ background: var(--bull); }}
        .ks-condition {{ font-size: 13px; font-weight: 500; }}
        
        .wacc-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-bottom: 30px;
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow: hidden;
        }}
        .wacc-table th {{
            background: #f1f5f9;
            padding: 10px;
            font-weight: 700;
            color: var(--primary-light);
            border: 1px solid var(--border);
            text-align: center;
        }}
        .wacc-table td {{
            padding: 10px;
            text-align: center;
            border: 1px solid var(--border);
        }}
        .wacc-source {{
            text-align: left !important;
            background: #fafafa;
            color: var(--text-light);
            font-size: 11px;
            padding: 12px !important;
        }}
        .valuation-alert-box {{
            margin: 0 0 14px 0;
            padding: 12px 16px;
            border: 1.5px solid #ef4444;
            border-left: 5px solid #ef4444;
            border-radius: 8px;
            background: rgba(239, 68, 68, 0.08);
        }}
        .valuation-alert-title {{
            font-size: 14px;
            font-weight: 800;
            color: #ef4444;
            margin-bottom: 6px;
        }}
        .valuation-alert-box ul {{
            margin: 0;
            padding-left: 18px;
            font-size: 13px;
            font-weight: 600;
            color: #b91c1c;
        }}
        .valuation-alert-box li {{ margin-bottom: 4px; }}
        
        /* Comps */
        .comps-wrapper {{
            margin-bottom: 35px;
        }}
        .comps-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 6px;
            color: var(--primary);
        }}
        .comps-desc {{
            font-size: 11px;
            color: var(--text-light);
            margin-bottom: 12px;
        }}
        .peer-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            border: 1px solid var(--border);
        }}
        .peer-table th {{
            background: #f8fafc;
            padding: 12px 10px;
            text-align: center;
            font-weight: 700;
            color: var(--primary-light);
            border: 1px solid var(--border);
        }}
        .peer-table td {{
            padding: 12px 10px;
            text-align: center;
            border: 1px solid var(--border);
        }}
        .peer-table tr:first-child td {{
            background: #f0f7ff;
            font-weight: 600;
        }}

        /* Detailed Fund Section */
        .fund-category {{ margin-bottom: 35px; }}
        .fund-category-title {{ font-size: 14px; font-weight: 800; color: var(--accent); margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1px; }}
        .fund-category-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
        .fund-item {{ background: #fdfdfd; border: 1px solid #f1f5f9; padding: 12px 15px; display: flex; justify-content: space-between; align-items: center; border-radius: 6px; }}
        .fund-item-label {{ font-size: 13px; color: #475569; font-weight: 500; }}
        .fund-item-label span {{ display: block; font-size: 10px; color: #94a3b8; font-weight: 400; }}
        .fund-item-value {{ font-size: 14px; font-weight: 700; color: var(--primary); }}
        .signal-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }}
        .signal-green {{ background: #10b981; box-shadow: 0 0 4px #10b98180; }}
        .signal-yellow {{ background: #f59e0b; box-shadow: 0 0 4px #f59e0b80; }}
        .signal-red {{ background: #ef4444; box-shadow: 0 0 4px #ef444480; }}
        .signal-gray {{ background: #cbd5e1; }}
        
        /* Card Grids */
        .thesis-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 25px; text-align: left; }}
        .thesis-card {{ padding: 25px; border-radius: 8px; border: 1px solid var(--border); background: #fff; }}
        .thesis-card.bull {{ border-top: 5px solid var(--bull); background: #f0fdf4; }}
        .thesis-card.bear {{ border-top: 5px solid var(--bear); background: #fef2f2; }}
        .thesis-tag {{ font-size: 12px; font-weight: 700; text-transform: uppercase; margin-bottom: 15px; }}
        .bull .thesis-tag {{ color: var(--bull); }}
        .bear .thesis-tag {{ color: var(--bear); }}
        .thesis-list {{ padding-left: 18px; margin: 0; font-size: 14px; color: #475569; }}
        .thesis-list li {{ margin-bottom: 10px; }}

        .analysis-block {{ background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 30px; }}
        .analysis-text {{ font-size: 16px; color: #1e293b; line-height: 1.8; padding: 25px 25px 10px 25px; }}
        .analysis-highlights {{ padding: 0 25px 25px 25px; }}
        .analysis-highlights-title {{ font-size: 12px; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; display: flex; align-items: center; }}
        .analysis-highlights-title::before {{ content: '⚡'; margin-right: 8px; }}
        .analysis-list {{ padding: 0; margin: 0; list-style: none; display: grid; grid-template-columns: 1fr; gap: 8px; }}
        .analysis-list li {{ position: relative; padding-left: 20px; font-size: 14px; color: #475569; line-height: 1.6; }}
        .analysis-list li::before {{ content: '•'; position: absolute; left: 0; color: var(--accent); font-weight: bold; font-size: 18px; line-height: 1; }}

        /* Execution Plan */
        .trading-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 20px; text-align: left; }}
        .trade-card {{ background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 20px; text-align: center; }}
        .trade-level {{ font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }}
        .trade-price {{ font-size: 24px; font-weight: 800; color: var(--accent); margin-bottom: 8px; }}
        .trade-weight {{ font-size: 13px; font-weight: 600; color: #1e293b; background: #e0f2fe; display: inline-block; padding: 2px 10px; border-radius: 4px; margin-bottom: 12px; }}
        .trade-logic {{ font-size: 13px; color: #64748b; line-height: 1.5; }}
        
        /* A-Share Wind Control Card Layout */
        .wind-control-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 25px;
            margin-bottom: 30px;
        }}
        .wind-card {{
            background: #fff;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
        }}
        .wind-card-title {{ font-size: 14px; font-weight: 800; color: var(--primary); margin-bottom: 12px; border-left: 4px solid var(--warning); padding-left: 8px; }}
        .wind-card-body {{ font-size: 13px; color: var(--text); line-height: 1.6; }}
        
        .data-warning {{ margin: 20px 0; padding: 15px; background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px; color: #92400e; font-size: 13px; display: flex; align-items: center; }}
        .data-warning::before {{ content: '⚠️'; margin-right: 10px; font-size: 16px; }}

        .risk-section {{ margin-top: 40px; background: #fff1f2; border: 1px solid #fecaca; border-radius: 8px; padding: 30px; text-align: left; }}
        .risk-header {{ font-weight: 800; color: #991b1b; display: flex; align-items: center; margin-bottom: 15px; font-size: 18px; }}
        .risk-header::before {{ content: '⚠️'; margin-right: 12px; }}
        .risk-content {{ font-size: 14px; color: #991b1b; }}
        .risk-content ul {{ padding-left: 20px; margin: 0; }}
        .risk-content li {{ margin-bottom: 8px; }}

        .data-table {{ width: 100%; border-collapse: collapse; font-size: 14px; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; text-align: left; }}
        .data-table th {{ background: var(--bg); padding: 15px; text-align: left; font-weight: 700; color: var(--primary); }}
        .data-table td {{ padding: 15px; border-top: 1px solid var(--border); }}

        .score-badge {{ background: var(--primary-light); color: #fff; padding: 6px 15px; border-radius: 4px; font-size: 14px; font-weight: 700; margin-left: 20px; text-transform: none; }}
        
        /* Collapsible Discussion Appendix */
        .discussion-log {{ margin-top: 60px; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; text-align: left; }}
        .discussion-toggle {{ cursor: pointer; user-select: none; }}
        .discussion-toggle summary {{ background: var(--primary-light); color: #fff; padding: 18px 25px; font-weight: 700; list-style: none; display: flex; align-items: center; justify-content: space-between; }}
        .discussion-toggle summary::after {{ content: '▶ 展开查看投研辩论'; font-size: 13px; opacity: 0.8; font-weight: 400; }}
        .discussion-toggle[open] summary::after {{ content: '▼ 收起投研辩论'; }}
        
        .log-msg {{ padding: 30px 25px; border-bottom: 1px solid var(--border); background: #fff; }}
        .log-role {{ margin-bottom: 15px; display: flex; align-items: center; }}
        .log-role span {{ background: var(--bg); color: var(--accent); border: 1px solid var(--border); padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }}
        .log-body {{ font-size: 14px; color: #334155; line-height: 1.8; border-left: 4px solid var(--border); padding-left: 20px; }}
        .log-body h1, .log-body h2, .log-body h3 {{ color: var(--primary); margin-top: 25px; margin-bottom: 15px; font-size: 15px; }}
        .log-body table {{ width: 100%; border-collapse: collapse; margin: 20px 0; border: 1px solid var(--border); }}
        .log-body th {{ background: var(--bg); padding: 10px; border: 1px solid var(--border); font-weight: 700; }}
        .log-body td {{ padding: 8px 10px; border: 1px solid var(--border); }}
        .log-body pre {{ white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; overflow-x: auto; max-width: 100%; background: #f8fafc; padding: 15px; border-radius: 6px; border: 1px solid var(--border); }}
        .log-body code {{ background: none; padding: 0; border: none; font-family: monospace; white-space: pre-wrap; word-wrap: break-word; }}

        .report-footer {{ margin-top: 60px; padding-top: 20px; border-top: 1px solid var(--border); color: #94a3b8; font-size: 12px; text-align: center; }}
        
        /* No Data Msg styling */
        .no-data-msg {{
            background: #f8fafc;
            border: 1px dashed var(--border);
            border-radius: 6px;
            padding: 15px;
            color: var(--text-light);
            text-align: center;
            font-size: 13px;
        }}

        @media (max-width: 900px) {{
            .dashboard-grid, .consensus-split, .valuation-top-row, .wind-control-grid, .thesis-grid, .evidence-taxonomy {{
                grid-template-columns: 1fr !important;
            }}
            .fund-category-grid, .trading-grid {{
                grid-template-columns: 1fr !important;
            }}
            .report-page {{
                padding: 30px;
            }}
            .dashboard-card, .wind-card, .thesis-card {{
                padding: 15px;
            }}
        }}

        @media print {{
            body {{ background: #fff; }}
            .report-page {{ box-shadow: none; margin: 0; padding: 30px; border: none; max-width: 100%; }}
            .discussion-toggle {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="report-page">
        <header class="report-header">
            <div class="ticker-info">
                <div class="brand-logo">ALSA Multi-Agent Intelligence</div>
                <h1>{info["name"]}</h1>
                <div class="ticker-sub">{info["symbol"]} | {info["market"]} | 研究报告号: {datetime.now().strftime("%Y%m%d%H%M")}</div>
            </div>
            <div class="price-box">
                <div class="current-price">{info["price"]} <span style="font-size:16px; font-weight:400; color:#94a3b8;">{info["currency"]}</span></div>
                <div class="price-pct">{chg_sign}{info["changePercent"]}%</div>
                <div style="font-size:11px; color:#94a3b8; margin-top:5px;">数据更新: {info["lastUpdated"]}</div>
            </div>
        </header>

        {verdict_html}
        {data_warning_html}
        {integrity_html}
        {action_html}
        {evidence_taxonomy_html}

        <!-- {locale["layer1_title"]} -->
        <h2 class="layer-title">{locale["layer1_title"]} <span class="layer-num">L1</span></h2>
        
        <div class="dashboard-grid">
            <div class="dashboard-card full-width">
                <h3 class="card-title">💡 tagline 投资亮点</h3>
                <div style="font-size: 18px; font-weight: 800; color: var(--accent); margin-bottom: 12px;">{esc(tagline)}</div>
                <div style="font-size: 14px; font-weight: 700; color: var(--primary-light); margin-bottom: 8px;">{locale["label_thesis_narrative"]}</div>
                <div style="font-size: 14px; line-height: 1.7; color: var(--text);">{esc(thesis)}</div>
            </div>
            
            <div class="dashboard-card">
                <h3 class="card-title">{locale["card_factor_profile"]}</h3>
                <div class="profile-tag-list">
                    <div class="profile-tag"><span>{locale["label_size"]}</span> {factor.get("size") or locale["label_unclassified"]}</div>
                    <div class="profile-tag"><span>{locale["label_style"]}</span> {factor.get("style") or locale["label_unclassified"]}</div>
                    <div class="profile-tag"><span>{locale["label_volatility"]}</span> {factor.get("volatility") or locale["label_unclassified"]}</div>
                </div>
                <div style="font-size: 13px; color: var(--text); font-weight: 500;">
                    <strong>{locale["label_expected_return"]}</strong> {factor.get("expected_return") or locale["label_no_expectation"]}
                </div>
                <div style="margin-top: 14px; text-align: center;">{factor_radar_html}</div>
            </div>
            
            <div class="dashboard-card">
                <h3 class="card-title">{locale["card_consensus"]}</h3>
                <div class="consensus-split">
                    <div class="consensus-box market">
                        <div class="consensus-box-title">{locale["label_market_consensus"]}</div>
                        <div>{esc(consensus.get("market_consensus") or locale["label_no_consensus"])}</div>
                    </div>
                    <div class="consensus-box alpha">
                        <div class="consensus-box-title">{locale["label_our_alpha"]}</div>
                        <div>{esc(consensus.get("our_alpha") or locale["label_no_alpha"])}</div>
                    </div>
                </div>
            </div>
            
            <div class="dashboard-card full-width">
                <h3 class="card-title">{locale["card_the_call"]}</h3>
                <div style="font-size: 15px; font-weight: 700; color: #1e3a8a; background: var(--accent-glow); padding: 12px 20px; border-radius: 6px; border-left: 4px solid var(--accent);">
                    {esc(the_call)}
                </div>
            </div>
            
            <div class="dashboard-card full-width">
                <h3 class="card-title">{locale["card_scenarios"]}</h3>
                <table class="data-table">
                    <thead><tr><th>{locale["scenario_case"]}</th><th>{locale["scenario_prob"]}</th><th>{locale["scenario_target"]}</th><th>{locale["scenario_logic"]}</th></tr></thead>
                    <tbody>{sc_rows}</tbody>
                </table>
                {expected_return_html}
            </div>
        </div>
        
        {catalyst_html}

        <!-- {locale["layer2_title"]} -->
        <h2 class="layer-title">{locale["layer2_title"]} <span class="layer-num">L2</span></h2>
        
        <div class="dashboard-grid">
            <div class="dashboard-card full-width">
                <h3 class="card-title">{locale["card_valuation"]}</h3>
                <div class="valuation-top-row">
                    <div class="archetype-box">
                        <div class="archetype-label">{locale["card_archetype_label"]}</div>
                        <div class="archetype-val">{archetype_zh}</div>
                    </div>
                    <div class="kill-switch-box {ks_class}">
                        <div class="ks-header-row">
                            <span class="ks-title">{locale["card_kill_switch"]}</span>
                            <span class="ks-status {ks_class}">{ks_status_zh}</span>
                        </div>
                        <div class="ks-condition">{ks_condition}</div>
                    </div>
                </div>
                
                <div style="margin-top:20px; margin-bottom:10px; font-size:14px; font-weight:700; color: var(--primary-light);">{locale["card_wacc"]}</div>
                {wacc_table_html}
            </div>
        </div>

        <section class="section">
            <h2 class="section-title">{locale["deep_fundamentals"]}</h2>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 15px;">
                <span class="signal-dot signal-green"></span>{locale["signal_healthy"]}
                <span style="margin-left: 12px;"><span class="signal-dot signal-yellow"></span>{locale["signal_neutral"]}</span>
                <span style="margin-left: 12px;"><span class="signal-dot signal-red"></span>{locale["signal_risk"]}</span>
                <span style="margin-left: 12px;"><span class="signal-dot signal-gray"></span>{locale["signal_na"]}</span>
            </div>
            {detailed_fund_html}
        </section>
        
        {peer_section_html}
        <div style="margin-top: 16px; margin-bottom: 16px;">{peer_chart_html}</div>

        {flow_section_html}

        <section class="section">
            <h2 class="section-title">{locale["core_variables"]}</h2>
            <div class="thesis-grid">
                <div class="thesis-card bull">
                    <div class="thesis-tag">{locale["bull_thesis"]}</div>
                    <ul class="thesis-list">{bull_list_html}</ul>
                </div>
                <div class="thesis-card bear">
                    <div class="thesis-tag">{locale["bear_thesis"]}</div>
                    <ul class="thesis-list">{bear_list_html}</ul>
                </div>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">{locale["moat_section"]}</h2>
            <div class="analysis-block">
                <div class="analysis-text">{md(d["moat_summary"])}</div>
                <div class="analysis-highlights">
                    <div class="analysis-highlights-title">{locale["key_moat"]}</div>
                    <ul class="analysis-list">
                        {moat_list}
                    </ul>
                </div>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">{locale["macro_section"]}</h2>
            <div class="analysis-block">
                <div class="analysis-text">{md(d["macro_summary"])}</div>
                <div class="analysis-highlights">
                    <div class="analysis-highlights-title">{locale["macro_section"]}</div>
                    <ul class="analysis-list">
                        {macro_list}
                    </ul>
                </div>
            </div>
        </section>

        <!-- {locale["layer3_title"]} -->
        <h2 class="layer-title">{locale["layer3_title"]} <span class="layer-num">L3</span></h2>
        
        <div class="dashboard-grid">
            <div class="dashboard-card full-width">
                <h3 class="card-title">{locale["card_trading_steps"]}</h3>
                <div style="font-size:14px; margin-bottom:25px; color:#475569; text-align:left;">{md(d["trading_plan"])}</div>
                <div class="trading-grid">
                    {trading_steps_html}
                </div>
            </div>
            
            <div class="dashboard-card full-width">
                <h3 class="card-title">{locale["card_wind_control"]}</h3>
                <div class="wind-control-grid">
                    {wind_control_html}
                </div>
            </div>
            
            <div class="dashboard-card">
                <h3 class="card-title">{locale["card_lr_signal"]}</h3>
                <div style="font-size:13px; line-height:1.7;">
                    <strong>{locale["label_left_side"]}</strong> {esc(self._render_prose(discipline.get("left_side_condition") or locale["label_no_left"], 200))}<br><br>
                    <strong>{locale["label_right_side"]}</strong> {esc(self._render_prose(discipline.get("right_side_trigger") or locale["label_no_right"], 200))}
                </div>
            </div>
            
            <div class="dashboard-card">
                <h3 class="card-title">{locale["card_drawdown"]}</h3>
                <div style="font-size:13px; line-height:1.7;">
                    <strong>{locale["label_max_drawdown"]}</strong> <span style="color:var(--bear); font-weight:700;">{esc(self._render_prose(discipline.get("max_drawdown_limit") or locale["label_default_drawdown"], 60))}</span><br><br>
                    <strong>{locale["label_invalidation"]}</strong> {esc(self._render_prose(discipline.get("thesis_invalidation_trigger") or locale["label_no_invalidation"], 200))}
                </div>
            </div>
        </div>

        <section class="section" id="risk-warning">
            <div class="risk-section">
                <div class="risk-header">{locale["risk_warning"]}</div>
                <div class="risk-content">
                    <ul>
                        {risk_points_html}
                    </ul>
                </div>
            </div>
        </section>

        <!-- {locale["appendix_title"]} -->
        <details class="discussion-toggle discussion-log">
            <summary>{locale["discussion_log"]}</summary>
            {log_html}
        </details>

        <footer class="report-footer">
            <p><strong>{locale["disclaimer"]}</strong></p>
            <p>{locale["copyright"]}</p>
        </footer>
    </div>
</body>
</html>"""




    def _compile_fundamentals(self, snapshot: dict, currency: str, ui_data: dict = {}, market: str = "US-Share") -> dict:
        m = {}
        if not isinstance(snapshot, dict): return m
        v, f, q = snapshot.get("valuation", {}), snapshot.get("financials", {}), snapshot.get("quote", {})
        
        # Determine financial currency (may differ from listing currency for ADRs)
        fin_currency = f.get("financialCurrency") or q.get("financialCurrency") or currency
        
        def ratio(val): return f"{round(val, 2)}" if val is not None and isinstance(val, (int, float)) else "N/A"
        def pct(val):
            if val is None or not isinstance(val, (int, float)): return "N/A"
            # If value is clearly a decimal ratio (e.g. 0.15 for 15%), convert to percentage
            # Use a more robust threshold: ratios from yfinance are typically < 1.0
            # API returns percentage values directly (e.g. 15.5 for 15.5%)
            if abs(val) < 1.0:
                return f"{round(val * 100, 2)}%"
            return f"{round(val, 2)}%"
        def money(val, use_currency=None):
            c = use_currency or currency
            if val is None or not isinstance(val, (int, float)): return "N/A"
            if abs(val) >= 1e12: return f"{round(val/1e12, 2)}万亿 {c}"
            if abs(val) >= 1e8: return f"{round(val/1e8, 2)}亿 {c}"
            if abs(val) >= 1e6: return f"{round(val/1e6, 2)}百万 {c}"
            return f"{round(val, 2)} {c}"

        # Combine sources (f, q, v)
        def get_val(key, sources=[f, q, v]):
            for s in sources:
                if key in s and s[key] is not None: return s[key]
            return None

        # 1. Valuation
        m["总市值"] = money(get_val("marketCap"))
        # EV is reported in financialCurrency by yfinance for foreign stocks
        m["企业价值 (EV)"] = money(get_val("enterpriseValue"), use_currency=fin_currency)
        
        np_val = money(get_val("netProfit"), use_currency=fin_currency)
        m["净利润"] = np_val if np_val != "N/A" else (ui_data.get("net_profit") or "N/A")
        
        # 扣非净利润 is A-Share specific (China GAAP disclosure)
        if market == "A-Share":
            npd_val = money(get_val("netProfitDeduct"), use_currency=fin_currency)
            m["扣非净利润"] = npd_val if npd_val != "N/A" else (ui_data.get("net_profit_deduct") or "N/A")
        m["市盈率 (PE)"] = ratio(get_val("trailingPE") or get_val("pe") or get_val("forwardPE"))
        m["市净率 (PB)"] = ratio(get_val("priceToBook") or get_val("pb"))
        # PEG: if not available, calculate from PE and earnings growth
        peg = get_val("pegRatio")
        if peg is None:
            pe_val = get_val("trailingPE") or get_val("pe")
            eg_val = get_val("earningsGrowth") or get_val("netProfitGrowth")
            if pe_val and eg_val and isinstance(pe_val, (int, float)) and isinstance(eg_val, (int, float)) and eg_val != 0:
                eg_pct = eg_val * 100 if abs(eg_val) < 1 else eg_val
                if eg_pct != 0:
                    peg = pe_val / eg_pct
        m["PEG"] = ratio(peg)
        m["市销率 (PS)"] = ratio(get_val("priceToSales"))
        m["EV/EBITDA"] = ratio(get_val("enterpriseToEbitda"))

        # 2. Profitability
        m["净资产收益率 (ROE)"] = pct(get_val("returnOnEquity") or get_val("roe"))
        m["总资产收益率 (ROA)"] = pct(get_val("returnOnAssets") or get_val("roa"))
        m["毛利率"] = pct(get_val("grossMargins") or get_val("grossMargin"))
        m["营业利润率"] = pct(get_val("operatingMargins") or get_val("operatingMargin"))
        m["净利率"] = pct(get_val("profitMargins") or get_val("profitMargin"))
        m["每股收益 (EPS)"] = ratio(get_val("eps"))

        # 3. Growth
        m["营收同比增长 (YoY)"] = pct(get_val("revenueYoY_annual") or get_val("revenueYoY") or get_val("revenueGrowth") or get_val("revenueGrowthYoY"))
        m["营收同比-单季 (YoY-Q)"] = pct(get_val("revenueGrowth") or get_val("revenueYoY") or get_val("revenueGrowthYoY"))
        
        rev_qoq = pct(get_val("revenueQoQ"))
        m["营收环比增长 (QoQ)"] = rev_qoq if rev_qoq != "N/A" else (ui_data.get("revenue_qoq") or "N/A")
        
        np_yoy = pct(get_val("netProfitYoY") or get_val("earningsGrowth") or get_val("netProfitGrowth") or get_val("netProfitGrowthYoY"))
        m["净利润同比增长 (YoY)"] = np_yoy if np_yoy != "N/A" else (ui_data.get("net_profit_yoy") or "N/A")
        
        np_qoq = pct(get_val("netProfitQoQ"))
        m["净利润环比增长 (QoQ)"] = np_qoq if np_qoq != "N/A" else (ui_data.get("net_profit_qoq") or "N/A")
        
        # 扣非净利润 growth is A-Share specific
        if market == "A-Share":
            npd_yoy = pct(get_val("netProfitDeductYoY"))
            m["扣非净利润同比增长 (YoY)"] = npd_yoy if npd_yoy != "N/A" else (ui_data.get("net_profit_deduct_yoy") or "N/A")
            
            npd_qoq = pct(get_val("netProfitDeductQoQ"))
            m["扣非净利润环比增长 (QoQ)"] = npd_qoq if npd_qoq != "N/A" else (ui_data.get("net_profit_deduct_qoq") or "N/A")
        
        m["营收3年复合增长 (CAGR)"] = pct(get_val("revenueCagr3y"))
        m["净利润3年复合增长 (CAGR)"] = pct(get_val("incomeCagr3y"))

        # 3b. Absolute revenue (TTM, fallback to latest quarterly) — surface the
        # absolute value, not just YoY %. Honest: shows N/A if truly unavailable.
        _rev = get_val("revenue")
        if _rev is None:
            _qh = f.get("quarterlyHistory") or []
            if isinstance(_qh, list) and _qh:
                _rev = _qh[0].get("Total Revenue") or _qh[0].get("revenue")
        m["营业总收入"] = money(_rev, use_currency=fin_currency)

        # 涨跌幅 — already in the price header; surface here for tabular completeness
        m["涨跌幅"] = pct(get_val("changePercent"))

        # 4. Financial Health
        # Asset-Liability Ratio (资产负债率) = Total Liabilities / Total Assets
        # debtToEquity from yfinance is (Total Debt / Total Equity) * 100
        # Correct conversion: if D/E = x, then Debt Ratio = x / (x + 100)
        debt_ratio = get_val("debtRatio")
        if debt_ratio is None:
            de = get_val("debtToEquity")
            if de is not None:
                # debtToEquity is in percentage form (e.g. 72.09 means 72.09%)
                # Asset-Liability Ratio = D/E / (1 + D/E) = (de/100) / (1 + de/100)
                debt_ratio = (de / 100) / (1 + de / 100)
        m["资产负债率"] = pct(debt_ratio)
        m["流动比率"] = ratio(get_val("currentRatio"))
        m["速动比率"] = ratio(get_val("quickRatio"))

        # 5. Cash Flow & Dividends (use financialCurrency for absolute values)
        m["经营现金流"] = money(get_val("operatingCashflow"), use_currency=fin_currency)
        m["自由现金流 (FCF)"] = money(get_val("freeCashflow"), use_currency=fin_currency)
        m["总现金(含短投)"] = money(get_val("totalCash"), use_currency=fin_currency)
        m["总有息负债"] = money(get_val("totalDebt"), use_currency=fin_currency)
        m["净现金"] = money(get_val("netCash"), use_currency=fin_currency)
        
        capex_val = money(get_val("capitalExpenditure"), use_currency=fin_currency)
        m["资本开支 (CAPEX)"] = capex_val if capex_val != "N/A" else (ui_data.get("capex") or "N/A")
        
        m["分红率"] = pct(get_val("payoutRatio"))
        
        div = get_val("dividendYield")
        if div is None:
            div = get_val("dividend")
        if div is not None and isinstance(div, (int, float)):
            if div == 0: m["股息率"] = "0.0%"
            else:
                # Cross-validate with dividendRate/price to resolve ambiguity
                div_rate = get_val("dividendRate")
                price = get_val("price") or q.get("currentPrice") or q.get("regularMarketPrice")
                if div_rate and price and isinstance(div_rate, (int, float)) and isinstance(price, (int, float)) and price > 0:
                    expected_pct = (div_rate / price) * 100
                    # Pick whichever interpretation (as-is or *100) is closer to expected
                    if abs(div - expected_pct) <= abs(div * 100 - expected_pct):
                        m["股息率"] = f"{round(div, 2)}%"
                    else:
                        m["股息率"] = f"{round(div * 100, 2)}%"
                elif div > 1 and div < 100:
                    m["股息率"] = f"{round(div, 2)}%"
                else:
                    # Modern yfinance returns dividendYield as percentage (e.g. 0.41 = 0.41%)
                    # trailingAnnualDividendYield is always decimal (e.g. 0.004 = 0.4%)
                    trailing = get_val("trailingAnnualDividendYield")
                    if trailing and isinstance(trailing, (int, float)) and trailing > 0:
                        trailing_pct = trailing * 100
                        if abs(div - trailing_pct) <= abs(div * 100 - trailing_pct):
                            m["股息率"] = f"{round(div, 2)}%"
                        else:
                            m["股息率"] = f"{round(div * 100, 2)}%"
                    else:
                        # No cross-reference; if < 1, treat as percentage (modern yfinance)
                        m["股息率"] = f"{round(div, 2)}%"
        else:
            # If payoutRatio is 0 or dividendRate is None/0, company pays no dividend
            pr = get_val("payoutRatio")
            dr = get_val("dividendRate")
            if pr is not None and pr == 0:
                m["股息率"] = "0% (无分红)"
            elif dr is not None and dr == 0:
                m["股息率"] = "0% (无分红)"
            else:
                m["股息率"] = "N/A"

        # 6. Efficiency — also check indicator history for turnover data
        at_val = get_val("assetTurnover")
        it_val = get_val("inventoryTurnover")
        # Try to extract from financial indicator history if not at top level
        if (at_val is None or it_val is None):
            ak_hist = f.get("financials", {}).get("history", []) if isinstance(f.get("financials"), dict) else []
            if ak_hist and isinstance(ak_hist, list) and len(ak_hist) > 0:
                latest_ind = ak_hist[0]
                if at_val is None:
                    at_val = latest_ind.get("总资产周转率(次)") or latest_ind.get("总资产周转率")
                if it_val is None:
                    it_val = latest_ind.get("存货周转率(次)") or latest_ind.get("存货周转率")
        # Convert string numbers from API
        def safe_float(v):
            if v is None: return None
            if isinstance(v, (int, float)): return v
            try: return float(str(v).replace(",", ""))
            except Exception:
                logger.exception("Failed to convert value '%s' to float in report generation", v)
                return None
        at_num = safe_float(at_val)
        it_num = safe_float(it_val)
        m["总资产周转率"] = ratio(at_num) if at_num else (ui_data.get("asset_turnover") or "N/A")
        m["存货周转率"] = ratio(it_num) if it_num else (ui_data.get("inventory_turnover") or "N/A")

        # 7. Ownership (note: ADS-level data for ADRs/HK stocks)
        insider_val = get_val("heldPercentInsiders")
        inst_val = get_val("heldPercentInstitutions")
        # Detect if this is an ADR/HK stock (currency mismatch)
        is_adr = fin_currency and currency and fin_currency != currency
        if insider_val is not None and isinstance(insider_val, (int, float)):
            label = f"{round(insider_val*100, 2)}% {'(ADS口径)' if is_adr else ''}".strip()
            m["大股东持股"] = label
        else:
            m["大股东持股"] = "N/A"
        if inst_val is not None and isinstance(inst_val, (int, float)):
            label = f"{round(inst_val*100, 2)}% {'(ADS口径)' if is_adr else ''}".strip()
            m["机构持仓"] = label
        else:
            m["机构持仓"] = "N/A"

        # 8. Market Context
        high = get_val("fiftyTwoWeekHigh")
        low = get_val("fiftyTwoWeekLow")
        curr = get_val("price") or get_val("currentPrice")
        if high and low and curr and high > low:
            percentile = (curr - low) / (high - low)
            m["股价百分位 (52周)"] = pct(percentile)
        else:
            m["股价百分位 (52周)"] = "N/A"

        pe_pct = get_val("pePercentile")
        if pe_pct is not None and isinstance(pe_pct, (int, float)):
            m["PE百分位"] = pct(pe_pct)
        else:
            m["PE百分位"] = ui_data.get("pe_percentile") or "N/A"

        # 9. Extended metrics (Part B): β / ROIC / WACC / dividend / buyback / coal
        m["贝塔系数 (β)"] = ratio(get_val("beta"))
        m["ROIC"] = pct(get_val("roic"))
        _wacc = get_val("wacc")
        m["WACC (估算)"] = pct(_wacc) if _wacc is not None else "N/A"
        _dh = f.get("dividendHistory") or []
        if _dh and isinstance(_dh, list):
            m["近3年分红(每10股)"] = "; ".join(
                f"{h.get('year', '')}: {h.get('pretaxBonusPer10', '')}" for h in _dh if isinstance(h, dict)
            )
        else:
            m["近3年分红(每10股)"] = "N/A"
        _bb = f.get("buyback")
        m["股份回购"] = (_bb.get("title") if isinstance(_bb, dict) else None) or "数据缺失"
        _coal = f.get("coalPrice")
        if isinstance(_coal, dict) and _coal.get("price") is not None:
            m["动力煤价格"] = f"{_coal.get('price')} {_coal.get('unit', '')} ({_coal.get('name', '')})"
        else:
            m["动力煤价格"] = "数据缺失"

        return m

    def _parse_metric_value(self, value_str: str):
        """Extract numeric value from a formatted metric string like '18.68%', '183.79亿 USD', '-22.25%', 'N/A'."""
        if not value_str or value_str == "N/A":
            return None
        s = str(value_str).strip()
        # Remove ADS口径 annotation
        s = s.replace("(ADS口径)", "").replace("(无分红)", "").strip()
        # Handle percentage
        if s.endswith("%"):
            try:
                return float(s[:-1])
            except ValueError:
                return None
        # Handle money values like "183.79亿 USD", "-112.1亿 CNY"
        import re
        m = re.match(r'^([+-]?[\d,.]+)', s)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                return None
        return None

    # Signal rules: metric_name → (green_condition, yellow_condition, red_condition)
    # Returns: "green" (good), "yellow" (neutral/caution), "red" (bad), "gray" (N/A)
    SIGNAL_RULES = {
        # Valuation — lower is better (except EV which is contextual)
        "市盈率 (PE)":       {"green": lambda v: 0 < v < 15, "yellow": lambda v: 15 <= v < 30, "red": lambda v: v >= 30 or v < 0},
        "市净率 (PB)":       {"green": lambda v: 0 < v < 1.5, "yellow": lambda v: 1.5 <= v < 3, "red": lambda v: v >= 3 or v < 0},
        "PEG":              {"green": lambda v: 0 < v < 1, "yellow": lambda v: 1 <= v < 2, "red": lambda v: v >= 2 or v < 0},
        "市销率 (PS)":       {"green": lambda v: 0 < v < 2, "yellow": lambda v: 2 <= v < 5, "red": lambda v: v >= 5},
        "EV/EBITDA":        {"green": lambda v: 0 < v < 10, "yellow": lambda v: 10 <= v < 20, "red": lambda v: v >= 20 or v < 0},
        # Profitability — higher is better
        "净资产收益率 (ROE)": {"green": lambda v: v >= 15, "yellow": lambda v: 5 <= v < 15, "red": lambda v: v < 5},
        "总资产收益率 (ROA)": {"green": lambda v: v >= 8, "yellow": lambda v: 3 <= v < 8, "red": lambda v: v < 3},
        "毛利率":            {"green": lambda v: v >= 30, "yellow": lambda v: 15 <= v < 30, "red": lambda v: v < 15},
        "营业利润率":         {"green": lambda v: v >= 15, "yellow": lambda v: 5 <= v < 15, "red": lambda v: v < 5},
        "净利率":            {"green": lambda v: v >= 10, "yellow": lambda v: 3 <= v < 10, "red": lambda v: v < 3},
        # Growth — positive is good
        "营收同比增长 (YoY)":  {"green": lambda v: v >= 10, "yellow": lambda v: 0 <= v < 10, "red": lambda v: v < 0},
        "营收同比-单季 (YoY-Q)": {"green": lambda v: v >= 10, "yellow": lambda v: 0 <= v < 10, "red": lambda v: v < 0},
        "营收环比增长 (QoQ)":  {"green": lambda v: v >= 5, "yellow": lambda v: 0 <= v < 5, "red": lambda v: v < 0},
        "净利润同比增长 (YoY)": {"green": lambda v: v >= 10, "yellow": lambda v: 0 <= v < 10, "red": lambda v: v < 0},
        "净利润环比增长 (QoQ)": {"green": lambda v: v >= 5, "yellow": lambda v: 0 <= v < 5, "red": lambda v: v < 0},
        "扣非净利润同比增长 (YoY)": {"green": lambda v: v >= 10, "yellow": lambda v: 0 <= v < 10, "red": lambda v: v < 0},
        "扣非净利润环比增长 (QoQ)": {"green": lambda v: v >= 5, "yellow": lambda v: 0 <= v < 5, "red": lambda v: v < 0},
        "营收3年复合增长 (CAGR)": {"green": lambda v: v >= 15, "yellow": lambda v: 5 <= v < 15, "red": lambda v: v < 5},
        "净利润3年复合增长 (CAGR)": {"green": lambda v: v >= 15, "yellow": lambda v: 5 <= v < 15, "red": lambda v: v < 5},
        # Financial Health
        "资产负债率":         {"green": lambda v: v < 40, "yellow": lambda v: 40 <= v < 60, "red": lambda v: v >= 60},
        "流动比率":           {"green": lambda v: v >= 2, "yellow": lambda v: 1 <= v < 2, "red": lambda v: v < 1},
        "速动比率":           {"green": lambda v: v >= 1, "yellow": lambda v: 0.5 <= v < 1, "red": lambda v: v < 0.5},
        # Cash Flow — positive is good
        "分红率":            {"green": lambda v: 20 <= v <= 70, "yellow": lambda v: 0 < v < 20 or 70 < v <= 100, "red": lambda v: v <= 0 or v > 100},
        "股息率":            {"green": lambda v: v >= 3, "yellow": lambda v: 1 <= v < 3, "red": lambda v: v < 1},
        # Efficiency
        "总资产周转率":       {"green": lambda v: v >= 0.8, "yellow": lambda v: 0.4 <= v < 0.8, "red": lambda v: v < 0.4},
        "存货周转率":         {"green": lambda v: v >= 6, "yellow": lambda v: 3 <= v < 6, "red": lambda v: v < 3},
        # Market Context — lower percentile = cheaper (green)
        "股价百分位 (52周)":  {"green": lambda v: v < 30, "yellow": lambda v: 30 <= v < 70, "red": lambda v: v >= 70},
        "PE百分位":          {"green": lambda v: v < 30, "yellow": lambda v: 30 <= v < 70, "red": lambda v: v >= 70},
    }

    def _get_metric_signal(self, metric_name: str, value_str: str) -> str:
        """Return signal color class: 'green', 'yellow', 'red', or 'gray'."""
        val = self._parse_metric_value(value_str)
        if val is None:
            return "gray"
        rules = self.SIGNAL_RULES.get(metric_name)
        if not rules:
            return "gray"
        try:
            if rules["green"](val):
                return "green"
            elif rules["red"](val):
                return "red"
            else:
                return "yellow"
        except Exception:
            return "gray"

    def _render_fund_item(self, metric_name: str, desc: str, value_str: str) -> str:
        """Render a single fund metric item with color signal dot."""
        import html as _html
        signal = self._get_metric_signal(metric_name, value_str)
        signal_html = f'<span class="signal-dot signal-{signal}"></span>'
        # value_str may contain LLM-derived fallback text (ui_data) — escape it
        return (
            f'<div class="fund-item">'
            f'<div class="fund-item-label">{signal_html}{_html.escape(str(metric_name))}<span>{_html.escape(str(desc))}</span></div>'
            f'<div class="fund-item-value">{_html.escape(str(value_str))}</div>'
            f'</div>'
        )

    def _default_scenarios(self):
        return [{"case": "Bull", "probability": 30, "targetPrice": "N/A", "logic": "Market outperformance"}, {"case": "Base", "probability": 50, "targetPrice": "N/A", "logic": "Steady growth"}, {"case": "Bear", "probability": 20, "targetPrice": "N/A", "logic": "Increased competition"}]
