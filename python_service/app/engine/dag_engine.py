"""DAGEngine — 动态并行执行引擎 (Phase 3, §4.2.5, ★ v3.1 核心新增).

开发指南 §4.2.5:
  "固定 Send → 动态 Send (运行时决定并行分支数)"
  build_parallel_branches(plan): Planner 输出多少个独立 Agent, Send 就派发多少并行分支.

v3.1 §4.2.4 并行 vs 串行边界:
  独立 → 并行 (asyncio.gather, 运行时动态分支数)
  依赖 → 串行 (handoff, §4.2.3)
  父子 → 嵌套 (as_tool, §4.2.2)

设计: 纯 asyncio 实现, 不依赖 LangGraph 运行时 (更可控/可测).
  - 拓扑分层 (Kahn): 同层无依赖 → asyncio.gather 并行; 跨层串行.
  - 短路: AgentResult.status=skipped 或数据不足 → 下游跳过 (§4.2 条件路由).
  - rerun: 重跑指定 Agent (供 Phase 4 Reflection 回溯).

与现有代码衔接 (非破坏):
  - discussion_service.build_topology (固定模板) → Planner 动态 ExecutionPlan
  - discussion_service 的 LangGraph StateGraph → DAGEngine (asyncio)
  - 复用 Phase 2: create_agent 工厂 + BaseAgent.run
  - 复用 Phase 1: contracts.ExecutionPlan/AgentSpec/AgentResult
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from ..schemas.contracts import (
    ExecutionPlan, AgentSpec, AgentResult, Snapshot,
)

logger = logging.getLogger(__name__)

# Agent 工厂签名: (role: str, **kwargs) -> BaseAgent (有 run 方法)
AgentFactory = Callable


class DAGEngine:
    """动态并行执行引擎.

    用法:
      engine = DAGEngine(agent_factory=create_agent)
      results = await engine.run(plan, snapshot)
      # results: list[AgentResult]
    """

    def __init__(self, agent_factory: Optional[AgentFactory] = None,
                 max_concurrency: int = 10):
        self.agent_factory = agent_factory
        self.max_concurrency = max_concurrency  # 并发上限 (开发指南 MAX_CONCURRENT_JOBS)

    def build_parallel_branches(self, plan: ExecutionPlan) -> list[list[AgentSpec]]:
        """按 depends_on 拓扑分层: 同层无依赖 → 一组并行分支.

        v3.1 §4.2.5: Planner 输出多少个独立 Agent, 并行分支就有多少.
        运行时决定分支数, 非硬编码.
        """
        specs = {a.agent_id: a for a in plan.agent_manifest}
        # 计算每个 agent 的依赖 (只保留 manifest 内的)
        deps = {aid: set(s.depends_on) & set(specs.keys())
                for aid, s in specs.items()}
        layers: list[list[AgentSpec]] = []
        done: set[str] = set()
        remaining = set(specs.keys())

        while remaining:
            # 本层: 依赖已全部完成的 agent
            layer_ids = [aid for aid in remaining if deps[aid] <= done]
            if not layer_ids:
                # 循环依赖兜底: 强制取剩余中依赖最少的
                logger.warning("[DAG] 检测到循环依赖, 强制破解: %s", remaining)
                layer_ids = [min(remaining, key=lambda x: len(deps[x]))]
            layer = [specs[aid] for aid in layer_ids]
            layers.append(layer)
            done.update(layer_ids)
            remaining -= set(layer_ids)
        return layers

    async def run(self, plan: ExecutionPlan, snapshot: Snapshot) -> list[AgentResult]:
        """执行 DAG: 分层并行, 跨层串行, 支持短路.

        Returns:
            list[AgentResult] (顺序按完成时间)
        """
        layers = self.build_parallel_branches(plan)
        results: list[AgentResult] = []
        short_circuit = False

        for i, layer in enumerate(layers):
            if short_circuit:
                # 短路: 跳过下游, 标记 skipped
                for spec in layer:
                    results.append(AgentResult(
                        agent_id=spec.agent_id, role=spec.role,
                        status="skipped", summary="(short-circuited)",
                    ))
                continue

            # 同层并行 (asyncio.gather, 运行时分支数)
            layer_results = await self._run_layer(layer, snapshot)
            results.extend(layer_results)

            # 短路检测: 数据严重不足 → 跳过下游
            if any(self._is_short_circuit(r) for r in layer_results):
                logger.info("[DAG] 第 %d 层触发短路, 跳过下游", i + 1)
                short_circuit = True

        return results

    async def _run_layer(self, layer: list[AgentSpec], snapshot: Snapshot) -> list[AgentResult]:
        """并行执行一层 (asyncio.gather, 并发上限)."""
        if len(layer) == 1:
            return [await self._run_one(layer[0], snapshot)]
        # 并发上限控制
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _guarded(spec):
            async with sem:
                return await self._run_one(spec, snapshot)

        return await asyncio.gather(*[_guarded(s) for s in layer])

    async def _run_one(self, spec: AgentSpec, snapshot: Snapshot) -> AgentResult:
        """执行单个 Agent (复用 Phase 2 BaseAgent.run)."""
        factory = self._get_factory()
        try:
            agent = factory(spec.role, agent_id=spec.agent_id)
            return await agent.run(spec, snapshot)
        except Exception as e:
            logger.warning("[DAG] Agent %s 执行失败, 降级: %s", spec.agent_id, e)
            return AgentResult(
                agent_id=spec.agent_id, role=spec.role,
                status="degraded", summary=f"(engine error: {e})",
                confidence=0.3,
            )

    async def rerun(self, plan: ExecutionPlan, snapshot: Snapshot,
                    agent_ids: list[str]) -> list[AgentResult]:
        """重跑指定 Agent (供 Phase 4 Reflection 回溯, §4.4).

        只重跑指定 agent_id, 不动其他.
        """
        specs = {a.agent_id: a for a in plan.agent_manifest}
        to_rerun = [specs[aid] for aid in agent_ids if aid in specs]
        if not to_rerun:
            return []
        return await self._run_layer(to_rerun, snapshot)

    # ── helpers ──────────────────────────────────────────────────────────

    def _get_factory(self) -> AgentFactory:
        if self.agent_factory is not None:
            return self.agent_factory
        # 默认懒导入 Phase 2 create_agent (避免循环导入)
        from ..agents.expert_agents import create_agent
        return create_agent

    @staticmethod
    def _is_short_circuit(result: AgentResult) -> bool:
        """短路检测: 数据严重不足 (开发指南 §4.2 条件路由)."""
        if result.status == "skipped":
            return True
        markers = ("数据严重不足", "无法获取", "CRITICAL_DATA_MISSING", "no data")
        s = (result.summary or "").lower()
        return any(m.lower() in s for m in markers)


# 进程级默认实例
dag_engine = DAGEngine()
