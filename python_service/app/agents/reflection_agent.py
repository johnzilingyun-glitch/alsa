"""ReflectionAgent — 可回溯反思 (Phase 4, §4.4, ★ v3.1 rerun 动态预算).

开发指南 §4.4:
  交叉验证 + 自我纠错 → 可回溯补查/重跑 (max=2 防死循环)
  → CritiqueResult {issues[], corrections[], rerun_agents[], need_more_evidence[], can_finalize}

流程 (§4.4):
  critique(aggregated, results, round_num=0) → CritiqueResult
    1. round_num >= MAX_REFLECTION_ROUNDS → 强制 finalize
    2. critique_generator 生成 critique (默认规则, 可注入 Pro LLM)
    3. if not can_finalize:
         need_more_evidence → _fetch_more (经 ToolRegistry)
         rerun_agents → DAGEngine.rerun → merge → re-aggregate
         → 递归 critique(round_num+1)  ← 计数防死循环
    4. return critique

v3.1 §7.2 rerun 动态预算: rerun 时 budget +2k 容纳冲突注入 (不再固定预算).
  通过 role_router.resolve_budget(role, is_rerun=True) 实现.

与现有代码衔接 (非破坏):
  - self_reflection_agent.SelfReflectionAgent (一次性反思) → ReflectionAgent (可回溯)
  - critic_agent.CriticAgent → ReflectionAgent (升级)
  - 复用 Phase 3: DAGEngine.rerun + EvidenceAggregator.aggregate
  - 复用 Phase 1: ToolRegistry (补查) + contracts.CritiqueResult
"""

from __future__ import annotations

import os
import logging
from typing import Any, Callable, Optional

from ..schemas.contracts import (
    CritiqueResult, Issue, Correction, AggregatedEvidence, AgentResult,
    ExecutionPlan, Snapshot,
)

logger = logging.getLogger(__name__)

MAX_REFLECTION_ROUNDS = int(os.getenv("MAX_REFLECTION_ROUNDS", "2"))
REFLECTION_CONFLICT_THRESHOLD = float(os.getenv("REFLECTION_CONFLICT_THRESHOLD", "0.4"))


class ReflectionAgent:
    """可回溯反思 Agent (⑤ Reflection Layer).

    用法:
      reflection = ReflectionAgent(dag_engine=eng, aggregator=agg)
      critique = await reflection.critique(aggregated, results, plan, snapshot)
      # critique.can_finalize / critique.rerun_agents / critique.issues
    """

    def __init__(
        self,
        dag_engine=None,
        aggregator=None,
        critique_generator: Optional[Callable] = None,
        max_rounds: int = None,
    ):
        # 懒导入默认值 (避免循环)
        self._dag = dag_engine
        self._aggregator = aggregator
        self._critique_generator = critique_generator
        self.max_rounds = max_rounds if max_rounds is not None else MAX_REFLECTION_ROUNDS

    async def critique(
        self,
        aggregated: AggregatedEvidence,
        results: list[AgentResult],
        plan: ExecutionPlan = None,
        snapshot: Snapshot = None,
        round_num: int = 0,
    ) -> CritiqueResult:
        """反思 + 可回溯. 递归 + 计数防死循环 (§4.4)."""
        # 1. 超轮次强制 finalize
        if round_num >= self.max_rounds:
            logger.info("[Reflection] 达 max_rounds=%d, 强制 finalize", self.max_rounds)
            return CritiqueResult(
                can_finalize=True, round_num=round_num,
                issues=[Issue(severity="medium",
                              description=f"已达反思上限({self.max_rounds}), 证据不足强制 finalize")],
            )

        # 2. 生成 critique (默认规则, 可注入 Pro LLM)
        critique = await self._generate_critique(aggregated, results, round_num)
        critique.round_num = round_num

        # 3. 不可 finalize → 回溯
        if not critique.can_finalize:
            # 3a. 补查缺失证据 (经 ToolRegistry)
            if critique.need_more_evidence:
                await self._fetch_more(critique.need_more_evidence, snapshot)

            # 3b. 重跑指定 Agent (DAGEngine.rerun, §4.4)
            if critique.rerun_agents and plan is not None and self._get_dag() is not None:
                rerun_results = await self._get_dag().rerun(
                    plan, snapshot or Snapshot(), critique.rerun_agents,
                )
                # merge: 替换同 agent_id 的旧结果
                results = self._merge(results, rerun_results)
                # re-aggregate
                agg = self._get_aggregator()
                if agg is not None:
                    aggregated = agg.aggregate(results)
                # 递归 + 计数
                logger.info("[Reflection] round %d 触发回溯, rerun %s",
                            round_num, critique.rerun_agents)
                return await self.critique(aggregated, results, plan, snapshot, round_num + 1)

        return critique

    # ════════════════════════════════════════════════════════════════════════
    # critique 生成 (默认规则, 可注入 LLM)
    # ════════════════════════════════════════════════════════════════════════

    async def _generate_critique(
        self,
        aggregated: AggregatedEvidence,
        results: list[AgentResult],
        round_num: int,
    ) -> CritiqueResult:
        """生成 CritiqueResult. 默认规则, 可注入 critique_generator (Pro LLM)."""
        if self._critique_generator is not None:
            try:
                return await self._critique_generator(aggregated, results, round_num)
            except Exception as e:
                logger.warning("[Reflection] critique_generator 失败, 退回规则: %s", e)
        return self._rule_based_critique(aggregated, results, round_num)

    def _rule_based_critique(
        self,
        aggregated: AggregatedEvidence,
        results: list[AgentResult],
        round_num: int,
    ) -> CritiqueResult:
        """规则生成 critique: 基于 conflicts + coverage + status.

        判定逻辑:
          - 有 conflicts → rerun 冲突相关 agent (低 consensus 的 claim 对应 agent)
          - 有 skipped/degraded agent → rerun
          - coverage 低 (<0.3) → need_more_evidence
          - 无冲突 + 无 skipped + 平均 coverage >0.5 → can_finalize
        """
        issues: list[Issue] = []
        corrections: list[Correction] = []
        rerun_agents: list[str] = []
        need_more: list[str] = []

        # 1. 冲突检测: aggregated.conflicts
        for conflict in aggregated.conflicts:
            # 收集冲突双方的 agent
            conflict_agents = set()
            for e in conflict.supporting + conflict.contradicting:
                if e.agent:
                    conflict_agents.add(e.agent)
            issues.append(Issue(
                severity="high",
                description=f"证据冲突: {conflict.claim} (涉及 {conflict_agents})",
            ))
            # rerun 冲突相关的 agent (取 results 中 role 匹配的 agent_id)
            for ag_id in self._find_agent_ids(results, conflict_agents):
                if ag_id not in rerun_agents:
                    rerun_agents.append(ag_id)
            corrections.append(Correction(
                target=conflict.claim, action="rerun",
                detail=f"重跑 {conflict_agents} 交叉验证 {conflict.claim}",
            ))

        # 2. skipped/degraded agent → rerun
        for r in results:
            if r.status in ("skipped", "degraded") and r.agent_id not in rerun_agents:
                issues.append(Issue(
                    severity="medium",
                    description=f"{r.role} 状态={r.status}, 需重跑",
                    agent_id=r.agent_id,
                ))
                rerun_agents.append(r.agent_id)
                corrections.append(Correction(
                    target=r.agent_id, action="rerun", detail=f"重跑 {r.role}",
                ))

        # 3. coverage 不足 → need_more_evidence
        low_cov = [role for role, cov in aggregated.coverage.items() if cov < 0.3]
        for role in low_cov:
            need_more.append(f"{role} 证据覆盖不足 (coverage<0.3)")

        # 4. can_finalize 判定
        avg_cov = (sum(aggregated.coverage.values()) / len(aggregated.coverage)
                   if aggregated.coverage else 0.0)
        has_failures = any(r.status in ("skipped", "degraded") for r in results)
        can_finalize = (not aggregated.conflicts) and (not has_failures) and (avg_cov >= 0.5)

        # 第一轮即使有问题也允许 finalize (除非有严重冲突), 避免无谓重跑
        # 实际由 round_num 上限兜底; 这里保守: 有冲突就不 finalize
        return CritiqueResult(
            issues=issues, corrections=corrections,
            rerun_agents=rerun_agents, need_more_evidence=need_more,
            can_finalize=can_finalize, round_num=round_num,
        )

    # ════════════════════════════════════════════════════════════════════════
    # 回溯辅助
    # ════════════════════════════════════════════════════════════════════════

    async def _fetch_more(self, need_more: list[str], snapshot: Snapshot) -> None:
        """补查缺失证据 (经 Phase 1 ToolRegistry, §4.4)."""
        try:
            from ..services.tools.registry import tool_registry
            from ..schemas.contracts import ToolCall
            for need in need_more:
                # need_more 是描述性字符串, 这里简化: 不实际调用 (需 data_type 映射)
                # 实际生产: 解析 need → data_type → ToolRegistry.execute
                logger.debug("[Reflection] 需补查: %s", need)
        except Exception as e:
            logger.debug("[Reflection] 补查失败(非致命): %s", e)

    @staticmethod
    def _merge(results: list[AgentResult], rerun_results: list[AgentResult]) -> list[AgentResult]:
        """merge: rerun 结果替换同 agent_id 的旧结果."""
        rerun_map = {r.agent_id: r for r in rerun_results}
        merged = [rerun_map.get(r.agent_id, r) for r in results]
        # 追加新增的 rerun 结果 (agent_id 不在原 results)
        existing_ids = {r.agent_id for r in results}
        for r in rerun_results:
            if r.agent_id not in existing_ids:
                merged.append(r)
        return merged

    @staticmethod
    def _find_agent_ids(results: list[AgentResult], roles: set[str]) -> list[str]:
        """按 role 名找 agent_id."""
        return [r.agent_id for r in results if r.role in roles]

    def _get_dag(self):
        if self._dag is not None:
            return self._dag
        try:
            from ..engine.dag_engine import dag_engine
            return dag_engine
        except Exception:
            return None

    def _get_aggregator(self):
        if self._aggregator is not None:
            return self._aggregator
        try:
            from ..services.evidence_store import evidence_aggregator
            return evidence_aggregator
        except Exception:
            return None


# 进程级默认实例
reflection_agent = ReflectionAgent()
