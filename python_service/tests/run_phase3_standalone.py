"""Phase 3 独立测试运行器 (绕过 conftest 重型导入)."""
import sys, asyncio, traceback
sys.path.insert(0, "python_service")

from app.schemas.contracts import (
    ExecutionPlan, AgentSpec, AgentResult, Evidence, Snapshot, DAGSpec,
)
from app.engine.dag_engine import DAGEngine
from app.services.planner_service import PlannerService, detect_market
from app.services.evidence_store import EvidenceAggregator

passed = failed = 0
def check(n, f):
    global passed, failed
    try: f(); print(f"  PASS  {n}"); passed += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); traceback.print_exc(); failed += 1
def check_async(n, f):
    global passed, failed
    try: asyncio.run(f()); print(f"  PASS  {n}"); passed += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); traceback.print_exc(); failed += 1

def make_mock_factory(stance="bullish", fail_roles=()):
    class _A:
        def __init__(s, role, agent_id=""): s.role=role; s.agent_id=agent_id or role
        async def run(s, plan, snapshot):
            if s.role in fail_roles:
                return AgentResult(agent_id=s.agent_id, role=s.role, status="degraded", summary="(fail)", confidence=0.3)
            return AgentResult(agent_id=s.agent_id, role=s.role, status="ok", summary=f"mock {s.role}", score=0.7, confidence=0.8,
                               evidence=[Evidence(claim=f"{s.role} view", stance=stance, confidence=0.8, agent=s.role)])
    return lambda role, agent_id="": _A(role, agent_id)

def _plan(agents, dag=None):
    return ExecutionPlan(plan_id="t", symbol="AAPL", market="US-Share", agent_manifest=agents, dag=dag or DAGSpec())

def t_parallel_branches():
    eng = DAGEngine(agent_factory=make_mock_factory())
    layers = eng.build_parallel_branches(_plan([AgentSpec(agent_id="A", role="TA"), AgentSpec(agent_id="B", role="FA"), AgentSpec(agent_id="C", role="SA")]))
    assert len(layers)==1 and len(layers[0])==3

def t_branches_with_deps():
    eng = DAGEngine(agent_factory=make_mock_factory())
    layers = eng.build_parallel_branches(_plan([AgentSpec(agent_id="A", role="TA"), AgentSpec(agent_id="B", role="FA", depends_on=["A"]), AgentSpec(agent_id="C", role="MA", depends_on=["A"])]))
    assert len(layers)==2 and layers[0][0].agent_id=="A"
    assert {a.agent_id for a in layers[1]}=={"B","C"}

def t_circular():
    eng = DAGEngine(agent_factory=make_mock_factory())
    layers = eng.build_parallel_branches(_plan([AgentSpec(agent_id="A", role="TA", depends_on=["B"]), AgentSpec(agent_id="B", role="FA", depends_on=["A"])]))
    assert sum(len(l) for l in layers)==2

async def t_run_parallel():
    eng = DAGEngine(agent_factory=make_mock_factory())
    r = await eng.run(_plan([AgentSpec(agent_id="A", role="TA"), AgentSpec(agent_id="B", role="FA")]), Snapshot())
    assert len(r)==2 and all(x.status=="ok" for x in r)

async def t_short_circuit():
    def fac(role, agent_id=""):
        class _A:
            def __init__(s): s.role=role; s.agent_id=agent_id or role
            async def run(s, plan, snap):
                if role=="TA": return AgentResult(agent_id=s.agent_id, role=role, status="ok", summary="数据严重不足")
                return AgentResult(agent_id=s.agent_id, role=role, status="ok", summary="ok")
        return _A()
    eng = DAGEngine(agent_factory=fac)
    r = await eng.run(_plan([AgentSpec(agent_id="A", role="TA"), AgentSpec(agent_id="B", role="FA", depends_on=["A"])]), Snapshot())
    b = next(x for x in r if x.role=="FA"); assert b.status=="skipped"

async def t_rerun():
    eng = DAGEngine(agent_factory=make_mock_factory())
    r = await eng.rerun(_plan([AgentSpec(agent_id="A", role="TA"), AgentSpec(agent_id="B", role="FA")]), Snapshot(), ["A"])
    assert len(r)==1 and r[0].agent_id=="A"

async def t_failure_degrades():
    eng = DAGEngine(agent_factory=make_mock_factory(fail_roles=("FA",)))
    r = await eng.run(_plan([AgentSpec(agent_id="A", role="TA"), AgentSpec(agent_id="B", role="FA")]), Snapshot())
    assert next(x for x in r if x.role=="FA").status=="degraded"
    assert next(x for x in r if x.role=="TA").status=="ok"

def t_detect_market():
    assert detect_market("600519.SH")=="A-Share"
    assert detect_market("0700.HK")=="HK-Share"
    assert detect_market("AAPL")=="US-Share"

async def t_planner_a():
    p = PlannerService(); plan = await p.plan("600519.SH", "分析", market="A-Share")
    roles=[a.role for a in plan.agent_manifest]
    assert all(r in roles for r in ["Technical Analyst","Fundamental Analyst","Sentiment Analyst"])
    ta=next(a for a in plan.agent_manifest if a.role=="Technical Analyst")
    assert "News Analyst" in [s.role for s in ta.subagents]

async def t_planner_hk():
    p = PlannerService(); plan = await p.plan("0700.HK", "分析", market="HK-Share")
    assert "Macro Analyst" in [a.role for a in plan.agent_manifest]
    ma=next(a for a in plan.agent_manifest if a.role=="Macro Analyst")
    assert "Risk Quantifier" in [s.role for s in ma.subagents]

async def t_planner_us():
    p = PlannerService(); plan = await p.plan("AAPL", "分析")
    ma=next(a for a in plan.agent_manifest if a.role=="Macro Analyst")
    assert "Valuation Analyst" in [s.role for s in ma.subagents]

async def t_planner_insufficient():
    p = PlannerService(); plan = await p.plan("X", "分析", market="US-Share", data_availability="insufficient")
    assert len(plan.agent_manifest)==1 and plan.agent_manifest[0].role=="Technical Analyst"

async def t_planner_toolmap():
    p = PlannerService(); plan = await p.plan("AAPL", "分析")
    qt = next(t for t in plan.data_fetch_manifest if t.data_type=="realtime_quote")
    assert len(qt.tools)>0 and qt.tools[0].tool_id=="fetch_realtime_quote" and qt.tools[0].priority==1

async def t_planner_dynamic_count():
    p = PlannerService()
    a = await p.plan("600519.SH", "分析", market="A-Share")
    ins = await p.plan("X", "分析", market="US-Share", data_availability="insufficient")
    assert len(ins.agent_manifest) < len(a.agent_manifest)

def t_agg_stance():
    agg = EvidenceAggregator()
    ae = agg.aggregate([AgentResult(agent_id="A", role="TA", evidence=[
        Evidence(claim="金叉", stance="bullish", confidence=0.9, agent="TA"),
        Evidence(claim="金叉", stance="bearish", confidence=0.4, agent="FA")])])
    assert len(ae.claims)==1 and len(ae.claims[0].supporting)==1 and len(ae.claims[0].contradicting)==1
    assert ae.claims[0].contradicting[0].confidence==0.4  # v3.1: 低conf仍是反对

def t_agg_conflict():
    agg = EvidenceAggregator()
    ae = agg.aggregate([AgentResult(agent_id="A", role="TA", evidence=[
        Evidence(claim="X", stance="bullish", agent="TA"), Evidence(claim="X", stance="bearish", agent="FA")])])
    assert len(ae.conflicts)==1

def t_agg_no_conflict():
    agg = EvidenceAggregator()
    ae = agg.aggregate([AgentResult(agent_id="A", role="TA", evidence=[
        Evidence(claim="X", stance="bullish", agent="TA"), Evidence(claim="X", stance="bullish", agent="FA")])])
    assert len(ae.conflicts)==0 and ae.claims[0].consensus==1.0

def t_agg_consensus():
    agg = EvidenceAggregator()
    ae = agg.aggregate([AgentResult(agent_id="A", role="TA", evidence=[
        Evidence(claim="X", stance="bullish", confidence=0.8, agent="TA"),
        Evidence(claim="X", stance="bearish", confidence=0.2, agent="FA")])])
    assert ae.claims[0].consensus==0.8

def t_agg_coverage():
    agg = EvidenceAggregator()
    ae = agg.aggregate([
        AgentResult(agent_id="A", role="TA", status="ok", evidence=[Evidence(claim="x", stance="bullish", confidence=0.8, agent="TA")]),
        AgentResult(agent_id="B", role="FA", status="skipped"),
        AgentResult(agent_id="C", role="MA", status="degraded")])
    assert ae.coverage["TA"]>ae.coverage["FA"] and ae.coverage["FA"]==0.0 and ae.coverage["MA"]==0.3

if __name__=="__main__":
    print("=== Phase 3 测试 (standalone) ===")
    for n,f in [("parallel_branches",t_parallel_branches),("branches_with_deps",t_branches_with_deps),("circular",t_circular),
                ("detect_market",t_detect_market),("agg_stance",t_agg_stance),("agg_conflict",t_agg_conflict),
                ("agg_no_conflict",t_agg_no_conflict),("agg_consensus",t_agg_consensus),("agg_coverage",t_agg_coverage)]:
        check(n,f)
    for n,f in [("run_parallel",t_run_parallel),("short_circuit",t_short_circuit),("rerun",t_rerun),("failure_degrades",t_failure_degrades),
                ("planner_a",t_planner_a),("planner_hk",t_planner_hk),("planner_us",t_planner_us),
                ("planner_insufficient",t_planner_insufficient),("planner_toolmap",t_planner_toolmap),("planner_dynamic_count",t_planner_dynamic_count)]:
        check_async(n,f)
    print(f"\n=== 结果: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)
