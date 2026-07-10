"""AnalysisPipeline — 端到端编排器 (架构闭环最后一公里).

把 Phase 1-7 的各层模块串联成可运行的完整流水线:
  PlannerService.plan → DAGEngine.run → EvidenceAggregator.aggregate
  → ReflectionAgent.critique → [HITL interrupt] → DecisionAgent.decide
  → OutputGuardrail.check → ReportBuilder.build_markdown

全程:
  - Tracer 全链路追踪 (每个阶段一个 span)
  - on_progress 回调 (阶段进度)
  - HITL interrupt 点 (§10.3 #1, 对接 CheckpointStore)
  - run_streaming async generator (§10.3 #3, 流式产出阶段事件)

依赖注入各层组件 (可测试, 默认用各层单例).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Optional

from ..schemas.contracts import (
    ExecutionPlan, AgentResult, AggregatedEvidence, CritiqueResult, Snapshot,
)
from ..agents.decision_agent import FinalDecision
from ..services.planner_service import PlannerService, planner_service
from ..engine.dag_engine import DAGEngine, dag_engine
from ..services.evidence_store import EvidenceAggregator, evidence_aggregator
from ..agents.reflection_agent import ReflectionAgent, reflection_agent
from ..agents.decision_agent import DecisionAgent, decision_agent
from ..services.output_guardrail import OutputGuardrail, output_guardrail, GuardrailResult
from ..agents.report_builder import ReportBuilder, report_builder
from ..observability.trace import Tracer, tracer
from ..services.checkpoint_store import CheckpointStore, checkpoint_store

logger = logging.getLogger(__name__)

# HITL interrupt 点 (§10.3 #1)
INTERRUPT_PRE_DECISION = "pre_decision"
INTERRUPT_POST_REFLECTION = "post_reflection"

# approval callback 签名: async (interrupt_point, context) -> bool (True=继续, False=中止)
ApprovalCallback = Callable


@dataclass
class PipelineResult:
    """端到端流水线产出."""
    status: str = "ok"               # ok / interrupted / aborted / degraded
    interrupt_point: str = ""        # interrupted 时的暂停点
    plan: Optional[ExecutionPlan] = None
    results: list[AgentResult] = field(default_factory=list)
    aggregated: Optional[AggregatedEvidence] = None
    critique: Optional[CritiqueResult] = None
    decision: Optional[FinalDecision] = None
    guardrail: Optional[GuardrailResult] = None
    report: str = ""                  # markdown
    trace_summary: dict = field(default_factory=dict)
    error: str = ""


class AnalysisPipeline:
    """端到端分析流水线编排器.

    用法:
      pipeline = AnalysisPipeline()
      result = await pipeline.run("AAPL", "分析趋势", market="US-Share")
      print(result.report)

    HITL:
      result = await pipeline.run("AAPL", "分析", interrupt_points={INTERRUPT_PRE_DECISION},
                                  approval_callback=my_callback)
    Streaming:
      async for event in pipeline.run_streaming("AAPL", "分析"):
          print(event)
    """

    def __init__(
        self,
        planner: Optional[PlannerService] = None,
        dag: Optional[DAGEngine] = None,
        aggregator: Optional[EvidenceAggregator] = None,
        reflection: Optional[ReflectionAgent] = None,
        decision: Optional[DecisionAgent] = None,
        guardrail: Optional[OutputGuardrail] = None,
        report: Optional[ReportBuilder] = None,
        tracer: Optional[Tracer] = None,
        checkpoint: Optional[CheckpointStore] = None,
    ):
        self.planner = planner or planner_service
        self.dag = dag or dag_engine
        self.aggregator = aggregator or evidence_aggregator
        self.reflection = reflection or reflection_agent
        self.decision = decision or decision_agent
        self.guardrail = guardrail or output_guardrail
        self.report_builder = report or report_builder
        self.tracer = tracer or Tracer()
        self.checkpoint = checkpoint or checkpoint_store

    async def run(
        self,
        symbol: str,
        question: str = "",
        market: str = "",
        snapshot: Optional[Snapshot] = None,
        on_progress: Optional[Callable] = None,
        interrupt_points: Optional[set] = None,
        approval_callback: Optional[ApprovalCallback] = None,
    ) -> PipelineResult:
        """端到端执行."""
        result = PipelineResult()
        interrupt_points = interrupt_points or set()
        snap = snapshot or Snapshot(symbol=symbol, market=market)

        try:
            # ① Planning
            with self.tracer.span("planning", kind="planning"):
                self._progress(on_progress, "planning", "start")
                plan = await self.planner.plan(symbol, question, market=market)
                result.plan = plan
                self._progress(on_progress, "planning", "done", agents=len(plan.agent_manifest))

            # ② Execution (DAG 动态并行)
            with self.tracer.span("execution", kind="dag"):
                self._progress(on_progress, "execution", "start")
                results = await self.dag.run(plan, snap)
                result.results = results
                self._progress(on_progress, "execution", "done", agents=len(results))

            # ③ Evidence Aggregation
            with self.tracer.span("aggregation", kind="evidence"):
                self._progress(on_progress, "aggregation", "start")
                aggregated = self.aggregator.aggregate(results)
                result.aggregated = aggregated
                self._progress(on_progress, "aggregation", "done",
                               claims=len(aggregated.claims), conflicts=len(aggregated.conflicts))

            # ④ Reflection (可回溯)
            with self.tracer.span("reflection", kind="reflection"):
                self._progress(on_progress, "reflection", "start")
                critique = await self.reflection.critique(aggregated, results, plan, snap)
                result.critique = critique
                self._progress(on_progress, "reflection", "done",
                               can_finalize=critique.can_finalize, issues=len(critique.issues))

            # ④.5 HITL interrupt: post_reflection (§10.3 #1)
            if INTERRUPT_POST_REFLECTION in interrupt_points:
                interrupted = await self._handle_interrupt(
                    INTERRUPT_POST_REFLECTION, result, approval_callback)
                if interrupted:
                    if result.status == "ok":  # 暂停 (非拒绝) → interrupted
                        result.status = "interrupted"
                        result.interrupt_point = INTERRUPT_POST_REFLECTION
                    return result

            # ⑤ HITL interrupt: pre_decision (§10.3 #1)
            if INTERRUPT_PRE_DECISION in interrupt_points:
                interrupted = await self._handle_interrupt(
                    INTERRUPT_PRE_DECISION, result, approval_callback)
                if interrupted:
                    if result.status == "ok":  # 暂停 (非拒绝) → interrupted
                        result.status = "interrupted"
                        result.interrupt_point = INTERRUPT_PRE_DECISION
                    return result

            # ⑥ Decision
            with self.tracer.span("decision", kind="decision"):
                self._progress(on_progress, "decision", "start")
                decision = await self.decision.decide(aggregated, critique, results, symbol=symbol)
                result.decision = decision
                self._progress(on_progress, "decision", "done",
                               action=decision.action, score=decision.final_score)

            # ⑦ Output Guardrail
            with self.tracer.span("guardrail", kind="guardrail"):
                gr = self.guardrail.check(decision, aggregated, critique)
                result.guardrail = gr
                if gr.action == "block" and gr.overridden_decision is not None:
                    result.decision = gr.overridden_decision  # 用修正决策
                    result.status = "degraded"
                self._progress(on_progress, "guardrail", "done", action=gr.action)

            # ⑧ Report
            with self.tracer.span("report", kind="report"):
                self._progress(on_progress, "report", "start")
                result.report = self.report_builder.build_markdown(
                    result.decision, aggregated, results, critique)
                self._progress(on_progress, "report", "done", len=len(result.report))

            result.trace_summary = self.tracer.summary()
            self._progress(on_progress, "done", "complete", result_status=result.status)
            return result

        except Exception as e:
            logger.exception("[Pipeline] 执行失败")
            result.status = "aborted"
            result.error = str(e)
            result.trace_summary = self.tracer.summary()
            return result

    async def run_streaming(
        self, symbol: str, question: str = "", market: str = "",
        snapshot: Optional[Snapshot] = None,
        interrupt_points: Optional[set] = None,
        approval_callback: Optional[ApprovalCallback] = None,
    ) -> AsyncGenerator[dict, None]:
        """流式执行 (§10.3 #3): async generator 产出阶段进度事件."""
        import asyncio
        queue: asyncio.Queue = asyncio.Queue()

        def _on_progress(stage, status, **data):
            queue.put_nowait({"stage": stage, "status": status, **data})

        task = asyncio.create_task(self.run(
            symbol, question, market=market, snapshot=snapshot,
            on_progress=_on_progress, interrupt_points=interrupt_points,
            approval_callback=approval_callback,
        ))

        # 轮询 queue + 检查 task 完成
        while not task.done():
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=0.01)
                yield ev
            except asyncio.TimeoutError:
                pass
        # task 完成, 排空队列
        while not queue.empty():
            yield queue.get_nowait()
        result = task.result()
        yield {"stage": "result", "status": result.status, "result": result}

    # ── HITL ──────────────────────────────────────────────────────────

    async def _handle_interrupt(self, point: str, result: PipelineResult,
                                approval_callback: Optional[ApprovalCallback]) -> bool:
        """处理 HITL 中断点 (§10.3 #1).

        存 checkpoint, 调 approval_callback 等审批.
        Returns: True=已中断(中止或暂停), False=继续.
        """
        # 存 checkpoint (供 resume)
        self.checkpoint.save(f"{result.plan.plan_id}:{point}", result)
        if approval_callback is None:
            # 无回调 → 暂停 (返回中断状态, 外部 resume)
            logger.info("[Pipeline] HITL 中断 @ %s (无回调, 暂停)", point)
            return True
        # 调审批回调
        try:
            approved = await approval_callback(point, {
                "plan_id": result.plan.plan_id,
                "critique": result.critique,
                "aggregated": result.aggregated,
            })
            if not approved:
                logger.info("[Pipeline] HITL @ %s 被拒绝", point)
                result.status = "aborted"
                return True
            return False  # 批准, 继续
        except Exception as e:
            logger.warning("[Pipeline] HITL 审批失败: %s", e)
            return True

    def resume(self, plan_id: str, point: str) -> Optional[PipelineResult]:
        """从 HITL 中断点恢复 (读 checkpoint)."""
        return self.checkpoint.resume(f"{plan_id}:{point}")

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _progress(on_progress, stage, status, **data):
        if on_progress:
            try:
                on_progress(stage, status, **data)
            except Exception:
                pass


# 进程级默认实例
analysis_pipeline = AnalysisPipeline()
