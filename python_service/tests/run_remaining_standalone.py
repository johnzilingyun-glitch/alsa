"""剩余优化项独立测试运行器."""
import sys, time, traceback
sys.path.insert(0, "python_service")

from app.schemas.contracts import AggregatedEvidence, AggregatedClaim, Evidence, CritiqueResult, Issue
from app.agents.decision_agent import FinalDecision
from app.services.output_guardrail import OutputGuardrail
from app.observability.trace import Tracer
from app.services.doc_chunker import DocChunker

passed = failed = 0
def check(n, f):
    global passed, failed
    try: f(); print(f"  PASS  {n}"); passed += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); traceback.print_exc(); failed += 1

def _agg(claims=None): return AggregatedEvidence(claims=claims or [], coverage={"TA":0.8} if claims else {})
def _claim(c="X"): return AggregatedClaim(claim=c, supporting=[Evidence(claim=c, stance="bullish", confidence=0.8, agent="TA")], contradicting=[], consensus=1.0)
def _dec(score=0.75, action="buy", conf=0.8, can_act=True, claims=None, summary="正常"):
    return FinalDecision(symbol="AAPL", final_score=score, stance="bullish", action=action, confidence=conf, summary=summary, key_claims=claims or ["[1.0] X"], can_act=can_act, rationale="t")

# guardrail
def t_g_empty():
    r=OutputGuardrail().check(_dec(), _agg())
    assert r.action=="block" and r.overridden_decision.action=="watch" and not r.overridden_decision.can_act
def t_g_buy_low():
    r=OutputGuardrail().check(_dec(score=0.3,action="buy"), _agg(claims=[_claim()])); assert r.action=="block"
def t_g_sell_high():
    r=OutputGuardrail().check(_dec(score=0.8,action="sell"), _agg(claims=[_claim()])); assert r.action=="block"
def t_g_low_conf():
    r=OutputGuardrail().check(_dec(conf=0.2,can_act=True), _agg(claims=[_claim()])); assert r.action in ("warn","pass")
def t_g_mismatch():
    lc=AggregatedClaim(claim="X",supporting=[Evidence(claim="X",stance="bullish",confidence=0.3,agent="TA")],contradicting=[],consensus=0.3)
    r=OutputGuardrail().check(_dec(score=0.8), _agg(claims=[lc])); assert any(i.rule=="score_evidence_mismatch" for i in r.issues)
def t_g_pass():
    r=OutputGuardrail().check(_dec(score=0.75,action="buy",conf=0.8), _agg(claims=[_claim()])); assert r.action=="pass"
def t_g_invalid_summary():
    r=OutputGuardrail().check(_dec(summary=""), _agg(claims=[_claim()])); assert r.action=="block"
def t_g_override_meta():
    r=OutputGuardrail().check(_dec(score=0.3,action="buy"), _agg())
    assert r.overridden_decision.symbol=="AAPL" and r.overridden_decision.action=="watch"

# tracer
def t_t_ctxmgr():
    t=Tracer()
    with t.span("agent_run",kind="agent") as sp:
        sp.set("role","TA"); time.sleep(0.01)
    assert sp.ended and sp.duration_ms>0 and sp.attributes["role"]=="TA"
def t_t_parent():
    t=Tracer()
    with t.span("root",kind="agent") as root:
        with t.span("child",kind="tool_call",parent_id=root.span_id) as ch: pass
    assert ch.parent_id==root.span_id
    tr=t.tree(); assert len(tr["roots"])==1 and tr["roots"][0]["children"][0]["kind"]=="tool_call"
def t_t_summary():
    t=Tracer()
    with t.span("a",kind="agent"): pass
    with t.span("b",kind="tool_call"): pass
    s=t.summary(); assert s["span_count"]==2 and s["by_kind"]["agent"]["count"]==1
def t_t_failed():
    t=Tracer()
    try:
        with t.span("bad",kind="agent"): raise ValueError("x")
    except ValueError: pass
    assert "bad" in t.summary()["failed_spans"]
def t_t_event():
    t=Tracer()
    with t.span("a",kind="agent") as sp: sp.event("ckpt",d="s")
    assert len(sp.events)==1 and sp.events[0]["name"]=="ckpt"

# chunker
def t_c_basic():
    rows=DocChunker(max_chars=100,overlap=20).chunk("短一。\n\n短二。",symbol="AAPL",source="t.md")
    assert len(rows)>=1 and rows[0]["symbol"]=="AAPL" and "chunk_idx" in rows[0]
def t_c_long():
    rows=DocChunker(max_chars=100,overlap=20).chunk("长文本内容。"*50,symbol="X")
    assert len(rows)>1
    for r in rows: assert r["char_count"]<=120
def t_c_para():
    rows=DocChunker(max_chars=50,overlap=10).chunk("段一。\n\n段二。\n\n段三。",symbol="X"); assert len(rows)>=1
def t_c_empty():
    assert DocChunker().chunk("")==[] and DocChunker().chunk("   ")==[]
def t_c_meta():
    rows=DocChunker(max_chars=200).chunk("内容。",symbol="AAPL",source="r.pdf",doc_type="filing",extra={"author":"a"})
    assert rows[0]["doc_type"]=="filing" and rows[0]["author"]=="a"
def t_c_many():
    rows=DocChunker(max_chars=100,overlap=20).chunk_many([{"text":"文一。","symbol":"A","source":"a"},{"text":"文二。","symbol":"B","source":"b"}])
    assert {r["symbol"] for r in rows}=={"A","B"}

if __name__=="__main__":
    print("=== 剩余优化项测试 (standalone) ===")
    for n,f in [("g_empty",t_g_empty),("g_buy_low",t_g_buy_low),("g_sell_high",t_g_sell_high),
                ("g_low_conf",t_g_low_conf),("g_mismatch",t_g_mismatch),("g_pass",t_g_pass),
                ("g_invalid_summary",t_g_invalid_summary),("g_override_meta",t_g_override_meta),
                ("t_ctxmgr",t_t_ctxmgr),("t_parent",t_t_parent),("t_summary",t_t_summary),
                ("t_failed",t_t_failed),("t_event",t_t_event),
                ("c_basic",t_c_basic),("c_long",t_c_long),("c_para",t_c_para),
                ("c_empty",t_c_empty),("c_meta",t_c_meta),("c_many",t_c_many)]:
        check(n,f)
    print(f"\n=== 结果: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)
