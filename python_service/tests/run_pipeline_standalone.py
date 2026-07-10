"""AnalysisPipeline 独立测试运行器."""
import sys, asyncio, traceback
sys.path.insert(0, "python_service")

from app.schemas.contracts import (
    ExecutionPlan, AgentSpec, AgentResult, Evidence, AggregatedEvidence,
    AggregatedClaim, CritiqueResult, Snapshot,
)
from app.agents.decision_agent import FinalDecision
from app.services.analysis_pipeline import (
    AnalysisPipeline, INTERRUPT_PRE_DECISION, INTERRUPT_POST_REFLECTION,
)
from app.observability.trace import Tracer
from app.services.checkpoint_store import CheckpointStore

passed = failed = 0
def check_async(n, f):
    global passed, failed
    try: asyncio.run(f()); print(f"  PASS  {n}"); passed += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); traceback.print_exc(); failed += 1

class MockPlanner:
    async def plan(self, symbol, question="", market="", **kw):
        return ExecutionPlan(plan_id=f"plan_{symbol}", symbol=symbol, market=market,
                             agent_manifest=[AgentSpec(agent_id=f"TA@{symbol}", role="Technical Analyst")])
class MockDAG:
    async def run(self, plan, snapshot):
        return [AgentResult(agent_id="TA@AAPL", role="Technical Analyst", status="ok", score=0.75, confidence=0.8, summary="偏多", evidence=[Evidence(claim="金叉", stance="bullish", confidence=0.9, source=["k"], agent="TA")])]
    async def rerun(self, plan, snapshot, ids): return [AgentResult(agent_id=i, role="TA", status="ok", score=0.7, confidence=0.8) for i in ids]
class MockAggregator:
    def aggregate(self, results):
        return AggregatedEvidence(claims=[AggregatedClaim(claim="金叉", supporting=[Evidence(claim="金叉", stance="bullish", confidence=0.9, source=["k"], agent="TA")], contradicting=[], consensus=1.0)], coverage={"Technical Analyst": 0.8})
class MockReflection:
    async def critique(self, aggregated, results, plan=None, snapshot=None, round_num=0):
        return CritiqueResult(can_finalize=True, round_num=round_num)
class MockDecision:
    async def decide(self, aggregated, critique, results, symbol=""):
        return FinalDecision(symbol=symbol, final_score=0.75, stance="bullish", action="buy", confidence=0.8, summary="偏多", key_claims=["[1.0] 金叉"], can_act=True, rationale="test")

def _pipe(**ov):
    return AnalysisPipeline(planner=ov.get("planner",MockPlanner()), dag=ov.get("dag",MockDAG()),
        aggregator=ov.get("aggregator",MockAggregator()), reflection=ov.get("reflection",MockReflection()),
        decision=ov.get("decision",MockDecision()), tracer=Tracer(), checkpoint=CheckpointStore())

async def t_full():
    r = await _pipe().run("AAPL", "分析", market="US-Share")
    assert r.status == "ok" and r.decision.action == "buy" and "投资分析报告" in r.report
async def t_trace():
    r = await _pipe().run("AAPL", "分析")
    assert r.trace_summary["span_count"] >= 6 and "decision" in r.trace_summary["by_kind"]
async def t_progress():
    ev = []
    await _pipe().run("AAPL", "分析", on_progress=lambda s, st, **d: ev.append(s))
    assert "planning" in ev and "decision" in ev
async def t_guardrail_block():
    class Bad(MockDecision):
        async def decide(self, a, c, r, symbol=""): return FinalDecision(symbol=symbol, final_score=0.3, action="buy", confidence=0.8, summary="矛盾", key_claims=["[1.0] 金叉"], can_act=True, rationale="t")
    r = await _pipe(decision=Bad()).run("AAPL", "分析")
    assert r.status == "degraded" and r.guardrail.action == "block" and r.decision.action == "watch"
async def t_hitl_no_cb():
    r = await _pipe().run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION})
    assert r.status == "interrupted" and r.interrupt_point == INTERRUPT_PRE_DECISION and r.decision is None
async def t_hitl_approved():
    async def ap(p, c): return True
    r = await _pipe().run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION}, approval_callback=ap)
    assert r.status == "ok" and r.decision is not None
async def t_hitl_rejected():
    async def ap(p, c): return False
    r = await _pipe().run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION}, approval_callback=ap)
    assert r.status == "aborted" and r.decision is None
async def t_hitl_checkpoint():
    p = _pipe()
    r = await p.run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION})
    assert r.status == "interrupted" and r.plan is not None
    restored = p.resume(r.plan.plan_id, INTERRUPT_PRE_DECISION)
    assert restored is not None and restored.status == "interrupted"
async def t_streaming():
    p = _pipe()
    events = []
    async for ev in p.run_streaming("AAPL", "分析"): events.append(ev)
    stages = [e.get("stage") for e in events]
    assert "planning" in stages and "result" in stages
    re = next(e for e in events if e.get("stage") == "result")
    assert re["status"] == "ok"
async def t_exception():
    class FailDAG(MockDAG):
        async def run(self, plan, snapshot): raise RuntimeError("DAG boom")
    r = await _pipe(dag=FailDAG()).run("AAPL", "分析")
    assert r.status == "aborted" and "DAG boom" in r.error
async def t_post_reflect():
    r = await _pipe().run("AAPL", "分析", interrupt_points={INTERRUPT_POST_REFLECTION})
    assert r.status == "interrupted" and r.interrupt_point == INTERRUPT_POST_REFLECTION and r.decision is None

if __name__ == "__main__":
    print("=== AnalysisPipeline 测试 (standalone) ===")
    for n, f in [("full", t_full), ("trace", t_trace), ("progress", t_progress), ("guardrail_block", t_guardrail_block),
                 ("hitl_no_cb", t_hitl_no_cb), ("hitl_approved", t_hitl_approved), ("hitl_rejected", t_hitl_rejected),
                 ("hitl_checkpoint", t_hitl_checkpoint), ("streaming", t_streaming), ("exception", t_exception),
                 ("post_reflect", t_post_reflect)]:
        check_async(n, f)
    print(f"\n=== 结果: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)
