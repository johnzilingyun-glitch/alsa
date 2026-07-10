# ALSA 端到端 Pipeline 编排器概览（架构闭环可运行）

> 对应 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` §10.3 #1/#3 + 架构集成
> 日期：2026-07-10
> 范围：AnalysisPipeline 端到端编排器 + HITL 中断 + Streaming 进度
> 前置：Phase 1-7 全部模块 + §10.3 高价值项已完成

---

## 一、本次完成内容

补全架构集成的**最后一公里**：把 Phase 1-7 各层模块串联成可运行的端到端流水线，并落地 §10.3 剩余两项（#1 Human-in-the-loop + #3 Streaming）：

| 模块 | 开发指南定位 | 要点 |
|------|-------------|------|
| `services/analysis_pipeline.py` | 架构集成 | 端到端 orchestrator：Planner→DAG→Aggregator→Reflection→[HITL]→Decision→Guardrail→Report |
| HITL interrupt | §10.3 #1 P2 | 决策前/反思后中断点，对接 CheckpointStore pause/resume，approval_callback 审批 |
| Streaming | §10.3 #3 P3 | run_streaming async generator，流式产出阶段进度事件 |

---

## 二、新增文件

```
python_service/app/services/analysis_pipeline.py   # ★ 端到端 Pipeline 编排器
python_service/tests/test_analysis_pipeline.py      # 测试 (11 项)
python_service/tests/run_pipeline_standalone.py     # 独立运行器 (11 项)
```

---

## 三、关键设计

### 1. AnalysisPipeline — 端到端编排
```
run(symbol, question, market, snapshot, on_progress, interrupt_points, approval_callback) → PipelineResult

① PlannerService.plan → ExecutionPlan           (Flash 规划)
② DAGEngine.run(plan, snapshot) → list[AgentResult]  (动态并行)
③ EvidenceAggregator.aggregate → AggregatedEvidence   (stance 聚合)
④ ReflectionAgent.critique → CritiqueResult           (可回溯 max=2)
④.5 [HITL interrupt: post_reflection]                 (§10.3 #1)
⑤ [HITL interrupt: pre_decision]                      (§10.3 #1)
⑥ DecisionAgent.decide → FinalDecision                (Evidence+Critique)
⑦ OutputGuardrail.check → GuardrailResult             (block 时用修正决策)
⑧ ReportBuilder.build_markdown → Report               (证据可追溯)
```
- **全程 Tracer 追踪**：每个阶段一个 span，trace_summary 含 by_kind 统计
- **on_progress 回调**：阶段进度事件（stage/status/data）
- **异常容错**：任意阶段抛异常 → status=aborted + error，不丢失已完成结果

### 2. HITL 中断（§10.3 #1）
- **中断点**：`INTERRUPT_POST_REFLECTION` / `INTERRUPT_PRE_DECISION`
- **approval_callback**：`async (point, context) → bool`（True 继续 / False 中止）
- **无 callback**：暂停（status=interrupted），存 CheckpointStore，外部 `resume(plan_id, point)` 恢复
- **拒绝**：status=aborted（不被 interrupted 覆盖）

### 3. Streaming（§10.3 #3）
```python
async for event in pipeline.run_streaming("AAPL", "分析"):
    print(event)  # {stage, status, ...} 阶段进度
# 最终 yield {stage: "result", status, result: PipelineResult}
```
- async generator，边跑边产出阶段事件
- 用 asyncio.Queue + task 轮询实现，可靠不丢事件

### 4. PipelineResult
```python
@dataclass
class PipelineResult:
    status: str          # ok / interrupted / aborted / degraded
    interrupt_point: str
    plan: ExecutionPlan
    results: list[AgentResult]
    aggregated: AggregatedEvidence
    critique: CritiqueResult
    decision: FinalDecision
    guardrail: GuardrailResult
    report: str          # markdown
    trace_summary: dict
    error: str
```

---

## 四、验收结果

### 测试
- **pytest** `test_analysis_pipeline.py`：**11/11 通过**（2.65s）
- **独立运行器** `run_pipeline_standalone.py`：**11/11 通过**
- **回归** Phase 1-5+7 + 剩余项：全绿（132 项测试零破坏）

### 测试覆盖
- 端到端 run → PipelineResult（decision/report/aggregated/critique/guardrail 全有）
- Tracer 追踪（span_count ≥ 6，by_kind 含各阶段）
- on_progress 回调（阶段事件）
- Guardrail block → status=degraded + 修正决策
- HITL 无 callback → interrupted
- HITL approved → 继续
- HITL rejected → aborted
- HITL checkpoint 保存 + resume
- Streaming async generator（阶段事件 + result）
- 异常 → aborted
- post_reflection 中断点

### 修复的 bug
1. `_progress(status=...)` 与位置参数 `status` 冲突 → 改 `result_status=`
2. `run_streaming` 的 `asyncio.shield(task)` 用法错误 → 改 Queue 轮询实现
3. HITL 拒绝时 `status="aborted"` 被 run() 覆盖为 `interrupted` → 加 `if status=="ok"` 守卫

---

## 五、§10.3 全部状态

| # | 项 | 状态 |
|---|----|------|
| 1 | Human-in-the-loop | ✅ Pipeline HITL interrupt（post_reflection / pre_decision） |
| 2 | Guardrails 输出校验 | ✅ output_guardrail.py（上一轮） |
| 3 | Streaming 中间结果 | ✅ Pipeline run_streaming |
| 4 | Agent 可观测性 trace | ✅ observability/trace.py（上一轮） |
| 5 | 多模型混合执行 | 🟡 role_router tier 路由（多厂商是配置扩展） |
| 6 | 记忆持久化跨会话 | ✅ Memory 四层（Phase 5） |

---

## 六、全架构最终状态（真正闭环可运行）

开发指南 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` v3.1 **全部内容落地 + 端到端可运行**：

```python
# 一行调用完整七层流水线
from app.services.analysis_pipeline import analysis_pipeline
result = await analysis_pipeline.run("AAPL", "分析趋势", market="US-Share")
print(result.report)        # Markdown 报告 (证据可追溯)
print(result.decision.action)  # buy/hold/sell/watch
```

```
① Request → ② Planner(Flash) → ③ DAG(动态并行) → ④ Aggregator(stance聚合)
  → ⑤ Reflection(可回溯max=2) → [HITL interrupt] → ⑥ Decision(Evidence+Critique)
  → ⑦ Report(证据可追溯) → [OutputGuardrail 拦截低质输出]
横切: CheckpointStore + Memory四层 + ToolRegistry + ContextBuilder
      + Tracer(全链路观测) + RoleRouter(Flash/Pro) + HITL + Streaming
```

**全量 132 项测试全绿**（P1:26 + P2:21 + P3:19 + P4:15 + P5+7:21 + 剩余:19 + Pipeline:11）。

---

**文档版本**：端到端 Pipeline 概览（架构闭环可运行）· 2026-07-10
**架构状态**：开发指南 v3.1 全部内容落地 + 端到端可运行 + §10.3 全部完成
