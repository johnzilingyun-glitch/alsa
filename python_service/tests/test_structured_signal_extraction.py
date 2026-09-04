"""Tests for structured trading-signal extraction (smart signal center backend).

Covers the extraction-layer fixes:
1. ``<structured_data>`` contract v2 (action + entryPrice / entryLow / entryHigh)
2. Backward compatibility with the legacy schema (no action/entry fields —
   action derived from recommendation)
3. JSON repair for unescaped inner double quotes (job_81c2b179 pattern)
4. Fallbacks (sentiment=Neutral / recommendation=Hold) when no or unparseable
   JSON block is present
5. The shared ``normalize_action`` taxonomy and verdict mapping consistency
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.services.analysis_job_service import (
    AnalysisJobService,
    _repair_json_payload,
    _verdict_from_recommendation,
)
from python_service.app.services.signal_taxonomy import normalize_action


def _chief(content: str) -> list:
    return [{"role": "Chief Strategist", "content": content, "timestamp": "2026-09-01T00:00:00Z"}]


# ---------------------------------------------------------------------------
# 1. Contract v2 extraction
# ---------------------------------------------------------------------------

def test_extract_full_new_schema_with_action_and_entry_price():
    content = (
        "## 投资结论\n详细分析正文……\n\n"
        "<structured_data>\n"
        '{"sentiment": "Bearish", "recommendation": "Strong Sell", "action": "SELL", '
        '"targetPrice": 88.0, "entryPrice": 101.5, "stopLossPrice": 110.0, '
        '"confidence": 78, "keyRisks": ["需求下滑", "产能过剩"]}'
        "\n</structured_data>"
    )
    fields = AnalysisJobService._extract_structured_fields(_chief(content))

    assert fields["sentiment"] == "Bearish"
    assert fields["recommendation"] == "Strong Sell"
    trading_plan = fields["tradingPlan"]
    assert trading_plan["action"] == "sell"
    assert trading_plan["entryPrice"] == "101.5"
    assert trading_plan["targetPrice"] == "88.0"
    assert trading_plan["stopLoss"] == "110.0"
    assert trading_plan["strategy"].startswith("基于多智能体决策")
    assert fields["keyRisks"] == ["需求下滑", "产能过剩"]


def test_extract_legacy_schema_derives_action_from_recommendation():
    """Old contract without action/entryPrice — action derived from recommendation."""
    content = (
        "<structured_data>\n"
        '{"sentiment": "Bullish", "recommendation": "Strong Buy", "targetPrice": 32.0, '
        '"stopLossPrice": 26.0, "confidence": 80, "keyRisks": ["x"]}'
        "\n</structured_data>"
    )
    fields = AnalysisJobService._extract_structured_fields(_chief(content))

    assert fields["recommendation"] == "Strong Buy"
    # Regression guard: the old verdict mapping dropped "Strong Buy" to watch.
    assert fields["tradingPlan"]["action"] == "buy"
    assert "entryPrice" not in fields["tradingPlan"]
    assert "entryLow" not in fields["tradingPlan"]


def test_extract_entry_range_low_high():
    content = (
        "<structured_data>\n"
        '{"sentiment": "Bullish", "recommendation": "Buy", "action": "BUY", '
        '"entryLow": 120.0, "entryHigh": 125.0, "targetPrice": 140.0, '
        '"stopLossPrice": 112.0, "confidence": 70, "keyRisks": []}'
        "\n</structured_data>"
    )
    fields = AnalysisJobService._extract_structured_fields(_chief(content))

    trading_plan = fields["tradingPlan"]
    assert trading_plan["action"] == "buy"
    assert trading_plan["entryLow"] == "120.0"
    assert trading_plan["entryHigh"] == "125.0"
    # Range contract: no point entryPrice synthesized from the band.
    assert "entryPrice" not in trading_plan


def test_extract_tolerates_range_string_prices():
    """Multi-target sector tasks may emit range strings — must pass through."""
    content = (
        "<structured_data>\n"
        '{"sentiment": "Bullish", "recommendation": "增持", "action": "BUY", '
        '"targetPrice": "27.5-30.0", "entryPrice": "25.8-26.5", "stopLossPrice": 23.0, '
        '"confidence": 60, "keyRisks": ["板块轮动"]}'
        "\n</structured_data>"
    )
    fields = AnalysisJobService._extract_structured_fields(_chief(content))

    trading_plan = fields["tradingPlan"]
    assert trading_plan["targetPrice"] == "27.5-30.0"
    assert trading_plan["entryPrice"] == "25.8-26.5"
    assert trading_plan["action"] == "buy"


def test_null_entry_price_is_omitted():
    """Contract: entryPrice null (no defensible entry level) → field omitted."""
    content = (
        "<structured_data>\n"
        '{"sentiment": "Neutral", "recommendation": "Hold", "action": "HOLD", '
        '"entryPrice": null, "targetPrice": 100.0, "stopLossPrice": 92.0, '
        '"confidence": 50, "keyRisks": []}'
        "\n</structured_data>"
    )
    fields = AnalysisJobService._extract_structured_fields(_chief(content))
    assert "entryPrice" not in fields["tradingPlan"]
    assert fields["tradingPlan"]["action"] == "hold"


def test_last_chief_strategist_message_wins():
    old_msg = _chief(
        "<structured_data>\n"
        '{"sentiment": "Bullish", "recommendation": "Buy", "targetPrice": 30.0, '
        '"stopLossPrice": 25.0, "confidence": 80, "keyRisks": []}'
        "\n</structured_data>"
    )
    new_msg = _chief(
        "<structured_data>\n"
        '{"sentiment": "Bearish", "recommendation": "Sell", "action": "SELL", '
        '"targetPrice": 18.0, "entryPrice": 22.0, "stopLossPrice": 24.0, '
        '"confidence": 65, "keyRisks": []}'
        "\n</structured_data>"
    )
    fields = AnalysisJobService._extract_structured_fields([old_msg[0], new_msg[0]])
    assert fields["sentiment"] == "Bearish"
    assert fields["tradingPlan"]["action"] == "sell"
    assert fields["tradingPlan"]["entryPrice"] == "22.0"


# ---------------------------------------------------------------------------
# 2. JSON repair (job_81c2b179 pattern)
# ---------------------------------------------------------------------------

def test_repair_real_case_inner_quotes_in_key_risks():
    """job_81c2b179: unescaped inner quotes in keyRisks used to kill the whole
    parse, silently dropping the Sell signal (frontend then fabricated prices)."""
    content = (
        "## 投资结论\n正文……\n\n"
        "<structured_data>\n"
        '{"sentiment": "Bearish", "recommendation": "Sell", "targetPrice": 95.0, '
        '"stopLossPrice": 105.0, "confidence": 65, '
        '"keyRisks": ["α报告"电子特气+军工占比40%"核心论点失效"]}'
        "\n</structured_data>"
    )
    fields = AnalysisJobService._extract_structured_fields(_chief(content))

    assert fields["sentiment"] == "Bearish"
    assert fields["recommendation"] == "Sell"
    # action derived from recommendation (no explicit action in this legacy payload)
    assert fields["tradingPlan"]["action"] == "sell"
    assert fields["tradingPlan"]["targetPrice"] == "95.0"
    assert fields["keyRisks"] == ['α报告"电子特气+军工占比40%"核心论点失效']


def test_repair_json_payload_escapes_inner_quotes():
    payload = '{"a": "x"y"z", "b": 1}'
    repaired = _repair_json_payload(payload)
    assert repaired == '{"a": "x\\"y\\"z", "b": 1}'
    assert json.loads(repaired) == {"a": 'x"y"z', "b": 1}


def test_repair_json_payload_keeps_escaped_sequences():
    payload = '{"a": "already \\"ok\\"", "b": "tail"quote"}'
    repaired = _repair_json_payload(payload)
    assert json.loads(repaired) == {"a": 'already "ok"', "b": "tail\"quote"}


def test_repair_json_payload_returns_none_when_nothing_fixable():
    # No string content to repair → None (repair cannot help, caller gives up).
    assert _repair_json_payload("{not json at all}") is None
    # Valid quoting already → nothing changed → None.
    assert _repair_json_payload('{"a": "b"}') is None


def test_broken_json_block_falls_back_to_neutral_hold():
    content = "分析正文……\n<structured_data>\n{这不是JSON}\n</structured_data>"
    fields = AnalysisJobService._extract_structured_fields(_chief(content))
    assert fields["sentiment"] == "Neutral"
    assert fields["recommendation"] == "Hold"
    assert fields["tradingPlan"]["action"] == "watch"
    assert fields["keyRisks"] == []


def test_missing_json_block_falls_back_to_neutral_hold():
    content = "## 报告\n没有任何结构化尾注的正文。"
    fields = AnalysisJobService._extract_structured_fields(_chief(content))
    assert fields["sentiment"] == "Neutral"
    assert fields["recommendation"] == "Hold"
    assert fields["tradingPlan"]["action"] == "watch"


def test_no_chief_message_falls_back_to_defaults():
    msgs = [{"role": "Technical Analyst", "content": "MACD 金叉，量能温和。"}]
    fields = AnalysisJobService._extract_structured_fields(msgs)
    assert fields["sentiment"] == "Neutral"
    assert fields["recommendation"] == "Hold"
    assert fields["tradingPlan"]["action"] == "watch"
    # Expert content still surfaces.
    assert "MACD" in fields["technicalAnalysis"]


# ---------------------------------------------------------------------------
# 3. Shared taxonomy + verdict mapping
# ---------------------------------------------------------------------------

TAXONOMY_CASES = [
    # buy group
    ("Buy", "buy"),
    ("buy", "buy"),
    ("Strong Buy", "buy"),
    ("strong buy", "buy"),
    ("Overweight", "buy"),
    ("买入", "buy"),
    ("增持", "buy"),
    ("长多", "buy"),
    ("维持买入评级", "buy"),  # containment
    # sell group
    ("Sell", "sell"),
    ("Strong Sell", "sell"),
    ("strong sell", "sell"),
    ("Underweight", "sell"),
    ("减持", "sell"),
    ("卖出", "sell"),
    ("看空", "sell"),
    ("Avoid", "sell"),
    ("避险", "sell"),
    ("Reduce", "sell"),
    ("建议减持", "sell"),  # containment
    # hold group
    ("Hold", "hold"),
    ("HOLD", "hold"),
    ("持有", "hold"),
    ("观望", "hold"),
    ("Neutral", "hold"),
    ("中性", "hold"),
    ("Watch", "hold"),
    # watch / garbage / negation
    ("暂不建仓", "watch"),
    ("Needs Review", "watch"),
    ("升级乱码评级", "watch"),
    ("buy or sell", "watch"),  # ambiguous multi-group hit
    ("Not Buy", "watch"),  # prefix negation
    ("不建议买入", "watch"),
    ("", "watch"),
    (None, "watch"),
]


@pytest.mark.parametrize("rec,expected", TAXONOMY_CASES)
def test_normalize_action(rec, expected):
    assert normalize_action(rec) == expected


@pytest.mark.parametrize("rec,expected", TAXONOMY_CASES)
def test_verdict_mapping_matches_taxonomy(rec, expected):
    """AnalysisRun.summary_verdict mapping must equal the shared taxonomy —
    regression guard for the old exact-match bug where Strong Buy / 中文评级
    all fell through to 'watch'."""
    assert _verdict_from_recommendation(rec) == expected
    assert _verdict_from_recommendation(rec) == normalize_action(rec)


def test_not_recommended_is_never_buy():
    # Documented behavior: prefix negation demotes to watch, so "Not
    # Recommended" can never resolve to buy via containment.
    assert normalize_action("Not Recommended") == "watch"
    assert normalize_action("Not Recommended") != "buy"
    assert _verdict_from_recommendation("Not Recommended") == "watch"
