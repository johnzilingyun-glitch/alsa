"""Phase 4 独立测试运行器."""
import sys, asyncio, traceback
sys.path.insert(0, "python_service")

from app.schemas.contracts import (
    AggregatedEvidence, AggregatedClaim, Conflict, CritiqueResult, Issue,
    AgentResult, Evidence, ExecutionPlan, Snapshot, AgentSpec, RiskItem,
)
from app.agents.reflection_agent import ReflectionAgent
from app.services.role_router import resolve_tier, resolve_model, resolve_budget, estimate_cost_saving
from app.agents.decision_agent import DecisionAgent

passed = failed = 0
def check(n, f):
    global passed, failed
    try: f(); print(f"  PASS  {n}"); passed += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); traceback.print_exc(); failed += 1
def check_async(n, f):
    global passed, failed
    try: asyncio.run(f()); print(f"  PASS  {n}"); passed += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); traceback.print_exc(); failed += 1

def _ev(claim, stance, conf=0.8, agent="TA"):
    return Evidence(claim=claim, stance=stance, confidence=conf, agent=agent)
def _r(role="TA", aid="A", status="ok", score=0.7, conf=0.8):
    return AgentResult(agent_id=aid, role=role, status=status, score=score, confidence=conf)
def _agg(claims=None, conflicts=None, coverage=None):
    return AggregatedEvidence(claims=claims or [], conflicts=conflicts or [], coverage=coverage or {"TA":0.8})

# role_router
def t_tier():
    assert resolve_tier("Planner")=="flash" and resolve_tier("Technical Analyst")=="pro" and resolve_tier("X")=="pro"
def t_model():
    assert resolve_model("Planner")!=resolve_model("Technical Analyst")
def t_budget():
    assert resolve_budget("Technical Analyst",is_rerun=True)==resolve_budget("Technical Analyst")+2000
    assert resolve_budget("Fundamental Analyst",is_rerun=True)==12000
def t_cost():
    assert estimate_cost_saving(["Planner","News Analyst","Technical Analyst"])["saving_rate"]>0.5

# reflection
def t_no_conflict_finalize():
    r=ReflectionAgent()
    c=asyncio.run(r.critique(_agg(claims=[AggregatedClaim(claim="X",supporting=[_ev("X","bullish")],contradicting=[],consensus=1.0)],coverage={"TA":0.8,"FA":0.7}),[_r("TA","A"),_r("FA","B")]))
    assert c.can_finalize and c.rerun_agents==[]
def t_conflict_rerun():
    r=ReflectionAgent()
    c=asyncio.run(r.critique(_agg(conflicts=[Conflict(claim="金叉",supporting=[_ev("金叉","bullish",agent="TA")],contradicting=[_ev("金叉","bearish",agent="FA")])],coverage={"TA":0.8,"FA":0.7}),[_r("TA","TA@AAPL"),_r("FA","FA@AAPL")]))
    assert not c.can_finalize and len(c.rerun_agents)>0
def t_skipped_rerun():
    r=ReflectionAgent()
    c=asyncio.run(r.critique(_agg(coverage={"TA":0.0}),[_r("TA","A",status="skipped")]))
    assert not c.can_finalize and "A" in c.rerun_agents
def t_max_rounds():
    r=ReflectionAgent(max_rounds=1)
    c=asyncio.run(r.critique(_agg(conflicts=[Conflict(claim="X",supporting=[_ev("X","bullish")],contradicting=[_ev("X","bearish")])]),[_r("TA","A"),_r("FA","B")],round_num=1))
    assert c.can_finalize and any("强制" in i.description for i in c.issues)
def t_merge():
    old=[_r("TA","A",score=0.5),_r("FA","B",score=0.6)]
    new=[_r("TA","A",score=0.9)]
    m=ReflectionAgent._merge(old,new)
    assert next(x for x in m if x.agent_id=="A").score==0.9
    assert next(x for x in m if x.agent_id=="B").score==0.6

async def t_rerun_recursion():
    class _DAG:
        async def rerun(self,plan,snap,ids): return [AgentResult(agent_id=i,role="TA",status="ok",score=0.7,confidence=0.8) for i in ids]
    n={"n":0}
    class _Agg:
        def aggregate(self,results):
            n["n"]+=1
            if n["n"]==1: return _agg(conflicts=[Conflict(claim="X",supporting=[_ev("X","bullish")],contradicting=[_ev("X","bearish")])],coverage={"TA":0.8})
            return _agg(coverage={"TA":0.8})
    r=ReflectionAgent(dag_engine=_DAG(),aggregator=_Agg())
    plan=ExecutionPlan(plan_id="t",symbol="AAPL",market="US-Share",agent_manifest=[AgentSpec(agent_id="TA@AAPL",role="TA")])
    c=await r.critique(_agg(conflicts=[Conflict(claim="X",supporting=[_ev("X","bullish")],contradicting=[_ev("X","bearish")])],coverage={"TA":0.8}),[_r("TA","TA@AAPL")],plan,Snapshot())
    assert c.can_finalize and c.round_num>=1

async def t_decision_buy():
    d=DecisionAgent()
    fd=await d.decide(_agg(claims=[AggregatedClaim(claim="强势",supporting=[_ev("强势","bullish")],contradicting=[],consensus=1.0)],coverage={"TA":0.8}),CritiqueResult(can_finalize=True),[_r("TA","A",score=0.8,conf=0.9)],symbol="AAPL")
    assert fd.action=="buy" and fd.can_act and fd.stance=="bullish"
async def t_decision_sell():
    d=DecisionAgent()
    fd=await d.decide(_agg(coverage={"TA":0.8}),CritiqueResult(can_finalize=True),[_r("TA","A",score=0.3,conf=0.8)])
    assert fd.action=="sell"
async def t_decision_watch():
    d=DecisionAgent()
    fd=await d.decide(_agg(coverage={"TA":0.8}),CritiqueResult(can_finalize=False,issues=[Issue(severity="high",description="冲突")]),[_r("TA","A",score=0.8,conf=0.9)])
    assert fd.action=="watch" and not fd.can_act and fd.confidence<0.9
async def t_decision_risks():
    d=DecisionAgent()
    results=[AgentResult(agent_id="A",role="TA",status="ok",score=0.7,confidence=0.8,risk=[RiskItem(category="market",description="阻力位",severity="medium")]),
             AgentResult(agent_id="B",role="FA",status="ok",score=0.7,confidence=0.8,risk=[RiskItem(category="market",description="阻力位",severity="medium"),RiskItem(category="liq",description="流动性差",severity="high")])]
    fd=await d.decide(_agg(coverage={"TA":0.8,"FA":0.7}),CritiqueResult(can_finalize=True),results)
    assert len(fd.risks)==2
async def t_decision_keyclaims():
    d=DecisionAgent()
    agg=_agg(claims=[AggregatedClaim(claim="强势信号",supporting=[_ev("强势信号","bullish")],contradicting=[],consensus=0.9),
                     AggregatedClaim(claim="弱信号",supporting=[_ev("弱信号","neutral")],contradicting=[],consensus=0.5)],coverage={"TA":0.8})
    fd=await d.decide(agg,CritiqueResult(can_finalize=True),[_r("TA","A")])
    assert any("强势信号" in c for c in fd.key_claims) and not any("弱信号" in c for c in fd.key_claims)

if __name__=="__main__":
    print("=== Phase 4 测试 (standalone) ===")
    for n,f in [("tier",t_tier),("model",t_model),("budget",t_budget),("cost",t_cost),
                ("no_conflict_finalize",t_no_conflict_finalize),("conflict_rerun",t_conflict_rerun),
                ("skipped_rerun",t_skipped_rerun),("max_rounds",t_max_rounds),("merge",t_merge)]:
        check(n,f)
    for n,f in [("rerun_recursion",t_rerun_recursion),("decision_buy",t_decision_buy),("decision_sell",t_decision_sell),
                ("decision_watch",t_decision_watch),("decision_risks",t_decision_risks),("decision_keyclaims",t_decision_keyclaims)]:
        check_async(n,f)
    print(f"\n=== 结果: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)
