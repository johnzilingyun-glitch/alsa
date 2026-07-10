"""Phase 2 SubAgent 框架 + Handoff 测试 (§4.2).

覆盖:
  - EvidenceBus 发布订阅 + stance 维度
  - Handoff 双向委托 + input_filter(3 模式) + 链深度上限
  - 结构化输出 Schema 解析 (合法/降级/markdown 包裹)
  - BaseAgent run 产出结构化 AgentResult (mock LLM)
  - SubAgent as_tool 嵌套
  - Handoff execute 实际委托
  - 单 Agent 失败降级不阻塞
"""
import json
import asyncio
import pytest

from app.schemas.contracts import (
    AgentSpec, Evidence, Snapshot, HandoffSpec,
)
from app.agents.evidence_bus import EvidenceBus
from app.agents.handoff import Handoff, make_handoff, apply_input_filter, HANDOFF_MAX_DEPTH
from app.agents.agent_result_schema import (
    AgentOutputSchema, parse_agent_output, response_format_spec,
)
from app.agents.base_agent import BaseAgent
from app.agents.expert_agents import (
    TechnicalAgent, FundamentalAgent, MacroAgent, SentimentAgent,
    NewsSubAgent, create_agent,
)


# ── mock LLM runner ─────────────────────────────────────────────────────────

def make_mock_runner(output: dict | str, *, fail: bool = False):
    """构造 mock LLM runner: 返回固定 JSON 或抛异常."""
    async def runner(prompt, *, role=None, response_schema=None, tools=None, model=None):
        if fail:
            raise RuntimeError("mock LLM failure")
        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=False)
    return runner


VALID_OUTPUT = {
    "summary": "技术面偏多, MACD 金叉, 站上 MA20",
    "score": 0.72, "confidence": 0.8, "stance": "bullish",
    "evidence": [
        {"claim": "MACD 金叉", "stance": "bullish", "confidence": 0.9, "source": ["kline"]},
        {"claim": "量能不足", "stance": "bearish", "confidence": 0.5, "source": ["kline"]},
    ],
    "risk": [{"category": "market", "description": "逼近阻力位", "severity": "medium"}],
    "status": "ok",
}


# ── EvidenceBus ─────────────────────────────────────────────────────────────

def test_evidence_bus_publish_relevant():
    bus = EvidenceBus()
    bus.publish("Technical Analyst", [
        Evidence(claim="金叉", stance="bullish", agent="Technical Analyst"),
    ])
    bus.publish("Fundamental Analyst", [
        Evidence(claim="营收下滑", stance="bearish", agent="Fundamental Analyst"),
    ])
    # Fundamental 读 Technical 的证据 (排除自己)
    evs = bus.relevant("Fundamental Analyst")
    assert len(evs) == 1
    assert evs[0].claim == "金叉"
    # all_evidence 含全部
    assert len(bus.all_evidence()) == 2


def test_evidence_bus_stance_summary():
    bus = EvidenceBus()
    bus.publish("TA", [
        Evidence(claim="a", stance="bullish"),
        Evidence(claim="b", stance="bearish"),
        Evidence(claim="c", stance="bullish"),
    ])
    ss = bus.stance_summary()
    assert ss["TA"]["bullish"] == 2
    assert ss["TA"]["bearish"] == 1


# ── Handoff input_filter ────────────────────────────────────────────────────

def test_input_filter_summary_only():
    history = [{"content": "round1 full"}, {"content": "round2 full"}]
    filtered = apply_input_filter(history, "summary_only")
    assert len(filtered) == 1
    assert "summary" in filtered[0]


def test_input_filter_recent_2():
    history = [{"c": "r1"}, {"c": "r2"}, {"c": "r3"}]
    filtered = apply_input_filter(history, "recent_2")
    assert len(filtered) == 2


def test_input_filter_full():
    history = [{"c": "r1"}, {"c": "r2"}]
    assert len(apply_input_filter(history, "full")) == 2


def test_handoff_tool_schema():
    hf = make_handoff("Fundamental Analyst")
    schema = hf.as_tool_schema()
    assert schema["function"]["name"].startswith("transfer_to_")
    assert "claim" in schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_handoff_execute_delegates():
    """Handoff.execute 调用目标 run_delegate."""
    target = FundamentalAgent(agent_id="FA", llm_runner=make_mock_runner(VALID_OUTPUT))
    hf = make_handoff("Fundamental Analyst", target_agent=target, input_filter="summary_only")
    result = await hf.execute(
        input_data={"claim": "技术突破需基本面印证", "reason": "量价配合"},
        caller_history=[{"content": "TA said breakout"}],
    )
    assert result.status == "ok"
    assert result.role == "Fundamental Analyst"


@pytest.mark.asyncio
async def test_handoff_depth_limit():
    """handoff 链深度达上限拒绝委托."""
    target = FundamentalAgent(agent_id="FA", llm_runner=make_mock_runner(VALID_OUTPUT))
    hf = make_handoff("Fundamental Analyst", target_agent=target)
    hf._depth = HANDOFF_MAX_DEPTH  # 模拟已达上限
    result = await hf.execute({"claim": "x"}, [])
    assert result["status"] == "skipped"


# ── 结构化输出 Schema ───────────────────────────────────────────────────────

def test_parse_valid_json():
    r = parse_agent_output(json.dumps(VALID_OUTPUT), "TA1", "Technical Analyst")
    assert r.status == "ok"
    assert r.stance if hasattr(r, "stance") else True  # AgentResult 无 stance, 看 evidence
    assert len(r.evidence) == 2
    assert r.evidence[0].stance == "bullish"
    assert r.confidence == 0.8


def test_parse_markdown_wrapped():
    wrapped = "```json\n" + json.dumps(VALID_OUTPUT) + "\n```"
    r = parse_agent_output(wrapped, "TA1", "Technical Analyst")
    assert r.status == "ok"
    assert len(r.evidence) == 2


def test_parse_invalid_degrades():
    r = parse_agent_output("not json at all", "TA1", "Technical Analyst")
    assert r.status == "degraded"
    assert r.confidence == 0.3  # 降级置信度


def test_parse_empty():
    r = parse_agent_output("", "TA1", "Technical Analyst")
    assert r.status == "degraded"


def test_response_format_spec():
    spec = response_format_spec()
    assert spec["type"] == "json_schema"
    assert "properties" in spec["json_schema"]["schema"]


def test_stance_validation():
    """非法 stance 归一为 neutral."""
    s = AgentOutputSchema(summary="x", score=0.5, confidence=0.5, stance="invalid")
    assert s.stance == "neutral"


# ── BaseAgent run ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_base_agent_run_structured():
    """BaseAgent.run 产出结构化 AgentResult + 发布证据."""
    bus = EvidenceBus()
    agent = TechnicalAgent(agent_id="TA1", evidence_bus=bus,
                           llm_runner=make_mock_runner(VALID_OUTPUT))
    plan = AgentSpec(agent_id="TA1", role="Technical Analyst",
                     question="分析 AAPL", budget_tokens=8000)
    snap = Snapshot(symbol="AAPL", market="美股",
                    history=[{"trade_date": f"2026-01-{i:02d}", "close": 100+i,
                              "high": 101+i, "low": 99+i, "volume": 1000, "open": 100} for i in range(1, 80)])
    result = await agent.run(plan, snap)
    assert result.status == "ok"
    assert result.role == "Technical Analyst"
    assert len(result.evidence) == 2
    # 证据已发布到 bus
    assert len(bus.by_role("Technical Analyst")) == 2


@pytest.mark.asyncio
async def test_base_agent_failure_degrades():
    """LLM 失败时降级, 不阻塞."""
    agent = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner({}, fail=True))
    plan = AgentSpec(agent_id="TA1", role="Technical Analyst", question="q", budget_tokens=4000)
    result = await agent.run(plan, Snapshot())
    # _reason_with_tools 捕获异常 → _force_finalize → degraded
    assert result.status == "degraded"


@pytest.mark.asyncio
async def test_subagent_as_tool():
    """SubAgent 作为工具被父 Agent 调用 (不转移控制权)."""
    sub = NewsSubAgent(agent_id="NS1", llm_runner=make_mock_runner(VALID_OUTPUT))
    result = await sub.run_as_tool({"query": "提取新闻证据"}, Snapshot(news=["news1", "news2"]))
    assert result.status == "ok"
    assert result.role == "News Analyst"


@pytest.mark.asyncio
async def test_technical_has_subagents_and_handoff():
    """TechnicalAgent 默认派生 News/Industry + handoff→Fundamental."""
    ta = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner(VALID_OUTPUT))
    assert "News Analyst" in ta.subagents
    assert "Industry Analyst" in ta.subagents
    assert "Fundamental Analyst" in ta.handoffs
    # handoff tool schema 生成
    tools = ta._build_tool_list()
    tool_names = [t["function"]["name"] for t in tools]
    assert any("transfer_to_fundamental" in n for n in tool_names)
    assert any("call_news" in n for n in tool_names)


@pytest.mark.asyncio
async def test_execute_decision_subagent():
    """_execute_decision 处理 subagent kind (结果回灌)."""
    sub = NewsSubAgent(agent_id="NS1", llm_runner=make_mock_runner(VALID_OUTPUT))
    parent = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner(VALID_OUTPUT))
    parent.register_subagent(sub)
    await parent._execute_decision(
        {"kind": "subagent", "subagent_id": "News Analyst",
         "input_data": {"query": "test"}},
        Snapshot(),
    )
    assert len(parent.state.injected) == 1


@pytest.mark.asyncio
async def test_execute_decision_handoff():
    """_execute_decision 处理 handoff kind (双向委托)."""
    target = FundamentalAgent(agent_id="FA", llm_runner=make_mock_runner(VALID_OUTPUT))
    parent = TechnicalAgent(agent_id="TA1", llm_runner=make_mock_runner(VALID_OUTPUT))
    # 注入 handoff 目标
    hf = make_handoff("Fundamental Analyst", target_agent=target)
    parent.register_handoff(hf)
    await parent._execute_decision(
        {"kind": "handoff", "target_role": "Fundamental Analyst",
         "input_data": {"claim": "验证突破", "reason": "test"}},
        Snapshot(),
    )
    assert len(parent.state.injected) == 1


def test_create_agent_factory():
    """create_agent 工厂按角色创建."""
    a = create_agent("Macro Analyst")
    assert isinstance(a, MacroAgent)
    assert "Risk Quantifier" in a.subagents
    a2 = create_agent("Unknown Role")
    assert isinstance(a2, BaseAgent)
