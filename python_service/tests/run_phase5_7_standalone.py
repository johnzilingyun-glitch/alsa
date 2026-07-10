"""Phase 5+7 独立测试运行器."""
import sys, os, tempfile, asyncio, traceback
sys.path.insert(0, "python_service")

from app.schemas.contracts import (
    ExecutionPlan, AgentSpec, AgentResult, Evidence, RiskItem,
    AggregatedEvidence, AggregatedClaim, Conflict, CritiqueResult, Issue, Snapshot,
)
from app.agents.decision_agent import FinalDecision
from app.services.checkpoint_store import CheckpointStore
from app.services.memory_store import MemoryStore, MemoryLayer
from app.agents.report_builder import ReportBuilder

passed = failed = 0
def check(n, f):
    global passed, failed
    try: f(); print(f"  PASS  {n}"); passed += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); traceback.print_exc(); failed += 1

def _plan(): return ExecutionPlan(plan_id="p1", symbol="AAPL", market="US-Share", agent_manifest=[AgentSpec(agent_id="TA@AAPL", role="TA")])
def _dec(): return FinalDecision(symbol="AAPL", final_score=0.75, stance="bullish", action="buy", confidence=0.8, summary="技术面偏多", risks=[RiskItem(category="market", description="阻力位", severity="medium")], key_claims=["[0.9] MACD金叉"], can_act=True, rationale="基于3个Agent")
def _agg(): return AggregatedEvidence(claims=[AggregatedClaim(claim="MACD金叉", supporting=[Evidence(claim="金叉", stance="bullish", confidence=0.9, source=["kline"], agent="TA")], contradicting=[Evidence(claim="量不足", stance="bearish", confidence=0.4, source=["kline"], agent="FA")], consensus=0.8)], conflicts=[Conflict(claim="MACD金叉", supporting=[Evidence(claim="金叉", stance="bullish", agent="TA")], contradicting=[Evidence(claim="量不足", stance="bearish", agent="FA")])], coverage={"TA":0.8,"FA":0.7})
def _crit(): return CritiqueResult(issues=[Issue(severity="medium", description="量价背离")], can_finalize=True)

def t_cp_save_resume():
    s=CheckpointStore(); p=_plan(); s.save("j1:p", p); assert s.resume("j1:p") is p
def t_cp_missing():
    assert CheckpointStore().resume("x") is None
def t_cp_list():
    s=CheckpointStore(); s.save("j1:a",1); s.save("j1:b",2); s.save("j2:a",3)
    assert len(s.list_checkpoints("j1"))==2
def t_cp_delete():
    s=CheckpointStore(); s.save("j1:a",1); assert s.delete("j1:a"); assert not s.delete("j1:a")
def t_cp_clear_job():
    s=CheckpointStore(); s.save("j1:a",1); s.save("j1:b",2); s.save("j2:a",3)
    assert s.clear("j1")==2 and s.list_checkpoints("j1")==[]
def t_cp_persist():
    d=tempfile.mkdtemp(); s1=CheckpointStore(persist_dir=d); s1.save("j1:d", _dec())
    s2=CheckpointStore(persist_dir=d); r=s2.resume("j1:d")
    assert r is not None
    score = r.get("final_score") if isinstance(r,dict) else getattr(r,"final_score",None)
    assert score==0.75
def t_cp_types():
    s=CheckpointStore(); s.save("p",_plan()); s.save("r",AgentResult(agent_id="A",role="TA")); s.save("d",_dec())
    assert s.resume("p") is not None and s.resume("r") is not None and s.resume("d") is not None

def t_mem_isolation():
    m=MemoryStore(); m.put(MemoryLayer.SESSION,"k","s"); m.put(MemoryLayer.PROJECT,"k","p"); m.put(MemoryLayer.USER,"k","u")
    assert m.get(MemoryLayer.SESSION,"k")=="s" and m.get(MemoryLayer.PROJECT,"k")=="p" and m.get(MemoryLayer.USER,"k")=="u"
def t_mem_query():
    m=MemoryStore(); m.put(MemoryLayer.SESSION,"j1:a",1); m.put(MemoryLayer.SESSION,"j1:b",2); m.put(MemoryLayer.SESSION,"j2:a",3)
    assert len(m.query(MemoryLayer.SESSION,"j1:"))==2
def t_mem_project_persist():
    d=tempfile.mkdtemp(); m1=MemoryStore(project_dir=d); m1.put(MemoryLayer.PROJECT,"mk","US")
    m2=MemoryStore(project_dir=d); assert m2.get(MemoryLayer.PROJECT,"mk")=="US"
def t_mem_snapshot():
    m=MemoryStore(); k=m.snapshot_session("j1",plan=_plan()); assert k=="j1:session"
    s=m.restore_session("j1"); assert s is not None and s["job_id"]=="j1"
def t_mem_snapshot_cp():
    m=MemoryStore(); cp=CheckpointStore(); m.snapshot_session("j1",plan=_plan(),checkpoint_store=cp)
    assert "j1:session" in cp.list_checkpoints("j1")
    m.clear_session("j1"); assert m.restore_session("j1") is None
    assert m.restore_session("j1",checkpoint_store=cp) is not None
def t_mem_clear():
    m=MemoryStore(); m.put(MemoryLayer.SESSION,"j1:a",1); m.put(MemoryLayer.SESSION,"j1:b",2); m.put(MemoryLayer.SESSION,"j2:a",3)
    assert m.clear_session("j1")==2 and m.query(MemoryLayer.SESSION,"j1")=={}
def t_mem_analysis_fallback():
    m=MemoryStore()
    # remember_analysis: AgentMemory 可用→True (兜底写 Session); 不可用→False
    ok=m.remember_analysis(symbol="AAPL",role="TA",summary="偏多",conclusions=["金叉"])
    # recall_analysis 同步查 Session 兜底
    r=m.recall_analysis(symbol="AAPL",role="TA"); assert len(r)==1 and "偏多" in r[0]["summary"]

def t_rb_structure():
    md=ReportBuilder().build_markdown(_dec(),_agg(),[],_crit())
    assert "投资分析报告" in md and "AAPL" in md and "综合评分" in md and "0.75" in md and "看多" in md and "买入" in md
def t_rb_traceable():
    md=ReportBuilder().build_markdown(_dec(),_agg(),[])
    assert "MACD金叉" in md and "TA" in md and "kline" in md and "source:" in md
def t_rb_conflicts():
    assert "证据冲突" in ReportBuilder().build_markdown(_dec(),_agg(),[])
def t_rb_risks():
    md=ReportBuilder().build_markdown(_dec(),_agg(),[]); assert "风险清单" in md and "阻力位" in md
def t_rb_issues():
    md=ReportBuilder().build_markdown(_dec(),_agg(),[],_crit()); assert "反思问题" in md and "量价背离" in md
def t_rb_dict():
    r=ReportBuilder().build(_dec(),_agg(),[],_crit())
    assert r["symbol"]=="AAPL" and r["score"]==0.75 and len(r["evidence"])==1 and r["evidence"][0]["supporting"][0]["source"]==["kline"]
def t_rb_empty():
    assert "无结构化证据" in ReportBuilder().build_markdown(_dec(),AggregatedEvidence(),[])

if __name__=="__main__":
    print("=== Phase 5+7 测试 (standalone) ===")
    for n,f in [("cp_save_resume",t_cp_save_resume),("cp_missing",t_cp_missing),("cp_list",t_cp_list),
                ("cp_delete",t_cp_delete),("cp_clear_job",t_cp_clear_job),("cp_persist",t_cp_persist),("cp_types",t_cp_types),
                ("mem_isolation",t_mem_isolation),("mem_query",t_mem_query),("mem_project_persist",t_mem_project_persist),
                ("mem_snapshot",t_mem_snapshot),("mem_snapshot_cp",t_mem_snapshot_cp),("mem_clear",t_mem_clear),("mem_analysis_fallback",t_mem_analysis_fallback),
                ("rb_structure",t_rb_structure),("rb_traceable",t_rb_traceable),("rb_conflicts",t_rb_conflicts),
                ("rb_risks",t_rb_risks),("rb_issues",t_rb_issues),("rb_dict",t_rb_dict),("rb_empty",t_rb_empty)]:
        check(n,f)
    print(f"\n=== 结果: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)
