"""Phase 2 独立测试运行器 (绕过 conftest 重型导入).

agents 包不依赖 tools(ths 链), 但 context_builder 依赖 polars(已装).
直接 import 即可, 无需 importlib bypass.
"""
import sys, json, asyncio, traceback

sys.path.insert(0, "python_service")

from app.schemas.contracts import AgentSpec, Evidence, Snapshot
from app.agents.evidence_bus import EvidenceBus
from app.agents.handoff import Handoff, make_handoff, apply_input_filter, HANDOFF_MAX_DEPTH
from app.agents.agent_result_schema import AgentOutputSchema, parse_agent_output, response_format_spec
from app.agents.base_agent import BaseAgent
from app.agents.expert_agents import (
    TechnicalAgent, FundamentalAgent, MacroAgent, SentimentAgent,
    NewsSubAgent, create_agent,
)

passed = failed = 0

def check(name, fn):
    global passed, failed
    try:
        fn(); print(f"  PASS  {name}"); passed += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}"); traceback.print_exc(); failed += 1

def check_async(name, fn):
    global passed, failed
    try:
        asyncio.run(fn()); print(f"  PASS  {name}"); passed += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}"); traceback.print_exc(); failed += 1

def make_mock_runner(output, fail=False):
    async def runner(prompt, *, role=None, response_schema=None, tools=None, model=None):
        if fail: raise RuntimeError("mock LLM failure")
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    return runner

VALID = {
    "summary": "技术面偏多", "score": 0.72, "confidence": 0.8, "stance": "bullish",
    "evidence": [
        {"claim": "金叉", "stance": "bullish", "confidence": 0.9, "source": ["k"]},
        {"claim": "量不足", "stance": "bearish", "confidence": 0.5, "source": ["k"]},
    ],
    "risk": [{"category": "market", "description": "阻力位", "severity": "medium"}],
    "status": "ok",
}

def t_bus_publish():
    bus = EvidenceBus()
    bus.publish("TA", [Evidence(claim="金叉", stance="bullish", agent="TA")])
    bus.publish("FA", [Evidence(claim="营收降", stance="bearish", agent="FA")])
    evs = bus.relevant("FA")
    assert len(evs) == 1 and evs[0].claim == "金叉"
    assert len(bus.all_evidence()) == 2

def t_bus_stance():
    bus = EvidenceBus()
    bus.publish("TA", [Evidence(claim="a", stance="bullish"), Evidence(claim="b", stance="bearish"),
                       Evidence(claim="c", stance="bullish")])
    ss = bus.stance_summary()
    assert ss["TA"]["bullish"] == 2 and ss["TA"]["bearish"] == 1

def t_filter_summary():
    f = apply_input_filter([{"content": "r1"}, {"content": "r2"}], "summary_only")
    assert len(f) == 1 and "summary" in f[0]

def t_filter_recent2():
    assert len(apply_input_filter([{"c": "1"}, {"c": "2"}, {"c": "3"}], "recent_2")) == 2

def t_filter_full():
    assert len(apply_input_filter([{"c": "1"}, {"c": "2"}], "full")) == 2

def t_handoff_schema():
    hf = make_handoff("Fundamental Analyst")
    s = hf.as_tool_schema()
    assert s["function"]["name"].startswith("transfer_to_")
    assert "claim" in s["function"]["parameters"]["properties"]

def t_parse_valid():
    r = parse_agent_output(json.dumps(VALID), "TA1", "Technical Analyst")
    assert r.status == "ok" and len(r.evidence) == 2 and r.evidence[0].stance == "bullish"

def t_parse_markdown():
    r = parse_agent_output("```json\n" + json.dumps(VALID) + "\n```", "TA1", "Technical Analyst")
    assert r.status == "ok" and len(r.evidence) == 2

def t_parse_invalid():
    r = parse_agent_output("not json", "TA1", "Technical Analyst")
    assert r.status == "degraded" and r.confidence == 0.3

def t_parse_empty():
    assert parse_agent_output("", "TA1", "TA").status == "degraded"

def t_response_format():
    assert response_format_spec()["type"] == "json_schema"

def t_stance_validate():
    assert AgentOutputSchema(summary="x", score=0.5, confidence=0.5, stance="bad").stance == "neutral"

def t_factory():
    assert isinstance(create_agent("Macro Analyst"), MacroAgent)
    assert "Risk Quantifier" in create_agent("Macro Analyst").subagents
    assert isinstance(create_agent("X"), BaseAgent)

async def t_handoff_execute():
    target = FundamentalAgent(agent_id="FA", llm_runner=make_mock_runner(VALID))
    hf = make_handoff("Fundamental Analyst", target_agent=target, input_filter="summary_only")
    r = await hf.execute({"claim": "验证", "reason": "t"}, [{"content": "TA said x"}])
    assert r.status == "ok" and r.role == "Fundamental Analyst"

async def t_handoff_depth():
    target = FundamentalAgent(agent_id="FA", llm_runner=make_mock_runner(VALID))
    hf = make_handoff("Fundamental Analyst", target_agent=target)
    hf._depth = HANDOFF_MAX_DEPTH
    r = await hf.execute({"claim": "x"}, [])
    assert r["status"] == "skipped"

async def t_agent_run():
    bus = EvidenceBus()
    a = TechnicalAgent(agent_id="TA1", evidence_bus=bus, llm_runner=make_mock_runner(VALID))
    plan = AgentSpec(agent_id="TA1", role="Technical Analyst", question="分析", budget_tokens=8000)
    snap = Snapshot(symbol="AAPL", market="美股",
                    history=[{"trade_date": f"2026-01-{i:02d}", "close": 100+i, "high": 101+i,
                              "low": 99+i, "volume": 1000, "open": 100} for i in range(1, 80)])
    r = await a.run(plan, snap)
    assert r.status == "ok" and r.role == "Technical Analyst" and len(r.evidence) == 2
    assert len(bus.by_role("Technical Analyst")) == 2

async def t_agent_failure():
    a = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner({}, fail=True))
    r = await a.run(AgentSpec(agent_id="TA1", role="Technical Analyst", question="q", budget_tokens=4000), Snapshot())
    assert r.status == "degraded"

async def t_subagent_astool():
    s = NewsSubAgent(agent_id="NS1", llm_runner=make_mock_runner(VALID))
    r = await s.run_as_tool({"query": "新闻"}, Snapshot(news=["n1", "n2"]))
    assert r.status == "ok" and r.role == "News Analyst"

async def t_technical_config():
    ta = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner(VALID))
    assert "News Analyst" in ta.subagents and "Industry Analyst" in ta.subagents
    assert "Fundamental Analyst" in ta.handoffs
    names = [t["function"]["name"] for t in ta._build_tool_list()]
    assert any("transfer_to_fundamental" in n for n in names)
    assert any("call_news" in n for n in names)

async def t_decision_subagent():
    sub = NewsSubAgent(agent_id="NS1", llm_runner=make_mock_runner(VALID))
    parent = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner(VALID))
    parent.register_subagent(sub)
    await parent._execute_decision({"kind": "subagent", "subagent_id": "News Analyst",
                                    "input_data": {"query": "t"}}, Snapshot())
    assert len(parent.state.injected) == 1

async def t_decision_handoff():
    target = FundamentalAgent(agent_id="FA", llm_runner=make_mock_runner(VALID))
    parent = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner(VALID))
    parent.register_handoff(make_handoff("Fundamental Analyst", target_agent=target))
    await parent._execute_decision({"kind": "handoff", "target_role": "Fundamental Analyst",
                                    "input_data": {"claim": "v", "reason": "t"}}, Snapshot())
    assert len(parent.state.injected) == 1

if __name__ == "__main__":
    print("=== Phase 2 测试 (standalone) ===")
    for n, f in [
        ("bus_publish", t_bus_publish), ("bus_stance", t_bus_stance),
        ("filter_summary", t_filter_summary), ("filter_recent2", t_filter_recent2),
        ("filter_full", t_filter_full), ("handoff_schema", t_handoff_schema),
        ("parse_valid", t_parse_valid), ("parse_markdown", t_parse_markdown),
        ("parse_invalid", t_parse_invalid), ("parse_empty", t_parse_empty),
        ("response_format", t_response_format), ("stance_validate", t_stance_validate),
        ("factory", t_factory),
    ]:
        check(n, f)
    for n, f in [
        ("handoff_execute", t_handoff_execute), ("handoff_depth", t_handoff_depth),
        ("agent_run", t_agent_run), ("agent_failure", t_agent_failure),
        ("subagent_astool", t_subagent_astool), ("technical_config", t_technical_config),
        ("decision_subagent", t_decision_subagent), ("decision_handoff", t_decision_handoff),
    ]:
        check_async(n, f)
    print(f"\n=== 结果: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)
