"""剩余优化项测试 — OutputGuardrail / Tracer / DocChunker."""
import time
import pytest

from app.schemas.contracts import (
    AggregatedEvidence, AggregatedClaim, Evidence, CritiqueResult, Issue,
)
from app.agents.decision_agent import FinalDecision
from app.services.output_guardrail import OutputGuardrail, GuardrailResult
from app.observability.trace import Tracer, Span
from app.services.doc_chunker import DocChunker


# ── fixtures ────────────────────────────────────────────────────────────────

def _agg(claims=None, conflicts=None):
    return AggregatedEvidence(claims=claims or [], conflicts=conflicts or [],
                              coverage={"TA": 0.8} if claims else {})

def _claim(claim="X", stance="bullish", conf=0.8, agent="TA"):
    return AggregatedClaim(claim=claim, supporting=[Evidence(claim=claim, stance=stance, confidence=conf, agent=agent)],
                           contradicting=[], consensus=1.0)

def _decision(score=0.75, action="buy", conf=0.8, can_act=True, claims=None, summary="正常"):
    return FinalDecision(symbol="AAPL", final_score=score, stance="bullish", action=action,
                         confidence=conf, summary=summary, key_claims=claims or ["[1.0] X"],
                         can_act=can_act, rationale="test")


# ════════════════════════════════════════════════════════════════════════
# OutputGuardrail
# ════════════════════════════════════════════════════════════════════════

def test_guardrail_empty_evidence_blocks():
    """空证据 → block."""
    g = OutputGuardrail()
    r = g.check(_decision(), _agg(claims=[]))
    assert r.action == "block"
    assert r.overridden_decision is not None
    assert r.overridden_decision.action == "watch"
    assert r.overridden_decision.can_act is False


def test_guardrail_action_score_contradiction_buy_low():
    """buy + 低分 → block."""
    g = OutputGuardrail()
    r = g.check(_decision(score=0.3, action="buy"), _agg(claims=[_claim()]))
    assert r.action == "block"
    assert r.overridden_decision.action == "watch"


def test_guardrail_action_score_contradiction_sell_high():
    """sell + 高分 → block."""
    g = OutputGuardrail()
    r = g.check(_decision(score=0.8, action="sell"), _agg(claims=[_claim()]))
    assert r.action == "block"


def test_guardrail_low_confidence_warn():
    """低置信可执行 → warn (不 block)."""
    g = OutputGuardrail()
    r = g.check(_decision(conf=0.2, can_act=True), _agg(claims=[_claim()]))
    assert r.action in ("warn", "pass")  # warn 但不 block
    assert r.overridden_decision is None


def test_guardrail_score_evidence_mismatch_warn():
    """高分但 consensus 低 → warn."""
    g = OutputGuardrail()
    low_consensus = AggregatedClaim(claim="X", supporting=[Evidence(claim="X", stance="bullish", confidence=0.3, agent="TA")],
                                    contradicting=[], consensus=0.3)
    r = g.check(_decision(score=0.8), _agg(claims=[low_consensus]))
    assert any(i.rule == "score_evidence_mismatch" for i in r.issues)


def test_guardrail_normal_passes():
    """正常决策 → pass."""
    g = OutputGuardrail()
    r = g.check(_decision(score=0.75, action="buy", conf=0.8, claims=["[1.0] X"]),
                _agg(claims=[_claim()]))
    assert r.action == "pass"
    assert r.passed is True


def test_guardrail_invalid_summary_blocks():
    """空摘要 → block."""
    g = OutputGuardrail()
    r = g.check(_decision(summary=""), _agg(claims=[_claim()]))
    assert r.action == "block"


def test_guardrail_override_preserves_metadata():
    """block 后修正决策保留 symbol/risks."""
    g = OutputGuardrail()
    d = _decision(score=0.3, action="buy")
    d.risks = []
    r = g.check(d, _agg(claims=[]))
    assert r.overridden_decision.symbol == "AAPL"
    assert r.overridden_decision.action == "watch"
    assert r.overridden_decision.confidence <= 0.3


# ════════════════════════════════════════════════════════════════════════
# Tracer
# ════════════════════════════════════════════════════════════════════════

def test_tracer_span_contextmanager():
    """span contextmanager 自动 end + duration."""
    t = Tracer()
    with t.span("agent_run", kind="agent") as sp:
        sp.set("role", "TA")
        time.sleep(0.01)
    assert sp.ended
    assert sp.duration_ms > 0
    assert sp.attributes["role"] == "TA"


def test_tracer_parent_child():
    """parent_id 建立调用树."""
    t = Tracer()
    with t.span("root", kind="agent") as root:
        with t.span("child_tool", kind="tool_call", parent_id=root.span_id) as child:
            pass
    assert child.parent_id == root.span_id
    tree = t.tree()
    assert len(tree["roots"]) == 1
    assert tree["roots"][0]["children"][0]["kind"] == "tool_call"


def test_tracer_summary():
    t = Tracer()
    with t.span("a", kind="agent"):
        pass
    with t.span("b", kind="tool_call"):
        pass
    with t.span("c", kind="handoff"):
        pass
    s = t.summary()
    assert s["span_count"] == 3
    assert s["by_kind"]["agent"]["count"] == 1
    assert s["by_kind"]["tool_call"]["count"] == 1


def test_tracer_failed_span():
    """异常 span 标记 failed."""
    t = Tracer()
    with pytest.raises(ValueError):
        with t.span("bad", kind="agent"):
            raise ValueError("boom")
    s = t.summary()
    assert "bad" in s["failed_spans"]


def test_tracer_event():
    t = Tracer()
    with t.span("a", kind="agent") as sp:
        sp.event("checkpoint", detail="saved")
    assert len(sp.events) == 1
    assert sp.events[0]["name"] == "checkpoint"


# ════════════════════════════════════════════════════════════════════════
# DocChunker
# ════════════════════════════════════════════════════════════════════════

def test_chunker_basic():
    c = DocChunker(max_chars=100, overlap=20)
    rows = c.chunk("短段落一。\n\n短段落二。", symbol="AAPL", source="t.md")
    # 两个短段落应合并 (若 < max_chars)
    assert len(rows) >= 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["source"] == "t.md"
    assert "chunk_idx" in rows[0]


def test_chunker_long_text_sliding_window():
    """超长文本滑动窗口 + overlap."""
    c = DocChunker(max_chars=100, overlap=20)
    long_text = "这是一段很长的文本内容。" * 50  # 远超 100
    rows = c.chunk(long_text, symbol="X")
    assert len(rows) > 1
    # 每块 ≤ max_chars (允许小溢出因边界调整)
    for r in rows:
        assert r["char_count"] <= 120


def test_chunker_paragraph_split():
    """按段落分割."""
    c = DocChunker(max_chars=50, overlap=10)
    text = "段落一内容。\n\n段落二内容。\n\n段落三内容。"
    rows = c.chunk(text, symbol="X")
    assert len(rows) >= 1


def test_chunker_empty():
    c = DocChunker()
    assert c.chunk("") == []
    assert c.chunk("   ") == []


def test_chunker_metadata():
    c = DocChunker(max_chars=200, overlap=30)
    rows = c.chunk("内容。", symbol="AAPL", source="r.pdf", doc_type="filing",
                   extra={"author": "analyst"})
    assert rows[0]["doc_type"] == "filing"
    assert rows[0]["author"] == "analyst"


def test_chunker_chunk_many():
    c = DocChunker(max_chars=100, overlap=20)
    docs = [{"text": "文档一内容。", "symbol": "A", "source": "a.md"},
            {"text": "文档二内容。", "symbol": "B", "source": "b.md"}]
    rows = c.chunk_many(docs)
    assert len(rows) >= 2
    symbols = {r["symbol"] for r in rows}
    assert symbols == {"A", "B"}
