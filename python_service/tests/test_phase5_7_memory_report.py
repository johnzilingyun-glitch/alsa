"""Phase 5+7 测试 — CheckpointStore / MemoryStore / ReportBuilder."""
import os, json, tempfile, asyncio, pytest

from app.schemas.contracts import (
    ExecutionPlan, AgentSpec, AgentResult, Evidence, RiskItem,
    AggregatedEvidence, AggregatedClaim, Conflict, CritiqueResult, Issue,
    Snapshot,
)
from app.agents.decision_agent import FinalDecision
from app.services.checkpoint_store import CheckpointStore
from app.services.memory_store import MemoryStore, MemoryLayer
from app.agents.report_builder import ReportBuilder


# ── fixtures ────────────────────────────────────────────────────────────────

def _plan():
    return ExecutionPlan(plan_id="p1", symbol="AAPL", market="US-Share",
                         agent_manifest=[AgentSpec(agent_id="TA@AAPL", role="Technical Analyst")])

def _decision():
    return FinalDecision(
        symbol="AAPL", final_score=0.75, stance="bullish", action="buy",
        confidence=0.8, summary="技术面偏多, MACD 金叉",
        risks=[RiskItem(category="market", description="阻力位", severity="medium")],
        key_claims=["[0.9] MACD 金叉"], can_act=True,
        rationale="基于 3 个 Agent 加权评分",
    )

def _aggregated():
    return AggregatedEvidence(
        claims=[
            AggregatedClaim(claim="MACD 金叉",
                            supporting=[Evidence(claim="金叉确认", stance="bullish", confidence=0.9, source=["kline"], agent="TA")],
                            contradicting=[Evidence(claim="量能不足", stance="bearish", confidence=0.4, source=["kline"], agent="FA")],
                            consensus=0.8),
        ],
        conflicts=[Conflict(claim="MACD 金叉",
                            supporting=[Evidence(claim="金叉确认", stance="bullish", agent="TA")],
                            contradicting=[Evidence(claim="量能不足", stance="bearish", agent="FA")])],
        coverage={"TA": 0.8, "FA": 0.7},
    )

def _critique():
    return CritiqueResult(issues=[Issue(severity="medium", description="量价背离需关注")], can_finalize=True)


# ════════════════════════════════════════════════════════════════════════
# CheckpointStore
# ════════════════════════════════════════════════════════════════════════

def test_checkpoint_save_resume_memory():
    store = CheckpointStore()
    plan = _plan()
    store.save("job1:plan", plan)
    resumed = store.resume("job1:plan")
    assert resumed is plan  # 内存级返回同一对象


def test_checkpoint_resume_missing():
    store = CheckpointStore()
    assert store.resume("nonexistent") is None


def test_checkpoint_list_filter():
    store = CheckpointStore()
    store.save("job1:a", 1)
    store.save("job1:b", 2)
    store.save("job2:a", 3)
    keys = store.list_checkpoints("job1")
    assert len(keys) == 2
    assert all(k.startswith("job1") for k in keys)


def test_checkpoint_delete():
    store = CheckpointStore()
    store.save("job1:a", 1)
    assert store.delete("job1:a") is True
    assert store.resume("job1:a") is None
    assert store.delete("job1:a") is False


def test_checkpoint_clear_job():
    store = CheckpointStore()
    store.save("job1:a", 1)
    store.save("job1:b", 2)
    store.save("job2:a", 3)
    n = store.clear("job1")
    assert n == 2
    assert store.list_checkpoints("job1") == []
    assert store.list_checkpoints("job2") == ["job2:a"]


def test_checkpoint_persist_roundtrip(tmp_path):
    """持久化: 跨实例恢复."""
    store1 = CheckpointStore(persist_dir=str(tmp_path))
    decision = _decision()
    store1.save("job1:decision", decision)
    # 新实例从持久化加载
    store2 = CheckpointStore(persist_dir=str(tmp_path))
    resumed = store2.resume("job1:decision")
    assert resumed is not None
    # 持久化恢复为 dict 或重建对象, 关键字段一致
    r = resumed if isinstance(resumed, dict) else resumed.__dict__ if hasattr(resumed, '__dict__') else resumed
    # _reconstruct 可能退化为 dict, 检查关键字段
    score = r.get("final_score") if isinstance(r, dict) else getattr(resumed, "final_score", None)
    assert score == 0.75


def test_checkpoint_various_types():
    """支持多种 dataclass 类型."""
    store = CheckpointStore()
    store.save("p", _plan())
    store.save("r", AgentResult(agent_id="A", role="TA", status="ok"))
    store.save("d", _decision())
    assert store.resume("p") is not None
    assert store.resume("r") is not None
    assert store.resume("d") is not None


# ════════════════════════════════════════════════════════════════════════
# MemoryStore
# ════════════════════════════════════════════════════════════════════════

def test_memory_layer_isolation():
    """四层隔离: Session/Project/User 互不干扰."""
    mem = MemoryStore()
    mem.put(MemoryLayer.SESSION, "k1", "session_val")
    mem.put(MemoryLayer.PROJECT, "k1", "project_val")
    mem.put(MemoryLayer.USER, "k1", "user_val")
    assert mem.get(MemoryLayer.SESSION, "k1") == "session_val"
    assert mem.get(MemoryLayer.PROJECT, "k1") == "project_val"
    assert mem.get(MemoryLayer.USER, "k1") == "user_val"


def test_memory_query_prefix():
    mem = MemoryStore()
    mem.put(MemoryLayer.SESSION, "job1:a", 1)
    mem.put(MemoryLayer.SESSION, "job1:b", 2)
    mem.put(MemoryLayer.SESSION, "job2:a", 3)
    result = mem.query(MemoryLayer.SESSION, "job1:")
    assert len(result) == 2
    assert all(k.startswith("job1:") for k in result)


def test_memory_project_persist(tmp_path):
    """Project 层持久化."""
    mem1 = MemoryStore(project_dir=str(tmp_path))
    mem1.put(MemoryLayer.PROJECT, "default_market", "US-Share")
    # 新实例从持久化加载
    mem2 = MemoryStore(project_dir=str(tmp_path))
    assert mem2.get(MemoryLayer.PROJECT, "default_market") == "US-Share"


def test_memory_session_snapshot_restore():
    """Session 快照/恢复."""
    mem = MemoryStore()
    plan = _plan()
    key = mem.snapshot_session("job1", plan=plan)
    assert key == "job1:session"
    snap = mem.restore_session("job1")
    assert snap is not None
    assert snap["job_id"] == "job1"


def test_memory_session_snapshot_with_checkpoint():
    """Session 快照落 CheckpointStore."""
    mem = MemoryStore()
    store = CheckpointStore()
    mem.snapshot_session("job1", plan=_plan(), checkpoint_store=store)
    # checkpoint 有
    assert "job1:session" in store.list_checkpoints("job1")
    # 清 session 后从 checkpoint 恢复
    mem.clear_session("job1")
    assert mem.restore_session("job1") is None
    snap = mem.restore_session("job1", checkpoint_store=store)
    assert snap is not None


def test_memory_clear_session():
    mem = MemoryStore()
    mem.put(MemoryLayer.SESSION, "job1:a", 1)
    mem.put(MemoryLayer.SESSION, "job1:b", 2)
    mem.put(MemoryLayer.SESSION, "job2:a", 3)
    n = mem.clear_session("job1")
    assert n == 2
    assert mem.query(MemoryLayer.SESSION, "job1") == {}


def test_memory_analysis_fallback():
    """Analysis 层: remember 标记是否走 AgentMemory, recall 同步查 Session 兜底."""
    mem = MemoryStore()
    # remember_analysis: AgentMemory 可用→True, 不可用→False (均兜底写 Session)
    mem.remember_analysis(symbol="AAPL", role="TA", summary="偏多", conclusions=["金叉"])
    # recall_analysis 同步查 Session 兜底
    results = mem.recall_analysis(symbol="AAPL", role="TA")
    assert len(results) == 1
    assert "偏多" in results[0]["summary"]


# ════════════════════════════════════════════════════════════════════════
# ReportBuilder
# ════════════════════════════════════════════════════════════════════════

def test_report_markdown_structure():
    rb = ReportBuilder()
    md = rb.build_markdown(_decision(), _aggregated(), [], _critique())
    assert "投资分析报告" in md
    assert "AAPL" in md
    assert "综合评分" in md
    assert "0.75" in md
    assert "看多" in md  # stance_cn
    assert "买入" in md  # action_cn


def test_report_markdown_evidence_traceable():
    """证据可追溯: claim + source + agent + stance."""
    rb = ReportBuilder()
    md = rb.build_markdown(_decision(), _aggregated(), [])
    assert "MACD 金叉" in md
    assert "TA" in md  # agent
    assert "kline" in md  # source
    assert "bullish" in md or "看多" in md  # stance
    assert "source:" in md


def test_report_markdown_conflicts():
    """冲突标记."""
    rb = ReportBuilder()
    md = rb.build_markdown(_decision(), _aggregated(), [])
    assert "证据冲突" in md
    assert "支持 vs" in md


def test_report_markdown_risks():
    rb = ReportBuilder()
    md = rb.build_markdown(_decision(), _aggregated(), [])
    assert "风险清单" in md
    assert "阻力位" in md
    assert "medium" in md or "中" in md


def test_report_markdown_issues():
    rb = ReportBuilder()
    md = rb.build_markdown(_decision(), _aggregated(), [], _critique())
    assert "反思问题" in md
    assert "量价背离" in md


def test_report_dict_structure():
    rb = ReportBuilder()
    r = rb.build(_decision(), _aggregated(), [], _critique())
    assert r["symbol"] == "AAPL"
    assert r["score"] == 0.75
    assert r["stance"] == "bullish"
    assert r["action"] == "buy"
    assert len(r["evidence"]) == 1
    assert r["evidence"][0]["claim"] == "MACD 金叉"
    assert len(r["evidence"][0]["supporting"]) == 1
    assert r["evidence"][0]["supporting"][0]["source"] == ["kline"]
    assert len(r["risks"]) == 1
    assert len(r["issues"]) == 1


def test_report_empty_evidence():
    """空证据不崩溃."""
    rb = ReportBuilder()
    empty_agg = AggregatedEvidence()
    md = rb.build_markdown(_decision(), empty_agg, [])
    assert "无结构化证据" in md
