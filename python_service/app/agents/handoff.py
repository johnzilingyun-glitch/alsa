"""Handoff — 双向委托机制 (Phase 2, §4.2.3, ★ v3.1 核心新增).

开发指南 §4.2.3, 参照 OpenAI Agents SDK 的 handoff():
  handoff 作为 tool 暴露给 LLM (tool_name = transfer_to_<target>),
  LLM 决定何时委托. 委托时携带结构化参数 (input_type), 接收方经
  input_filter 控制可见的历史范围 (治 context).

与 EvidenceBus 的区别 (§4.2.3):
  EvidenceBus = 异步, Agent 完成后发布 → 适合独立并行
  Handoff     = 同步, Agent A 执行中请求 B 验证 → 适合有依赖

input_filter 是治 context 的关键 (OpenAI input_filter 范式):
  - "summary_only": 只传上一轮摘要 (默认, 最小 context)
  - "recent_2":     传最近 2 轮全文
  - "full":         传完整历史 (仅关键决策用)

v3.1 规范 (§7.5):
  1. handoff 默认 summary_only
  2. 必须带 input_type (结构化委托参数)
  3. 结果回灌当前 Agent, 不替换主控制权 (除非显式 transfer)
  4. handoff 链深度上限 = 2 (HANDOFF_MAX_DEPTH, 防 A→B→A→B)
"""

from __future__ import annotations

import os
import logging
from typing import Any, Callable, Optional

from ..schemas.contracts import HandoffSpec

logger = logging.getLogger(__name__)

HANDOFF_MAX_DEPTH = int(os.getenv("HANDOFF_MAX_DEPTH", "2"))
HANDOFF_DEFAULT_FILTER = os.getenv("HANDOFF_DEFAULT_FILTER", "summary_only")


def apply_input_filter(history: list, filter_mode: str) -> list:
    """按 input_filter 裁剪历史, 治 context.

    Args:
        history: 调用方的对话/工具历史 (list[dict] 或 list[str])
        filter_mode: summary_only / recent_2 / full

    Returns:
        裁剪后的历史 (不修改原列表)
    """
    if not history:
        return []
    if filter_mode == "full":
        return list(history)
    if filter_mode == "recent_2":
        return list(history[-2:])
    # summary_only (默认): 只传最后一条的摘要
    if not history:
        return []
    last = history[-1]
    if isinstance(last, dict):
        # 取 summary/content 字段, 截断
        s = last.get("summary") or last.get("content") or str(last)
        return [{"summary": s[:600] if isinstance(s, str) else str(s)[:600]}]
    if isinstance(last, str):
        return [{"summary": last[:600]}]
    return [{"summary": str(last)[:600]}]


class Handoff:
    """双向委托机制.

    持有 HandoffSpec + 目标 Agent 引用 (duck typing: 目标需有 run_delegate).
    as_tool_schema() 生成 transfer_to_<target> 的 function tool 给 LLM.
    execute() 执行委托: 过滤 context → 调用目标 run_delegate → 返回结果.
    """

    def __init__(self, spec: HandoffSpec, target_agent: Any = None):
        self.spec = spec
        self.target = target_agent
        # 运行时链深度跟踪 (防循环)
        self._depth = 0

    @property
    def tool_name(self) -> str:
        return self.spec.tool_name or f"transfer_to_{self.spec.target_role}"

    @property
    def tool_description(self) -> str:
        if self.spec.tool_description:
            return self.spec.tool_description
        return (
            f"Handoff to {self.spec.target_role} agent. Use when you need "
            f"cross-validation or evidence from {self.spec.target_role} perspective. "
            f"Pass a structured claim + reason for the delegation."
        )

    def as_tool_schema(self) -> dict:
        """生成 OpenAI function tool schema (暴露给 LLM)."""
        # input_type 决定参数 schema; 默认 {claim, reason}
        props = {"claim": {"type": "string", "description": "需委托验证的断言"},
                 "reason": {"type": "string", "description": "委托原因"}}
        if isinstance(self.spec.input_type, dict):
            props = self.spec.input_type
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.tool_description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": list(props.keys())[:1],
                },
            },
        }

    async def execute(self, input_data: dict, caller_history: list,
                      caller_snapshot: Any = None) -> Any:
        """执行委托: 过滤 context → 调用目标 run_delegate → 返回结果.

        v3.1 §7.5: 结果回灌当前 Agent, 不替换主控制权.
        v3.1 §7.5: 链深度上限 HANDOFF_MAX_DEPTH.
        """
        if self._depth >= HANDOFF_MAX_DEPTH:
            logger.warning("[Handoff] 链深度达上限 %d, 拒绝委托到 %s",
                           HANDOFF_MAX_DEPTH, self.spec.target_role)
            return {"status": "skipped", "reason": f"handoff depth limit ({HANDOFF_MAX_DEPTH})"}

        if self.target is None:
            logger.warning("[Handoff] 无目标 Agent: %s", self.spec.target_role)
            return {"status": "skipped", "reason": "no target agent"}

        # 触发 on_handoff 回调 (如启动数据预取)
        if self.spec.on_handoff is not None:
            try:
                self.spec.on_handoff(self.spec.target_role, input_data)
            except Exception as e:
                logger.debug("[Handoff] on_handoff 回调失败: %s", e)

        # input_filter 治 context
        filtered = apply_input_filter(caller_history, self.spec.input_filter)

        self._depth += 1
        try:
            result = await self.target.run_delegate(
                filtered_history=filtered,
                input_data=input_data,
                snapshot=caller_snapshot,
                depth=self._depth,
            )
            return result
        except Exception as e:
            logger.warning("[Handoff] 委托 %s 失败: %s", self.spec.target_role, e)
            return {"status": "failed", "reason": str(e)}
        finally:
            self._depth -= 1


def make_handoff(target_role: str, target_agent: Any = None,
                 input_filter: str = None, input_type: Any = None,
                 tool_description: str = "", on_handoff: Optional[Callable] = None) -> Handoff:
    """便捷构造 Handoff (默认 summary_only)."""
    spec = HandoffSpec(
        target_role=target_role,
        tool_name=f"transfer_to_{target_role.lower().replace(' ', '_')}",
        tool_description=tool_description,
        input_type=input_type,
        input_filter=input_filter or HANDOFF_DEFAULT_FILTER,
        on_handoff=on_handoff,
    )
    return Handoff(spec, target_agent)
