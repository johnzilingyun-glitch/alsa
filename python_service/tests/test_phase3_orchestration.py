"""Phase 3 测试 — DAGEngine 动态并行 / Planner 动态规划 / EvidenceAggregator.

对应开发指南 §4.1 / §4.2.5 / §4.3.
"""
import asyncio
import pytest

from app.schemas.contracts import (
    ExecutionPlan, AgentSpec, AgentResult, Evidence, Snapshot, DAGSpec,
    SubAgentSpec, AggregatedEvidence,
)
from app.engine.dag_engine import DAGEngine
from app.services.planner_service import PlannerService, detect_market
from app.services.evidence_store import EvidenceAggregator


# ── mock agent factory (避免真实 LLM) ───────────────────────────────────────

def make_mock_factory(output_stance="bullish", fail_roles=()):
    """构造 mock agent_factory: 返回固定 AgentResult."""
    class _MockAgent:
        def __init__(self, role, agent_id=""):
            self.role = role
            self.agent_id = agent_id or role
        async def run(self, plan, snapshot):
            if self.role in fail_roles:
                return AgentResult(agent_id=self.agent_id, role=self.role,
                                   status="degraded", summary="(mock fail)", confidence=0.3)
            return AgentResult(
                agent_id=self.agent_id, role=self.role, status="ok",
                summary=f"mock {self.role}", score=0.7, confidence=0.8,
                evidence=[Evidence(claim=f"{self.role} view", stance=output_stance,
                                   confidence=0.8, agent=self.role)],
            )
    def factory(role, agent_id=""):
        return _MockAgent(role, agent_id)
    return factory


# ════════════════════════════════════════════════════════════════════════
# DAGEngine
# ════════════════════════════════════════════════════════════════════════

def _plan(agents, dag=None):
    return ExecutionPlan(
        plan_id="t1", symbol="AAPL", market="US-Share",
        agent_manifest=agents, dag=dag or DAGSpec(),
    )


def test_dag_parallel_branches_no_deps():
    """无依赖的 Agent 全部归同一层 (并行)."""
    eng = DAGEngine(agent_factory=make_mock_factory())
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst"),
        AgentSpec(agent_id="B", role="Fundamental Analyst"),
        AgentSpec(agent_id="C", role="Sentiment Analyst"),
    ])
    layers = eng.build_parallel_branches(plan)
    assert len(layers) == 1  # 全并行一层
    assert len(layers[0]) == 3


def test_dag_parallel_branches_with_deps():
    """有 depends_on 的 Agent 归下一层 (串行)."""
    eng = DAGEngine(agent_factory=make_mock_factory())
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst", depends_on=[]),
        AgentSpec(agent_id="B", role="Fundamental Analyst", depends_on=["A"]),
        AgentSpec(agent_id="C", role="Macro Analyst", depends_on=["A"]),
    ])
    layers = eng.build_parallel_branches(plan)
    assert len(layers) == 2  # A 一层, B+C 一层
    assert layers[0][0].agent_id == "A"
    layer2_ids = {a.agent_id for a in layers[1]}
    assert layer2_ids == {"B", "C"}


def test_dag_circular_deps_break():
    """循环依赖兜底破解."""
    eng = DAGEngine(agent_factory=make_mock_factory())
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst", depends_on=["B"]),
        AgentSpec(agent_id="B", role="Fundamental Analyst", depends_on=["A"]),
    ])
    layers = eng.build_parallel_branches(plan)  # 不应死循环
    total = sum(len(l) for l in layers)
    assert total == 2


@pytest.mark.asyncio
async def test_dag_run_parallel():
    """run 执行全部 Agent, 收 AgentResult."""
    eng = DAGEngine(agent_factory=make_mock_factory())
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst"),
        AgentSpec(agent_id="B", role="Fundamental Analyst"),
    ])
    results = await eng.run(plan, Snapshot())
    assert len(results) == 2
    assert all(r.status == "ok" for r in results)


@pytest.mark.asyncio
async def test_dag_run_serial_with_deps():
    """有依赖的串行执行."""
    eng = DAGEngine(agent_factory=make_mock_factory())
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst", depends_on=[]),
        AgentSpec(agent_id="B", role="Fundamental Analyst", depends_on=["A"]),
    ])
    results = await eng.run(plan, Snapshot())
    assert len(results) == 2


@pytest.mark.asyncio
async def test_dag_short_circuit():
    """短路: 数据不足标记 → 下游 skipped."""
    def factory(role, agent_id=""):
        class _A:
            def __init__(s): s.role = role; s.agent_id = agent_id or role
            async def run(s, plan, snap):
                if role == "Technical Analyst":
                    return AgentResult(agent_id=s.agent_id, role=role, status="ok",
                                       summary="数据严重不足，无法获取")
                return AgentResult(agent_id=s.agent_id, role=role, status="ok", summary="ok")
        return _A()
    eng = DAGEngine(agent_factory=factory)
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst", depends_on=[]),
        AgentSpec(agent_id="B", role="Fundamental Analyst", depends_on=["A"]),
    ])
    results = await eng.run(plan, Snapshot())
    # B 应被短路 skipped
    b = next(r for r in results if r.role == "Fundamental Analyst")
    assert b.status == "skipped"


@pytest.mark.asyncio
async def test_dag_rerun():
    """rerun 只重跑指定 Agent."""
    eng = DAGEngine(agent_factory=make_mock_factory())
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst"),
        AgentSpec(agent_id="B", role="Fundamental Analyst"),
    ])
    results = await eng.rerun(plan, Snapshot(), ["A"])
    assert len(results) == 1
    assert results[0].agent_id == "A"


@pytest.mark.asyncio
async def test_dag_agent_failure_degrades():
    """单 Agent 失败降级, 不阻塞其他."""
    eng = DAGEngine(agent_factory=make_mock_factory(fail_roles=("Fundamental Analyst",)))
    plan = _plan([
        AgentSpec(agent_id="A", role="Technical Analyst"),
        AgentSpec(agent_id="B", role="Fundamental Analyst"),
    ])
    results = await eng.run(plan, Snapshot())
    b = next(r for r in results if r.role == "Fundamental Analyst")
    assert b.status == "degraded"
    a = next(r for r in results if r.role == "Technical Analyst")
    assert a.status == "ok"  # 不阻塞


# ════════════════════════════════════════════════════════════════════════
# PlannerService
# ════════════════════════════════════════════════════════════════════════

def test_detect_market():
    assert detect_market("600519.SH") == "A-Share"
    assert detect_market("0700.HK") == "HK-Share"
    assert detect_market("AAPL") == "US-Share"
    assert detect_market("00700") == "HK-Share"


@pytest.mark.asyncio
async def test_planner_a_share():
    """A股 → Technical[News,Industry] + Fundamental + Sentiment (3 Agent)."""
    p = PlannerService()
    plan = await p.plan("600519.SH", "分析", market="A-Share")
    roles = [a.role for a in plan.agent_manifest]
    assert "Technical Analyst" in roles
    assert "Fundamental Analyst" in roles
    assert "Sentiment Analyst" in roles
    # Technical 派生 News + Industry
    ta = next(a for a in plan.agent_manifest if a.role == "Technical Analyst")
    sub_roles = [s.role for s in ta.subagents]
    assert "News Analyst" in sub_roles
    assert "Industry Analyst" in sub_roles


@pytest.mark.asyncio
async def test_planner_hk_share():
    """港股 → Fundamental + Macro[Risk] + Sentiment."""
    p = PlannerService()
    plan = await p.plan("0700.HK", "分析", market="HK-Share")
    roles = [a.role for a in plan.agent_manifest]
    assert "Fundamental Analyst" in roles
    assert "Macro Analyst" in roles
    ma = next(a for a in plan.agent_manifest if a.role == "Macro Analyst")
    assert "Risk Quantifier" in [s.role for s in ma.subagents]


@pytest.mark.asyncio
async def test_planner_us_share():
    """美股 → Technical + Fundamental + Macro[Valuation]."""
    p = PlannerService()
    plan = await p.plan("AAPL", "分析")
    roles = [a.role for a in plan.agent_manifest]
    assert "Technical Analyst" in roles
    assert "Macro Analyst" in roles
    ma = next(a for a in plan.agent_manifest if a.role == "Macro Analyst")
    assert "Valuation Analyst" in [s.role for s in ma.subagents]


@pytest.mark.asyncio
async def test_planner_insufficient_data():
    """数据不足 → 仅 Technical (1 Agent)."""
    p = PlannerService()
    plan = await p.plan("XXXX", "分析", market="US-Share", data_availability="insufficient")
    assert len(plan.agent_manifest) == 1
    assert plan.agent_manifest[0].role == "Technical Analyst"


@pytest.mark.asyncio
async def test_planner_toolregistry_mapping():
    """data_fetch_manifest 经 ToolRegistry 映射到候选工具."""
    p = PlannerService()
    plan = await p.plan("AAPL", "分析")
    quote_task = next(t for t in plan.data_fetch_manifest if t.data_type == "realtime_quote")
    assert len(quote_task.tools) > 0
    assert quote_task.tools[0].tool_id == "fetch_realtime_quote"
    assert quote_task.tools[0].priority == 1


@pytest.mark.asyncio
async def test_planner_validate_patch():
    """validate_and_patch: 至少 1 Agent + quote/history."""
    p = PlannerService()
    plan = await p.plan("AAPL", "分析")
    assert len(plan.agent_manifest) >= 1
    data_types = [t.data_type for t in plan.data_fetch_manifest]
    assert "realtime_quote" in data_types
    assert "history_kline" in data_types


@pytest.mark.asyncio
async def test_planner_dynamic_agent_count():
    """v3.1 验收: Planner 按股票特征动态选 Agent 数."""
    p = PlannerService()
    a_plan = await p.plan("600519.SH", "分析", market="A-Share")
    us_plan = await p.plan("AAPL", "分析")
    ins_plan = await p.plan("X", "分析", market="US-Share", data_availability="insufficient")
    # 不同特征 → 不同 Agent 数 (运行时决定)
    a_n = len(a_plan.agent_manifest)
    us_n = len(us_plan.agent_manifest)
    ins_n = len(ins_plan.agent_manifest)
    assert ins_n < a_n  # 数据不足更少 Agent
    assert ins_n == 1


# ════════════════════════════════════════════════════════════════════════
# EvidenceAggregator
# ════════════════════════════════════════════════════════════════════════

def test_aggregator_stance_split():
    """v3.1: 按 stance 分 supporting/contradicting (不是 confidence)."""
    agg = EvidenceAggregator()
    results = [
        AgentResult(agent_id="A", role="TA", evidence=[
            Evidence(claim="金叉", stance="bullish", confidence=0.9, agent="TA"),
            Evidence(claim="金叉", stance="bearish", confidence=0.4, agent="FA"),  # 反对
        ]),
    ]
    ae = agg.aggregate(results)
    assert len(ae.claims) == 1
    ac = ae.claims[0]
    assert len(ac.supporting) == 1  # bullish
    assert len(ac.contradicting) == 1  # bearish
    # 低 confidence(0.4) 的 bearish 仍是 contradicting (v3.1 修复)
    assert ac.contradicting[0].confidence == 0.4


def test_aggregator_conflict_marked():
    """存在 contradicting+supporting → 标记冲突."""
    agg = EvidenceAggregator()
    results = [
        AgentResult(agent_id="A", role="TA", evidence=[
            Evidence(claim="X", stance="bullish", agent="TA"),
            Evidence(claim="X", stance="bearish", agent="FA"),
        ]),
    ]
    ae = agg.aggregate(results)
    assert len(ae.conflicts) == 1
    assert ae.conflicts[0].claim == "X"


def test_aggregator_no_conflict_all_bullish():
    """全 bullish 无冲突."""
    agg = EvidenceAggregator()
    results = [
        AgentResult(agent_id="A", role="TA", evidence=[
            Evidence(claim="X", stance="bullish", agent="TA"),
            Evidence(claim="X", stance="bullish", agent="FA"),
        ]),
    ]
    ae = agg.aggregate(results)
    assert len(ae.conflicts) == 0
    assert ae.claims[0].consensus == 1.0


def test_aggregator_consensus():
    """consensus = supporting权重 / 总权重."""
    agg = EvidenceAggregator()
    results = [
        AgentResult(agent_id="A", role="TA", evidence=[
            Evidence(claim="X", stance="bullish", confidence=0.8, agent="TA"),
            Evidence(claim="X", stance="bearish", confidence=0.2, agent="FA"),
        ]),
    ]
    ae = agg.aggregate(results)
    # 0.8 / (0.8+0.2) = 0.8
    assert ae.claims[0].consensus == 0.8


def test_aggregator_coverage():
    """coverage: skipped=0, degraded=0.3, ok+evidence 高."""
    agg = EvidenceAggregator()
    results = [
        AgentResult(agent_id="A", role="TA", status="ok",
                    evidence=[Evidence(claim="x", stance="bullish", confidence=0.8, agent="TA")]),
        AgentResult(agent_id="B", role="FA", status="skipped"),
        AgentResult(agent_id="C", role="MA", status="degraded"),
    ]
    ae = agg.aggregate(results)
    assert ae.coverage["TA"] > ae.coverage["FA"]
    assert ae.coverage["FA"] == 0.0
    assert ae.coverage["MA"] == 0.3


def test_aggregator_empty():
    agg = EvidenceAggregator()
    ae = agg.aggregate([])
    assert ae.claims == []
    assert ae.conflicts == []


def test_aggregator_stance_distribution():
    agg = EvidenceAggregator()
    results = [
        AgentResult(agent_id="A", role="TA", evidence=[
            Evidence(claim="X", stance="bullish", agent="TA"),
            Evidence(claim="Y", stance="bearish", agent="FA"),
            Evidence(claim="Z", stance="neutral", agent="MA"),
        ]),
    ]
    ae = agg.aggregate(results)
    dist = EvidenceAggregator.stance_distribution(ae)
    assert dist["bullish"] == 1
    assert dist["bearish"] == 1
    assert dist["neutral"] == 1
