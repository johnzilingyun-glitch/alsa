"""BaseAgent — 独立 Agent 实例 (Phase 2, §4.2.2, ★ v3.1 核心新增).

开发指南 §4.2.2:
  把 Phase 0 的 make_node 闭包改造为独立 Agent 实例:
  有状态 / 可降级 / 可 handoff 委托 / 可派生 SubAgent.

核心方法:
  run(plan, snapshot) → AgentResult
    1. context_builder.build() 构建最小高价值上下文
    2. _reason_with_tools: tool loop (LLM 工具列表含 数据工具 + SubAgent(as_tool) + Handoff)
    3. 解析结构化输出 → AgentResult (移除 2000 字截断, §7.1)
    4. evidence_bus.publish(role, evidence) (替换 history_states)

  run_delegate(filtered_history, input_data, snapshot, depth)
    被 Handoff 委托时执行 (双向委托的接收方). input_filter 已由 Handoff 裁剪.

  _execute_decision(decision, snapshot)
    handoff:   双向委托 (结果回灌, 不替换控制权)
    subagent:  as_tool 嵌套 (不转移控制权)
    data:      普通工具 → ToolRegistry.execute (Phase 1 治理)

降级 (§7.3, v3.1: Phase2 仅 degrade, pause/resume 归 Phase5):
  skip / default(中性) / retry(瞬时错误)

依赖注入: llm_runner 为 Callable, 默认懒导入 agent_orchestrator (避免循环导入).
测试时可注入 mock, 不依赖重型 LLM/数据栈.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ..schemas.contracts import AgentSpec, AgentResult, Evidence, Snapshot
from ..services.context_builder import ContextBuilder, context_builder as _default_cb
from .evidence_bus import EvidenceBus, evidence_bus as _default_bus
from .handoff import Handoff
from .agent_result_schema import parse_agent_output, response_format_spec

logger = logging.getLogger(__name__)

# LLM runner 签名:
#   async llm_runner(prompt: str, *, role: str, response_schema: dict | None,
#                    tools: list | None, model: str) -> str
LLMRunner = Callable


class AgentState:
    """Agent 运行时状态 (可被 handoff/subagent 结果回灌)."""

    def __init__(self):
        self.history: list = []          # 对话/工具历史 (input_filter 用)
        self.tool_results: list = []     # 工具调用结果
        self.injected: list = []         # handoff/subagent 回灌的中间结果
        self.round: int = 0

    def inject(self, result: Any) -> None:
        """回灌 handoff/subagent 结果到当前 Agent 上下文."""
        self.injected.append(result)
        self.history.append({"injected": result})

    def snapshot_history(self) -> list:
        return list(self.history)


class BaseAgent:
    """独立 Agent 实例: 有状态 / 可降级 / 可 handoff / 可派生 SubAgent.

    子类应覆盖:
      - role_prompt(question, ctx) -> str: 角色专属 prompt 组装
      - default_subagents() / default_handoffs(): 角色默认配置 (可选)
    """

    # 子类覆盖: 角色名
    role: str = "BaseAgent"

    def __init__(
        self,
        agent_id: str = "",
        *,
        context_builder: Optional[ContextBuilder] = None,
        evidence_bus: Optional[EvidenceBus] = None,
        llm_runner: Optional[LLMRunner] = None,
        max_tool_rounds: int = 8,
        model: str = "gemini-3.1-pro-preview",
    ):
        self.agent_id = agent_id or self.role
        self.state = AgentState()
        self.context_builder = context_builder or _default_cb
        self.evidence_bus = evidence_bus or _default_bus
        self._llm_runner = llm_runner
        self.max_tool_rounds = max_tool_rounds
        self.model = model
        # SubAgent (as_tool) + Handoff 注册表
        self.subagents: dict[str, "BaseAgent"] = {}
        self.handoffs: dict[str, Handoff] = {}
        # 初始化角色默认配置
        for sub in self.default_subagents():
            self.register_subagent(sub)
        for hf in self.default_handoffs():
            self.register_handoff(hf)

    # ════════════════════════════════════════════════════════════════════════
    # 子类覆盖点
    # ════════════════════════════════════════════════════════════════════════

    def default_subagents(self) -> list["BaseAgent"]:
        """角色默认派生的 SubAgent (子类覆盖)."""
        return []

    def default_handoffs(self) -> list[Handoff]:
        """角色默认可委托的 Handoff (子类覆盖)."""
        return []

    def role_prompt(self, question: str, ctx: dict) -> str:
        """角色专属 prompt (子类覆盖). 默认通用模板."""
        parts = [f"# Role: {self.role}", f"# Task\n{question}"]
        ms = ctx.get("market_summary")
        if ms:
            parts.append(f"# Market Summary\n{ms}")
        fund = ctx.get("fundamentals")
        if fund:
            parts.append(f"# Fundamentals\n{fund}")
        news = ctx.get("news")
        if news:
            parts.append("# News\n" + "\n".join(f"- {n}" for n in news))
        ev = ctx.get("evidence")
        if ev:
            parts.append(f"# Other Agents' Evidence\n{ev}")
        parts.append(
            "# Output\nRespond ONLY as JSON matching the schema: "
            "{summary, score(0-1), confidence(0-1), stance(bullish/bearish/neutral), "
            "evidence[{claim,stance,confidence,source}], risk[{category,description,severity}], status}."
        )
        return "\n\n".join(parts)

    # ════════════════════════════════════════════════════════════════════════
    # 注册
    # ════════════════════════════════════════════════════════════════════════

    def register_subagent(self, sub: "BaseAgent") -> None:
        """注册 SubAgent (as_tool, 父 Agent 调用时不转移控制权)."""
        self.subagents[sub.role] = sub

    def register_handoff(self, hf: Handoff) -> None:
        """注册 Handoff (双向委托, 作为 transfer_to_<target> tool 暴露)."""
        self.handoffs[hf.spec.target_role] = hf

    # ════════════════════════════════════════════════════════════════════════
    # 主入口
    # ════════════════════════════════════════════════════════════════════════

    async def run(self, plan: AgentSpec, snapshot: Snapshot) -> AgentResult:
        """执行 Agent: 构建 ctx → tool loop → 结构化输出 → 发布证据.

        单 Agent 失败不阻塞 (降级返回 default/degraded).
        """
        try:
            # 1. 构建上下文 (复用 Phase 1 ContextBuilder)
            evidence = self.evidence_bus.relevant(self.role) if self.evidence_bus else []
            ctx = self.context_builder.build(
                question=plan.question,
                snapshot=snapshot,
                evidence=self._evidence_brief(evidence),
                budget_tokens=plan.budget_tokens,
            )
            prompt = self.role_prompt(plan.question, ctx)

            # 2. tool loop (含 handoff + subagent as_tool)
            raw_output = await self._reason_with_tools(prompt, snapshot, plan)
            self.state.history.append({"role": self.role, "output": raw_output})

            # 3. 解析结构化输出
            result = parse_agent_output(raw_output, self.agent_id, self.role)

            # 4. 发布证据到 EvidenceBus (替换 history_states)
            if result.evidence and self.evidence_bus:
                self.evidence_bus.publish(self.role, result.evidence)

            return result
        except Exception as e:
            logger.warning("[BaseAgent:%s] run 失败, 降级: %s", self.role, e)
            return self._degrade(plan.fallback, e)

    async def run_delegate(self, filtered_history: list, input_data: dict,
                           snapshot: Snapshot = None, depth: int = 0) -> AgentResult:
        """被 Handoff 委托时执行 (双向委托接收方).

        v3.1 §7.5: 结果回灌当前 Agent, 不替换主控制权.
        input_filter 已由 Handoff.apply_input_filter 裁剪 (治 context).
        """
        # 注入委托方的过滤历史 + 委托参数
        self.state.history = list(filtered_history)
        claim = input_data.get("claim", "") if isinstance(input_data, dict) else str(input_data)
        reason = input_data.get("reason", "") if isinstance(input_data, dict) else ""
        question = f"[Handoff 委托验证] claim: {claim}\nreason: {reason}\n请从 {self.role} 视角验证上述断言."

        plan = AgentSpec(
            agent_id=f"{self.agent_id}#delegate",
            role=self.role,
            question=question,
            budget_tokens=6000,
            fallback="default",
        )
        return await self.run(plan, snapshot or Snapshot())

    # ════════════════════════════════════════════════════════════════════════
    # tool loop
    # ════════════════════════════════════════════════════════════════════════

    async def _reason_with_tools(self, prompt: str, snapshot: Snapshot,
                                 plan: AgentSpec) -> str:
        """LLM 工具列表含: 数据工具 + SubAgent(as_tool) + Handoff(transfer_to_X).

        v3.1 §4.2.2: LLM 可在工具列表中看到 handoff 和 subagent as_tool.
        """
        runner = self._get_llm_runner()
        tools = self._build_tool_list()

        # 注入 handoff/subagent 工具的执行拦截
        # (默认 runner 不识别这些; 这里用包装: 若 LLM 调用 transfer_to_X/subagent,
        #  由本类 _execute_decision 处理. 简化实现: 先无 tool 调用直出结构化 JSON,
        #  handoff/subagent 通过显式 API 触发 — Phase3 再接入 native tool dispatch.)
        try:
            output = await runner(
                prompt,
                role=self.role,
                response_schema=response_format_spec(),
                tools=tools,
                model=self.model,
            )
        except Exception as e:
            logger.warning("[BaseAgent:%s] LLM 调用失败, 强制 finalize: %s", self.role, e)
            output = self._force_finalize(plan)
        return output

    def _build_tool_list(self) -> list:
        """构建工具列表: 数据工具 + SubAgent(as_tool) + Handoff(transfer_to_X)."""
        tools = []
        # Handoff 作为 tool 暴露 (transfer_to_<target>)
        for hf in self.handoffs.values():
            tools.append(hf.as_tool_schema())
        # SubAgent as_tool (作为工具, 不转移控制权)
        for sub_role, sub in self.subagents.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": f"call_{sub_role.lower().replace(' ', '_')}",
                    "description": f"Invoke {sub_role} subagent as a tool to fetch/refine evidence. Does not transfer control.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to investigate"},
                        },
                        "required": ["query"],
                    },
                },
            })
        return tools

    async def _execute_decision(self, decision: dict, snapshot: Snapshot) -> None:
        """执行 LLM 决策: handoff / subagent / data 工具.

        v3.1 §4.2.2:
          handoff:  双向委托 (结果回灌, 不替换控制权)
          subagent: as_tool 嵌套 (不转移控制权)
          data:     普通工具 → ToolRegistry.execute (Phase 1 治理)
        """
        kind = decision.get("kind", "data")
        if kind == "handoff":
            target_role = decision.get("target_role", "")
            hf = self.handoffs.get(target_role)
            if hf:
                result = await hf.execute(
                    decision.get("input_data", {}),
                    self.state.snapshot_history(),
                    snapshot,
                )
                self.state.inject(result)
        elif kind == "subagent":
            sub_role = decision.get("subagent_id", "")
            sub = self.subagents.get(sub_role)
            if sub:
                result = await sub.run_as_tool(decision.get("input_data", {}), snapshot)
                self.state.inject(result)
        else:
            # data 工具: 经 Phase 1 ToolRegistry 治理 (校验+缓存+fallback)
            await self._exec_data_tool(decision, snapshot)

    async def _exec_data_tool(self, decision: dict, snapshot: Snapshot) -> None:
        """普通数据工具经 ToolRegistry.execute (Phase 1 治理)."""
        try:
            from ..services.tools.registry import tool_registry
            from ..schemas.contracts import ToolCall
            call = ToolCall(
                tool_id=decision.get("tool_id", ""),
                params=decision.get("params", {}),
                market=getattr(snapshot, "market", ""),
            )
            result = await tool_registry.execute(call, snapshot)
            self.state.tool_results.append(result)
        except Exception as e:
            logger.debug("[BaseAgent:%s] data tool 失败(非致命): %s", self.role, e)

    # ════════════════════════════════════════════════════════════════════════
    # SubAgent as_tool 入口
    # ════════════════════════════════════════════════════════════════════════

    async def run_as_tool(self, input_data: dict, snapshot: Snapshot) -> AgentResult:
        """作为工具被父 Agent 调用 (OpenAI Agent.as_tool 范式, 不转移控制权).

        返回结果回灌父 Agent 上下文.
        """
        query = input_data.get("query", "") if isinstance(input_data, dict) else str(input_data)
        plan = AgentSpec(
            agent_id=f"{self.agent_id}#astool",
            role=self.role,
            question=query,
            budget_tokens=4000,
            fallback="default",
        )
        return await self.run(plan, snapshot)

    # ════════════════════════════════════════════════════════════════════════
    # 降级 / finalize
    # ════════════════════════════════════════════════════════════════════════

    def _degrade(self, fallback: str, error: Exception) -> AgentResult:
        """降级 (§7.3). v3.1: Phase2 仅 degrade, pause/resume 归 Phase5."""
        mode = fallback or "skip"
        if mode == "default":
            return AgentResult(
                agent_id=self.agent_id, role=self.role, status="degraded",
                summary=f"(degraded: {error})", score=0.5, confidence=0.3,
            )
        if mode == "retry":
            # 瞬时错误重试一次 (此处简化: 返回 skipped, 由上层重试)
            return AgentResult(
                agent_id=self.agent_id, role=self.role, status="skipped",
                summary=f"(retry: {error})", confidence=0.0,
            )
        # skip
        return AgentResult(
            agent_id=self.agent_id, role=self.role, status="skipped",
            summary=f"(skipped: {error})", confidence=0.0,
        )

    def _force_finalize(self, plan: AgentSpec) -> str:
        """超轮次/LLM 失败时强制产出结构化输出."""
        import json
        return json.dumps({
            "summary": f"(force finalized due to tool loop limit/error)",
            "score": 0.5, "confidence": 0.3, "stance": "neutral",
            "evidence": [], "risk": [], "status": "degraded",
        }, ensure_ascii=False)

    # ════════════════════════════════════════════════════════════════════════
    # helpers
    # ════════════════════════════════════════════════════════════════════════

    def _get_llm_runner(self) -> LLMRunner:
        """获取 LLM runner (默认懒导入 agent_orchestrator, 避免循环导入)."""
        if self._llm_runner is not None:
            return self._llm_runner
        return _default_llm_runner

    @staticmethod
    def _evidence_brief(evidence: list) -> str:
        """把其他 Agent 的证据压成 brief (治 context)."""
        if not evidence:
            return ""
        lines = []
        for e in evidence[:10]:  # 最多 10 条
            src = e.agent or "?"
            lines.append(f"- [{src}|{e.stance}|{e.confidence:.1f}] {e.claim}")
        return "\n".join(lines)


async def _default_llm_runner(prompt: str, *, role: str = None,
                              response_schema: dict = None, tools: list = None,
                              model: str = "gemini-3.1-pro-preview") -> str:
    """默认 LLM runner: 懒导入 agent_orchestrator (避免循环导入 & 重型依赖).

    生产环境用此默认; 测试时注入 mock.
    """
    from ..services.agent_orchestrator import agent_orchestrator
    return await agent_orchestrator.generate_with_tools(
        prompt=prompt, model=model, role=role,
        response_schema=response_schema,
    )
