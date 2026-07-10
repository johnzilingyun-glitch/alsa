"""AnalysisPipeline 端到端测试 (mock 各层组件)."""
import asyncio
import pytest

from app.schemas.contracts import (
    ExecutionPlan, AgentSpec, AgentResult, Evidence, AggregatedEvidence,
    AggregatedClaim, CritiqueResult, Issue, Snapshot,
)
from app.agents.decision_agent import FinalDecision
from app.services.analysis_pipeline import (
    AnalysisPipeline, PipelineResult, INTERRUPT_PRE_DECISION, INTERRUPT_POST_REFLECTION,
)
from app.observability.trace import Tracer
from app.services.checkpoint_store import CheckpointStore


# ── mock 各层组件 ────────────────────────────────────────────────────────────

class MockPlanner:
    async def plan(self, symbol, question="", market="", **kw):
        return ExecutionPlan(plan_id=f"plan_{symbol}", symbol=symbol, market=market,
                             agent_manifest=[AgentSpec(agent_id=f"TA@{symbol}", role="Technical Analyst")])

class MockDAG:
    async def run(self, plan, snapshot):
        return [AgentResult(agent_id="TA@AAPL", role="Technical Analyst", status="ok",
                            score=0.75, confidence=0.8, summary="偏多",
                            evidence=[Evidence(claim="金叉", stance="bullish", confidence=0.9, source=["k"], agent="TA")])]
    async def rerun(self, plan, snapshot, ids):
        return [AgentResult(agent_id=i, role="TA", status="ok", score=0.7, confidence=0.8) for i in ids]

class MockAggregator:
    def aggregate(self, results):
        return AggregatedEvidence(
            claims=[AggregatedClaim(claim="金叉",
                     supporting=[Evidence(claim="金叉", stance="bullish", confidence=0.9, source=["k"], agent="TA")],
                     contradicting=[], consensus=1.0)],
            coverage={"Technical Analyst": 0.8})

class MockReflection:
    async def critique(self, aggregated, results, plan=None, snapshot=None, round_num=0):
        return CritiqueResult(can_finalize=True, round_num=round_num)

class MockDecision:
    async def decide(self, aggregated, critique, results, symbol=""):
        return FinalDecision(symbol=symbol, final_score=0.75, stance="bullish", action="buy",
                             confidence=0.8, summary="偏多", key_claims=["[1.0] 金叉"],
                             can_act=True, rationale="test")

def _make_pipeline(**overrides):
    """构造测试用 pipeline (mock 各层)."""
    return AnalysisPipeline(
        planner=overrides.get("planner", MockPlanner()),
        dag=overrides.get("dag", MockDAG()),
        aggregator=overrides.get("aggregator", MockAggregator()),
        reflection=overrides.get("reflection", MockReflection()),
        decision=overrides.get("decision", MockDecision()),
        tracer=Tracer(),
        checkpoint=CheckpointStore(),
    )


# ════════════════════════════════════════════════════════════════════════
# 端到端 run
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_full_run():
    p = _make_pipeline()
    r = await p.run("AAPL", "分析", market="US-Share")
    assert r.status == "ok"
    assert r.decision is not None
    assert r.decision.action == "buy"
    assert r.report != ""
    assert "投资分析报告" in r.report
    assert r.aggregated is not None
    assert r.critique is not None
    assert r.guardrail is not None


@pytest.mark.asyncio
async def test_pipeline_trace_summary():
    p = _make_pipeline()
    r = await p.run("AAPL", "分析")
    assert r.trace_summary["span_count"] >= 6  # planning/execution/aggregation/reflection/decision/guardrail/report
    assert "planning" in r.trace_summary["by_kind"]
    assert "decision" in r.trace_summary["by_kind"]


@pytest.mark.asyncio
async def test_pipeline_on_progress():
    p = _make_pipeline()
    events = []
    r = await p.run("AAPL", "分析", on_progress=lambda s, st, **d: events.append((s, st)))
    stages = [e[0] for e in events]
    assert "planning" in stages
    assert "execution" in stages
    assert "decision" in stages
    assert "done" in [e[1] for e in events]  # 最终 done


# ════════════════════════════════════════════════════════════════════════
# Guardrail 拦截
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_guardrail_block():
    """guardrail block 时用修正决策, status=degraded."""
    class BadDecision(MockDecision):
        async def decide(self, aggregated, critique, results, symbol=""):
            return FinalDecision(symbol=symbol, final_score=0.3, action="buy",  # 低分buy → block
                                 confidence=0.8, summary="矛盾", key_claims=["[1.0] 金叉"],
                                 can_act=True, rationale="t")
    p = _make_pipeline(decision=BadDecision())
    r = await p.run("AAPL", "分析")
    assert r.status == "degraded"
    assert r.guardrail.action == "block"
    assert r.decision.action == "watch"  # 修正决策
    assert r.decision.can_act is False


# ════════════════════════════════════════════════════════════════════════
# HITL 中断 (§10.3 #1)
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_hitl_interrupt_no_callback():
    """无 approval_callback → 暂停 (interrupted)."""
    p = _make_pipeline()
    r = await p.run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION})
    assert r.status == "interrupted"
    assert r.interrupt_point == INTERRUPT_PRE_DECISION
    assert r.critique is not None  # reflection 已完成
    assert r.decision is None      # decision 未执行


@pytest.mark.asyncio
async def test_pipeline_hitl_approved():
    """approval_callback 批准 → 继续."""
    async def approve(point, ctx):
        return True
    p = _make_pipeline()
    r = await p.run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION},
                    approval_callback=approve)
    assert r.status == "ok"
    assert r.decision is not None  # 批准后执行了 decision


@pytest.mark.asyncio
async def test_pipeline_hitl_rejected():
    """approval_callback 拒绝 → aborted."""
    async def approve(point, ctx):
        return False
    p = _make_pipeline()
    r = await p.run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION},
                    approval_callback=approve)
    assert r.status == "aborted"
    assert r.decision is None


@pytest.mark.asyncio
async def test_pipeline_hitl_checkpoint_saved():
    """中断时存 checkpoint, 可 resume."""
    p = _make_pipeline()
    r = await p.run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION})
    assert r.status == "interrupted"
    assert r.plan is not None
    # resume
    restored = p.resume(r.plan.plan_id, INTERRUPT_PRE_DECISION)
    assert restored is not None
    assert restored.status == "interrupted"


# ════════════════════════════════════════════════════════════════════════
# Streaming (§10.3 #3)
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_streaming():
    """run_streaming 产出阶段事件."""
    p = _make_pipeline()
    events = []
    async for ev in p.run_streaming("AAPL", "分析"):
        events.append(ev)
    stages = [e.get("stage") for e in events]
    assert "planning" in stages
    assert "result" in stages  # 最终结果事件
    result_event = next(e for e in events if e.get("stage") == "result")
    assert result_event["status"] == "ok"


# ════════════════════════════════════════════════════════════════════════
# 异常处理
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_exception_aborted():
    """某层抛异常 → status=aborted."""
    class FailDAG(MockDAG):
        async def run(self, plan, snapshot):
            raise RuntimeError("DAG boom")
    p = _make_pipeline(dag=FailDAG())
    r = await p.run("AAPL", "分析")
    assert r.status == "aborted"
    assert "DAG boom" in r.error


@pytest.mark.asyncio
async def test_pipeline_post_reflection_interrupt():
    """post_reflection 中断点."""
    p = _make_pipeline()
    r = await p.run("AAPL", "分析", interrupt_points={INTERRUPT_POST_REFLECTION})
    assert r.status == "interrupted"
    assert r.interrupt_point == INTERRUPT_POST_REFLECTION
    assert r.critique is not None
    assert r.decision is None
