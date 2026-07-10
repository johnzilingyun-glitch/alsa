"""Phase 4 测试 — ReflectionAgent 可回溯 / role_router / DecisionAgent.

对应开发指南 §4.4 / §6 / §7.2.
"""
import asyncio
import pytest

from app.schemas.contracts import (
    AggregatedEvidence, AggregatedClaim, Conflict, CritiqueResult, Issue,
    AgentResult, Evidence, ExecutionPlan, Snapshot, AgentSpec, RiskItem,
)
from app.agents.reflection_agent import ReflectionAgent, MAX_REFLECTION_ROUNDS
from app.services.role_router import (
    resolve_tier, resolve_model, resolve_budget, is_flash_role, is_pro_role,
    estimate_cost_saving,
)
from app.agents.decision_agent import DecisionAgent, FinalDecision


# ── helpers ─────────────────────────────────────────────────────────────────

def _evidence(claim, stance, conf=0.8, agent="TA"):
    return Evidence(claim=claim, stance=stance, confidence=conf, agent=agent)

def _result(role="TA", agent_id="A", status="ok", score=0.7, conf=0.8, evidence=None):
    return AgentResult(agent_id=agent_id, role=role, status=status, score=score,
                       confidence=conf, evidence=evidence or [])

def _aggregated(claims=None, conflicts=None, coverage=None):
    return AggregatedEvidence(
        claims=claims or [], conflicts=conflicts or [],
        coverage=coverage or {"TA": 0.8},
    )


# ════════════════════════════════════════════════════════════════════════
# role_router
# ════════════════════════════════════════════════════════════════════════

def test_resolve_tier():
    assert resolve_tier("Planner") == "flash"
    assert resolve_tier("News Analyst") == "flash"
    assert resolve_tier("Technical Analyst") == "pro"
    assert resolve_tier("Reflection") == "pro"
    assert resolve_tier("Unknown") == "pro"  # 默认 pro


def test_resolve_model():
    assert "flash" in resolve_model("Planner").lower() or resolve_model("Planner") != resolve_model("Technical Analyst")
    # flash ≠ pro model
    assert resolve_model("Planner") != resolve_model("Technical Analyst")


def test_resolve_budget_rerun_bonus():
    """v3.1 §7.2: rerun 时 +2k."""
    base = resolve_budget("Technical Analyst")
    rerun = resolve_budget("Technical Analyst", is_rerun=True)
    assert rerun == base + 2000
    assert resolve_budget("Fundamental Analyst", is_rerun=True) == 12000


def test_is_flash_pro():
    assert is_flash_role("Planner")
    assert is_pro_role("Technical Analyst")
    assert not is_flash_role("Technical Analyst")


def test_cost_saving():
    """Flash 分层 → 成本节省 >50% 目标."""
    s = estimate_cost_saving(["Planner", "News Analyst", "Technical Analyst"])
    assert s["flash_count"] == 2
    assert s["pro_count"] == 1
    assert s["saving_rate"] > 0.5


# ════════════════════════════════════════════════════════════════════════
# ReflectionAgent
# ════════════════════════════════════════════════════════════════════════

def test_reflection_no_conflict_finalizes():
    """无冲突 + coverage OK → can_finalize."""
    r = ReflectionAgent()
    agg = _aggregated(
        claims=[AggregatedClaim(claim="X", supporting=[_evidence("X", "bullish")],
                                contradicting=[], consensus=1.0)],
        coverage={"TA": 0.8, "FA": 0.7},
    )
    results = [_result("TA", "A"), _result("FA", "B")]
    critique = asyncio.run(r.critique(agg, results))
    assert critique.can_finalize is True
    assert critique.rerun_agents == []


def test_reflection_conflict_triggers_rerun():
    """有冲突 → rerun 相关 agent, can_finalize=False."""
    r = ReflectionAgent()
    agg = _aggregated(
        conflicts=[Conflict(claim="金叉",
                            supporting=[_evidence("金叉", "bullish", agent="TA")],
                            contradicting=[_evidence("金叉", "bearish", agent="FA")])],
        coverage={"TA": 0.8, "FA": 0.7},
    )
    results = [_result("TA", "TA@AAPL"), _result("FA", "FA@AAPL")]
    critique = asyncio.run(r.critique(agg, results))
    assert critique.can_finalize is False
    assert len(critique.rerun_agents) > 0
    assert any("TA" in a or "FA" in a for a in critique.rerun_agents)


def test_reflection_skipped_triggers_rerun():
    """skipped agent → rerun."""
    r = ReflectionAgent()
    agg = _aggregated(coverage={"TA": 0.0})
    results = [_result("TA", "A", status="skipped")]
    critique = asyncio.run(r.critique(agg, results))
    assert critique.can_finalize is False
    assert "A" in critique.rerun_agents


def test_reflection_max_rounds_force_finalize():
    """超 max_rounds → 强制 finalize."""
    r = ReflectionAgent(max_rounds=1)
    agg = _aggregated(conflicts=[Conflict(claim="X",
                                          supporting=[_evidence("X", "bullish")],
                                          contradicting=[_evidence("X", "bearish")])])
    results = [_result("TA", "A"), _result("FA", "B")]
    # round_num >= max_rounds (1) → 强制 finalize
    critique = asyncio.run(r.critique(agg, results, round_num=1))
    assert critique.can_finalize is True
    assert any("强制" in i.description for i in critique.issues)


@pytest.mark.asyncio
async def test_reflection_rerun_recursion():
    """rerun 触发递归回溯 (round_num+1)."""
    # mock dag: rerun 返回修正后的结果 (无冲突)
    class _MockDAG:
        async def rerun(self, plan, snapshot, agent_ids):
            return [AgentResult(agent_id=aid, role="TA", status="ok", score=0.7,
                                confidence=0.8) for aid in agent_ids]
    # mock aggregator: 第二次聚合无冲突
    call_count = {"n": 0}
    class _MockAgg:
        def aggregate(self, results):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _aggregated(conflicts=[Conflict(claim="X",
                                                       supporting=[_evidence("X", "bullish")],
                                                       contradicting=[_evidence("X", "bearish")])],
                                   coverage={"TA": 0.8})
            return _aggregated(coverage={"TA": 0.8})  # 第二次无冲突
    r = ReflectionAgent(dag_engine=_MockDAG(), aggregator=_MockAgg())
    plan = ExecutionPlan(plan_id="t", symbol="AAPL", market="US-Share",
                         agent_manifest=[AgentSpec(agent_id="TA@AAPL", role="TA")])
    agg = _aggregated(conflicts=[Conflict(claim="X",
                                          supporting=[_evidence("X", "bullish")],
                                          contradicting=[_evidence("X", "bearish")])],
                      coverage={"TA": 0.8})
    results = [_result("TA", "TA@AAPL")]
    critique = await r.critique(agg, results, plan, Snapshot())
    # 回溯后第二次无冲突 → can_finalize
    assert critique.can_finalize is True
    assert critique.round_num >= 1  # 至少递归一次


def test_reflection_merge():
    """_merge 替换同 agent_id."""
    old = [_result("TA", "A", score=0.5), _result("FA", "B", score=0.6)]
    new = [_result("TA", "A", score=0.9)]  # rerun A
    merged = ReflectionAgent._merge(old, new)
    a = next(m for m in merged if m.agent_id == "A")
    assert a.score == 0.9  # 被替换
    b = next(m for m in merged if m.agent_id == "B")
    assert b.score == 0.6  # 保留


# ════════════════════════════════════════════════════════════════════════
# DecisionAgent
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_decision_buy_high_score():
    """高分 + can_finalize → buy."""
    d = DecisionAgent()
    agg = _aggregated(
        claims=[AggregatedClaim(claim="强势", supporting=[_evidence("强势", "bullish")],
                                contradicting=[], consensus=1.0)],
        coverage={"TA": 0.8},
    )
    critique = CritiqueResult(can_finalize=True)
    results = [_result("TA", "A", score=0.8, conf=0.9)]
    fd = await d.decide(agg, critique, results, symbol="AAPL")
    assert fd.action == "buy"
    assert fd.can_act is True
    assert fd.stance == "bullish"


@pytest.mark.asyncio
async def test_decision_sell_low_score():
    """低分 → sell."""
    d = DecisionAgent()
    agg = _aggregated(coverage={"TA": 0.8})
    critique = CritiqueResult(can_finalize=True)
    results = [_result("TA", "A", score=0.3, conf=0.8)]
    fd = await d.decide(agg, critique, results)
    assert fd.action == "sell"


@pytest.mark.asyncio
async def test_decision_not_finalizable_watch():
    """critique 不可 finalize → action=watch, confidence 降级."""
    d = DecisionAgent()
    agg = _aggregated(coverage={"TA": 0.8})
    critique = CritiqueResult(can_finalize=False, issues=[Issue(severity="high", description="冲突")])
    results = [_result("TA", "A", score=0.8, conf=0.9)]
    fd = await d.decide(agg, critique, results)
    assert fd.action == "watch"
    assert fd.can_act is False
    assert fd.confidence < 0.9  # 降级 (×0.6)


@pytest.mark.asyncio
async def test_decision_risks_aggregated():
    """风险汇总 + 去重."""
    d = DecisionAgent()
    agg = _aggregated(coverage={"TA": 0.8, "FA": 0.7})
    critique = CritiqueResult(can_finalize=True)
    results = [
        _result("TA", "A", evidence=None) if False else AgentResult(
            agent_id="A", role="TA", status="ok", score=0.7, confidence=0.8,
            risk=[RiskItem(category="market", description="阻力位", severity="medium")]),
        AgentResult(agent_id="B", role="FA", status="ok", score=0.7, confidence=0.8,
                    risk=[RiskItem(category="market", description="阻力位", severity="medium"),  # 重复
                          RiskItem(category="liquidity", description="流动性差", severity="high")]),
    ]
    fd = await d.decide(agg, critique, results)
    assert len(fd.risks) == 2  # 去重后 2 条


@pytest.mark.asyncio
async def test_decision_key_claims():
    """高 consensus claim 进入 key_claims."""
    d = DecisionAgent()
    agg = _aggregated(
        claims=[
            AggregatedClaim(claim="强势信号", supporting=[_evidence("强势信号", "bullish")],
                            contradicting=[], consensus=0.9),
            AggregatedClaim(claim="弱信号", supporting=[_evidence("弱信号", "neutral")],
                            contradicting=[], consensus=0.5),
        ],
        coverage={"TA": 0.8},
    )
    critique = CritiqueResult(can_finalize=True)
    results = [_result("TA", "A")]
    fd = await d.decide(agg, critique, results)
    assert any("强势信号" in c for c in fd.key_claims)
    assert not any("弱信号" in c for c in fd.key_claims)
