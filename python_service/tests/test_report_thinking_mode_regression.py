"""Regression tests: DeepSeek thinking-mode responses must not break report generation.

Commit f0a5573 enabled DeepSeek V4 thinking mode (reasoning_effort=max). Responses
then arrive as '<think>...reasoning...</think><content>'. The reasoning text
contains '{' fragments (the model plans its JSON there), which hijacked the
first-brace JSON scan in _run_ui_data_expert and forced the markdown-dumping
fallback path — the rendered deep research report ended up displaying raw
'# 🔬 …' markdown inside the "推理 Inference" claim card.

These tests lock in the fixes:
1. JSON extraction tolerates <think> blocks + JSON-like fragments in prose.
2. Fallback/validation never lets raw markdown documents reach structured fields.
"""
import os
import re
import sys
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.services.report_generator_service import ReportGeneratorService

REPORT_MD = """# 🔬 昭衍新药（06127.HK）深度研究分析报告

**日期：2026-08-10 | 分析师：AI 深度研究专家 | 数据截止：2026-08-10 盘中**

---

## 📊 CIO 决策面板

| 维度 | 判断 |
|------|------|
| **核心定调** | 实验猴价格驱动的非经常性利润狂欢，主业仍在亏损边缘徘徊 |

实验猴公允价值变动贡献净利润159.8%，主业持续亏损。表面PE 61x实则严重失真——这是披着CRO外衣的实验猴大宗商品股。
"""


def _extract_json_like_ui_expert(service: ReportGeneratorService, res: str) -> dict:
    """Replicate the JSON extraction block of _run_ui_data_expert (as of the fix)."""
    cleaned = re.sub(r'<think>.*?</think>', '', res, flags=re.DOTALL)
    cleaned = re.sub(r'```(?:json)?\s*\n?', '', cleaned)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = cleaned.strip()

    json_str = ""
    best_candidate = ""
    best_key_count = -1
    for brace_pos in (m.start() for m in re.finditer(r'\{', cleaned)):
        candidate = service._extract_balanced_json(cleaned[brace_pos:])
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
            break
    json_str = best_candidate
    if not json_str:
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            json_str = match.group(0)
    return json.loads(json_str) if json_str else {}


def test_think_block_with_brace_fragments_does_not_hijack_json_extraction():
    """Reasoning text containing {'x': 1}-style fragments must not win the scan."""
    service = ReportGeneratorService()
    res = """<think>
我需要输出一个 JSON 对象。结构应该类似 {"verdict": "...", "tagline": "..."}，让我再想想 {"x": 1}。
实际上先整理思路：1) 提取结论 2) 映射字段。好，现在写最终答案。
</think>

```json
{"verdict": "实验猴价格驱动非经常性利润，主业亏损边缘", "tagline": "昭衍新药：猴价狂欢下的估值陷阱", "investment_thesis": "猴价公允价值变动是不可持续的借来利润", "recommendation": "HOLD", "the_call": "谨慎对待，等待猴价拐点验证", "score": 75}
```
"""
    parsed = _extract_json_like_ui_expert(service, res)
    assert parsed.get("verdict") == "实验猴价格驱动非经常性利润，主业亏损边缘", \
        f"Wrong object extracted (verdict={parsed.get('verdict')!r}) — think block hijacked the scan"
    assert parsed.get("recommendation") == "HOLD"
    assert parsed.get("score") == 75


def test_strip_thinking_prefix_removes_think_blocks():
    service = ReportGeneratorService()
    content = "<think>\n我需要先规划一下输出结构。\n</think>\n\n# 标题\n\n分析正文。"
    stripped = service._strip_thinking_prefix(content)
    assert "<think>" not in stripped
    assert "分析正文" in stripped


def test_fallback_ui_data_sanitizes_markdown_dump():
    """The fallback path must reduce a raw markdown report to plain prose."""
    service = ReportGeneratorService()
    msgs = [{"role": "Deep Research Specialist", "content": REPORT_MD}]
    snapshot = {"quote": {"symbol": "06127"}}
    ui = service._build_fallback_ui_data("06127", msgs, snapshot)
    for field in ("summary", "verdict", "tagline", "investment_thesis", "the_call"):
        val = str(ui.get(field, ""))
        assert "#" not in val, f"{field} still contains raw markdown heading: {val[:60]!r}"
        assert "|" not in val, f"{field} still contains table pipes: {val[:60]!r}"
        assert "**" not in val, f"{field} still contains bold markers: {val[:60]!r}"


def test_validation_cleans_markdown_dump_fields():
    """Structured fields polluted with markdown dumps are cleaned/backfilled."""
    service = ReportGeneratorService()
    ui_data = {
        "verdict": "# 🔬 昭衍新药（06127.HK）深度研究分析报告",
        "tagline": "06127: # 🔬 昭衍新药（06127.HK）深度研究分析报告",
        "investment_thesis": REPORT_MD,
        "the_call": REPORT_MD,
        "recommendation": "HOLD",
        "action_stance": "根据研讨分析结论，当前建议对该标的采取 WATCH 评级指导意见",
        "summary": REPORT_MD,
        "data_completeness": {"score": 100, "missing": [], "impact": ""},
    }
    snapshot = {"quote": {"symbol": "06127"}}
    msgs = [{"role": "Deep Research Specialist", "content": REPORT_MD}]
    service._validate_and_backfill_ui_data(ui_data, msgs, snapshot)
    for field in ("verdict", "tagline", "investment_thesis", "the_call", "summary"):
        val = str(ui_data[field])
        assert "#" not in val and "|" not in val and "**" not in val, \
            f"{field} still contains raw markdown: {val[:80]!r}"


def test_sanitize_markdown_field_drops_tables_and_headers():
    service = ReportGeneratorService()
    clean = service._sanitize_markdown_field(REPORT_MD, max_len=500)
    assert "#" not in clean
    assert "|" not in clean
    assert "**" not in clean
    assert "实验猴公允价值变动" in clean  # substantive prose preserved


def test_render_prose_strips_mid_line_heading_marker():
    """A tagline like '06127: # 🔬 …' must lose the heading marker too."""
    service = ReportGeneratorService()
    val = "06127: # 🔬 昭衍新药（06127.HK）深度研究分析报告"
    assert service._looks_like_markdown_dump(val)
    cleaned = service._render_prose(val, max_len=120)
    assert "#" not in cleaned
    assert "06127" in cleaned


def test_markdown2_chinese_bold_and_structured_data():
    """markdown2 pairs '**' wrongly around CJK text ('**+104%**，其中**美国…**'
    becomes nested garbage). Bold must render as <strong> and LLM
    <structured_data> JSON blocks must be folded away."""
    service = ReportGeneratorService()
    md = (
        "当前猴价已较低点上涨**+104%**，其中**美国《生物安全法案》**影响有限。\n"
        "<structured_data> {\"sentiment\": \"Bearish\", \"score\": 0.4} </structured_data>\n\n"
        "列表项：\n- **核心逻辑**：供不应求\n"
    )
    html = service._markdown_to_html_fallback(md)
    assert "**" not in html, "literal ** leaks into report"
    assert "structured" not in html, "structured_data JSON leaks into report"
    assert "<strong>+104%</strong>" in html
    assert "<strong>美国《生物安全法案》</strong>" in html
    assert "<strong>核心逻辑</strong>" in html


def test_markdown2_bare_lt_does_not_break_dom():
    """Expert text like 'ma50<ma200' must be escaped, not parsed as a tag."""
    service = ReportGeneratorService()
    html = service._markdown_to_html_fallback("均线：ma5>ma20 且 ma50<ma200，中期趋势未坏。")
    assert "ma50&lt;ma200" in html
    assert "<ma200" not in html


def test_fund_table_hides_na_rows_and_shows_derived_metrics():
    """The deep-fundamentals table must hide N/A rows and surface computable
    derived metrics (PS, payout, turnover, beta, WACC...)."""
    service = ReportGeneratorService()
    financials = {
        "marketCap": 20607076050, "price": 26.74, "pe": 61.49, "pb": 2.13,
        "roe": 2.82, "grossMargin": 20.49, "eps": 0.32,
        "revenue": 316135036.49, "netProfit": 238356654.58,
        "revenueGrowthYoY": 10.02, "netProfitGrowthYoY": 479.67,
        "priceToSales": 12.22, "payoutRatio": 0.442, "assetTurnover": 0.03,
        "roic": 2.12, "fiftyTwoWeekHigh": 30.0, "fiftyTwoWeekLow": 20.0,
        "beta": 1.29, "debtRatio": 14.74, "operatingCashflow": 127611163.08,
        "totalCash": 983084920.32, "dividendYield": 0.5,
        "revenueQoQ": 10.02, "netProfitQoQ": 479.67,
        "revenueCagr3y": -5.06, "incomeCagr3y": 8.28,
    }
    fund = service._compile_fundamentals(
        {"financials": financials, "quote": {"currency": "CNY", "changePercent": -1.6}},
        "CNY", {}, market="HK-Share",
    )
    assert "市销率 (PS)" in fund and fund["市销率 (PS)"] == "12.22"
    assert "分红率" in fund and fund["分红率"] == "44.2%"
    assert "总资产周转率" in fund and fund["总资产周转率"] == "0.03"
    assert "ROIC" in fund and fund["ROIC"] == "2.12%"
    assert "贝塔系数 (β)" in fund and fund["贝塔系数 (β)"] == "1.29"
    assert "股价百分位 (52周)" in fund and fund["股价百分位 (52周)"] == "67.4%"
    na_fields = [k for k, v in fund.items() if v == "N/A"]
    assert len(na_fields) < len(fund) * 0.5


def test_render_html_sanitizes_all_llm_text_spots():
    """Render-time defense: even if every LLM field is a markdown dump, the
    final HTML body must not contain raw markdown markers anywhere."""
    service = ReportGeneratorService()
    data = {
        "info": {"name": "昭衍新药", "symbol": "06127", "market": "HK-Share",
                 "price": 27.06, "changePercent": -1.2, "currency": "CNY",
                 "lastUpdated": "2026-08-10 11:35"},
        "fund": {},
        "verdict": REPORT_MD,
        "action_stance": REPORT_MD,
        "tagline": "06127: # 🔬 昭衍新药（06127.HK）深度研究分析报告",
        "investment_thesis": REPORT_MD,
        "factor_profile": {"size": "中盘", "style": "周期", "volatility": "高Beta", "expected_return": "中性"},
        "consensus_vs_non_consensus": {"market_consensus": REPORT_MD, "our_alpha": REPORT_MD},
        "the_call": REPORT_MD,
        "catalyst_calendar": [{"event": REPORT_MD, "date": "2026Q3", "impact_logic": REPORT_MD}],
        "stock_archetype": "Cyclical", "wacc_breakdown": {},
        "kill_switch": {"condition": REPORT_MD, "status": "SAFE"},
        "market_wind_control": {"lockup_date": REPORT_MD, "lockup_impact": REPORT_MD,
                                 "reduction_plan": REPORT_MD, "crowding_level": REPORT_MD},
        "trading_discipline": {"left_side_condition": REPORT_MD, "right_side_trigger": REPORT_MD,
                                "max_drawdown_limit": "-8%", "thesis_invalidation_trigger": REPORT_MD},
        "data_completeness": {"score": 100, "missing": [], "impact": ""},
        "peer_comparison": [{"name": "益诺思", "symbol": "688710", "pe": 30, "pb": 2,
                              "roe": 5, "margin": 10, "marketCap": "50亿", "vs_target": REPORT_MD}],
        "summary": REPORT_MD, "moat_summary": REPORT_MD, "moat_points": [REPORT_MD],
        "macro_summary": REPORT_MD, "macro_points": [REPORT_MD], "trading_plan": REPORT_MD,
        "trading_steps": [{"level": "第一层", "price": "27", "weight": "30%", "logic": REPORT_MD}],
        "risks_points": [REPORT_MD], "key_opps": [REPORT_MD], "key_risks": [REPORT_MD],
        "scenarios": [{"case": "Bull", "probability": 30, "targetPrice": "35", "logic": REPORT_MD}],
        "score": 75, "recommendation": "HOLD",
        "discussion": [{"role": "Deep Research Specialist", "content": "<p>log</p>", "model": "deepseek-v4-pro"}],
        "northbound": {}, "baijiu_price": {}, "snapshot": {},
    }
    html = service._render_html(data)
    body = re.sub(r"<style[\s\S]*?</style>", "", html)
    for marker in ("# 🔬", "**日期", "|------", "## 📊", "<think>", "| **核心定调**", "| 维度 |"):
        assert marker not in body, f"raw markdown leaked into rendered body: {marker}"
    # Structure intact
    assert "推理 Inference" in body and "事实 Fact" in body
    assert "实验猴公允价值变动贡献净利润159.8%" in body
    assert "行业可比公司对标" in body and "催化剂事件日历" in body
