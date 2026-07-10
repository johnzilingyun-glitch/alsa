"""ALSA 多智能体架构层间数据契约 (v3.1).

对应开发指南 §3.2「数据契约（层间只传结构化数据）」。

设计原则:
  - 纯 stdlib dataclasses, 零外部依赖, 任何层/任何阶段都能 import.
  - 每个数据类标注产出层与消费层, 边界清晰.
  - 字段命名与开发指南保持一致, 便于与文档对照.

层间流转:
  ② Planning  → ExecutionPlan / AgentSpec / SubAgentSpec / HandoffSpec
  ③ Execution → AgentResult / Evidence
  ④ Evidence  → AggregatedEvidence / AggregatedClaim / Conflict
  ⑤ Reflection→ CritiqueResult
  横切        → ToolCall / ToolResult / ToolSpec / Snapshot
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional


# ──────────────────────────────────────────────────────────────────────────
# ② Planning Layer → Execution Layer
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class DataFetchTask:
    """Planner 决定的单条数据获取需求 (尚未映射到具体工具)."""
    data_type: str            # realtime_quote / history_kline / financial_stmt / news / ...
    symbol: str = ""
    params: dict = field(default_factory=dict)
    # 经 ToolRegistry.resolve 填充: 候选工具 (按优先级)
    tools: list["ToolSpec"] = field(default_factory=list)


@dataclass
class SubAgentSpec:
    """可派生的子 Agent (OpenAI Agent.as_tool() 范式)."""
    subagent_id: str
    role: str                 # news / industry / risk / valuation
    as_tool: bool = True      # True=作为工具被父 Agent 调用 (不转移控制)
    input_schema: Any = None  # 调用参数 schema (typing 类型或 dict)


@dataclass
class HandoffSpec:
    """双向委托规格 (OpenAI handoff 范式).

    input_filter 是治 context 的关键:
      - "summary_only": 只传上一轮摘要 (默认, 最小 context)
      - "recent_2":     传最近 2 轮全文
      - "full":         传完整历史 (仅关键决策用)
    """
    target_role: str
    tool_name: str = ""              # transfer_to_<target>
    tool_description: str = ""
    input_type: Any = None           # 委托时携带的结构化参数 (如 {claim, reason})
    input_filter: str = "summary_only"
    on_handoff: Optional[Callable] = None  # 委托触发回调 (如启动数据预取)


@dataclass
class AgentSpec:
    """激活的单个 Agent 规格."""
    agent_id: str
    role: str                  # technical / fundamental / macro / sentiment
    model_tier: str = "pro"    # flash / pro
    question: str = ""
    subagents: list[SubAgentSpec] = field(default_factory=list)
    handoffs: list[HandoffSpec] = field(default_factory=list)
    context_keys: list[str] = field(default_factory=list)  # 从 snapshot 取哪些数据
    budget_tokens: int = 8000
    depends_on: list[str] = field(default_factory=list)    # 依赖的其他 agent_id (handoff 串行)
    fallback: str = "skip"     # skip / default / retry


@dataclass
class DAGSpec:
    """执行拓扑: 并行(Send) / 串行(handoff) / 条件分支."""
    parallel_groups: list[list[str]] = field(default_factory=list)  # 每组内并行
    serial_chains: list[list[str]] = field(default_factory=list)    # 每条链串行
    conditions: dict[str, str] = field(default_factory=dict)        # agent_id -> 条件表达式


@dataclass
class ExecutionPlan:
    """② → ③ 执行计划 (Planner 产出)."""
    plan_id: str
    symbol: str
    market: str
    data_fetch_manifest: list[DataFetchTask] = field(default_factory=list)
    agent_manifest: list[AgentSpec] = field(default_factory=list)
    dag: DAGSpec = field(default_factory=DAGSpec)
    budget_tokens: int = 30000
    created_at: datetime = field(default_factory=datetime.now)


# ──────────────────────────────────────────────────────────────────────────
# ③ Execution Layer → Evidence Layer
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class Evidence:
    """可追溯的结构化证据.

    v3.1 修复: 用 stance 维度判支持/反对, 替代纯 confidence 判定矛盾.
    stance ∈ {bullish, bearish, neutral}.
    """
    claim: str                # 可追溯断言
    stance: str = "neutral"   # bullish / bearish / neutral ← v3.1
    confidence: float = 0.5   # 0-1
    source: list[str] = field(default_factory=list)  # 数据源 ID
    agent: str = ""
    data_ref: str = ""        # 指向 snapshot/外置存储


@dataclass
class RiskItem:
    """单条风险."""
    category: str             # market / liquidity / fundamental / ...
    description: str
    severity: str = "medium"  # low / medium / high
    mitigation: str = ""


@dataclass
class AgentResult:
    """③ → ④ Agent 结构化输出 (禁止 content[:2000] 截断)."""
    agent_id: str
    role: str
    summary: str = ""               # ≤ 500 tokens
    score: float = 0.5              # 0-1
    confidence: float = 0.5         # 0-1
    evidence: list[Evidence] = field(default_factory=list)
    risk: list[RiskItem] = field(default_factory=list)
    status: str = "ok"              # ok / degraded / failed / skipped


# ──────────────────────────────────────────────────────────────────────────
# ④ Evidence Layer → Reflection Layer
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class AggregatedClaim:
    """按 claim + stance 维度聚合的结论.

    v3.1 修复: supporting=stance bullish/neutral, contradicting=stance bearish.
    低 confidence 只是证据弱, 不一定是反对.
    """
    claim: str
    supporting: list[Evidence] = field(default_factory=list)
    contradicting: list[Evidence] = field(default_factory=list)
    consensus: float = 0.5          # 一致性分数 0-1


@dataclass
class Conflict:
    """冲突标记 (存在 contradicting 证据时)."""
    claim: str
    supporting: list[Evidence] = field(default_factory=list)
    contradicting: list[Evidence] = field(default_factory=list)


@dataclass
class AggregatedEvidence:
    """④ → ⑤ 聚合证据."""
    claims: list[AggregatedClaim] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    coverage: dict[str, float] = field(default_factory=dict)  # role -> 覆盖度 0-1


# ──────────────────────────────────────────────────────────────────────────
# ⑤ Reflection Layer → Decision Layer
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class Issue:
    """反思发现的问题."""
    severity: str            # low / medium / high
    description: str
    agent_id: str = ""


@dataclass
class Correction:
    """修正建议."""
    target: str              # agent_id / claim
    action: str              # rerun / fetch_more / override
    detail: str = ""


@dataclass
class CritiqueResult:
    """⑤ → ⑥ 反思结果 (可回溯, max_reflection_rounds=2)."""
    issues: list[Issue] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    rerun_agents: list[str] = field(default_factory=list)
    need_more_evidence: list[str] = field(default_factory=list)
    can_finalize: bool = True
    round_num: int = 0


# ──────────────────────────────────────────────────────────────────────────
# 横切: Tool Registry 数据结构
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class ToolSpec:
    """候选工具规格 (能力矩阵产出)."""
    tool_id: str
    priority: int = 1         # 1=首选, 2=降级...


@dataclass
class ToolCall:
    """单次工具调用请求."""
    tool_id: str
    params: dict = field(default_factory=dict)
    market: str = ""          # 调用市场上下文 (前置校验需要)
    kind: str = "data"        # data / handoff / subagent
    target_role: str = ""
    subagent_id: str = ""
    input_filter: str = "summary_only"
    input_data: Any = None


@dataclass
class ToolResult:
    """工具调用结果."""
    status: str = "ok"        # ok / cached / invalid / failed / degraded
    data: Any = None
    reason: str = ""          # invalid/failed 时的原因
    tool_id: str = ""         # 实际执行的工具 (fallback 后可能变化)
    cache_key: str = ""
    from_cache: bool = False


# ──────────────────────────────────────────────────────────────────────────
# 横切: Snapshot Store
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class Snapshot:
    """预取数据快照 (Planner 预取目标, Agent 优先读).

    存储原始数据, 经 ContextBuilder 压缩后进入 Prompt.
    全文按 data_ref 回调 (recall).
    """
    symbol: str = ""
    market: str = ""
    quote: dict = field(default_factory=dict)
    history: Any = None        # polars DataFrame 或 dict
    financials: dict = field(default_factory=dict)
    news: list = field(default_factory=list)
    extras: dict = field(default_factory=dict)  # 资金流/dividends/sec_filings 等
    # 外置存储: data_ref -> 原始全文 (recall 时回调)
    store: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def put(self, ref: str, full_text: str) -> None:
        """写入外置存储."""
        self.store[ref] = full_text

    def recall(self, ref: str) -> str:
        """按需召回原始数据 (验证/反思时用). 非默认行为."""
        return self.store.get(ref, "")
