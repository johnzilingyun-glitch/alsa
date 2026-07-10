"""ToolRegistry — 工具注册表 + 能力矩阵 + 调用治理 (Phase 1, §4.6).

开发指南 §4.6.1 设计目标:
  "不只'限制调用', 更要'充分且不重复/不无效地调用'."

三层调用治理 (§4.6.2):
  L1 预取层 — Planner 预取写入 snapshot, Agent 优先读
  L2 缓存层 — 跨 Agent 共享缓存 (shared_cache.py)         ← 集成
  L3 校验层 — 前置条件校验 (preconditions.py)             ← 集成

能力矩阵 (§4.6.1 CAPABILITY_MATRIX):
  data_type → [(tool_id, priority), ...]
  resolve(data_type) 供 Planner 生成 data_fetch_manifest.

execute(ToolCall) 治理流程:
  前置校验 → 查共享缓存 → 执行注册 callable / 外部 executor
  → 结果有效性校验 → 失败按 fallback chain 降级 → 写缓存 → 记指标

★ 向后兼容: 100% 保留原有 API (register/get_tool/get_all_schemas/
  is_computation_tool/get_registered_names). 新治理层为 opt-in 叠加,
  现有 expert_tools.ToolExecutor 与 agent_orchestrator 无需改动即可继续工作.

与现有代码衔接:
  - expert_tools.TOOL_DEFINITIONS + tool_registry.get_all_schemas() 合并不变.
  - tools/__init__.py 的 `from .registry import tool_registry` 不变.
  - search.py/iwencai.py/ths_tools.py 的 @tool_registry.register 装饰器不变.
  - 渐进迁移: ToolExecutor._result_cache 可逐步由 shared_tool_cache 取代.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Callable, Awaitable, List, Optional

from .shared_cache import shared_tool_cache, make_cache_key
from .preconditions import validate_precondition, is_valid_result
from .metrics import tool_metrics

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表 + 能力矩阵 + 调用治理.

    向后兼容层: register / get_tool / get_all_schemas / is_computation_tool /
    get_registered_names 保持原签名与行为.
    治理层 (opt-in): resolve / validate / execute / register_capability.
    """

    # ── 能力矩阵: data_type → [(tool_id, priority), ...] (§4.6.1) ──────────
    CAPABILITY_MATRIX: Dict[str, List[tuple]] = {
        "realtime_quote":   [("fetch_realtime_quote", 1), ("financial_data", 2)],
        "history_kline":    [("fetch_history", 1), ("calculate_indicators", 2)],
        "financial_stmt":   [("financial_data", 1), ("finance_query", 2)],
        "news":             [("news_search", 1), ("web_search", 2)],
        "industry_data":    [("business_query", 1), ("web_search", 2)],
        "macro_indicator":  [("macro_query", 1)],
        "deep_content":     [("deep_scrape", 1)],
    }

    # 工具 → data_type 反查 (用于 execute 时确定缓存 TTL)
    _TOOL_DATA_TYPE: Dict[str, str] = {}

    def __init__(self):
        # ── 原有: 装饰器注册的 callable ──────────────────────────────────
        self._tools: Dict[str, Callable[[Any], Awaitable[str]]] = {}
        self._schemas: List[Dict[str, Any]] = []
        self._computation_tools: set = set()
        # ── 新增: 治理层依赖 ────────────────────────────────────────────
        self._cache = shared_tool_cache
        self._metrics = tool_metrics
        # 外部 executor (可选): 用于治理 expert_tools 中非装饰器注册的工具.
        # 签名: async executor(tool_id: str, params: dict) -> str
        self._external_executor: Optional[Callable] = None

    # ════════════════════════════════════════════════════════════════════════
    # 向后兼容层 (原 API, 签名与行为不变)
    # ════════════════════════════════════════════════════════════════════════

    def register(self, schema: Dict[str, Any], is_computation: bool = False):
        """装饰器: 注册工具 schema + callable. (原 API, 不变)

        新增副作用: 同步登记到 metrics (用于 never_called 检测).
        """
        def decorator(func):
            name = schema["name"]
            self._tools[name] = func
            self._schemas.append(schema)
            if is_computation:
                self._computation_tools.add(name)
            self._metrics.register_tool(name)  # 新增: 登记
            return func
        return decorator

    def get_tool(self, name: str) -> Optional[Callable]:
        return self._tools.get(name)

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        return self._schemas

    def is_computation_tool(self, name: str) -> bool:
        return name in self._computation_tools

    def get_registered_names(self) -> List[str]:
        return list(self._tools.keys())

    # ════════════════════════════════════════════════════════════════════════
    # 治理层 (新增, opt-in)
    # ════════════════════════════════════════════════════════════════════════

    def set_external_executor(self, executor: Callable) -> None:
        """注入外部执行器 (治理 expert_tools 中非装饰器注册的工具).

        expert_tools.ToolExecutor 负责分发 TOOL_DEFINITIONS 中的工具;
        注入后 ToolRegistry.execute 可治理这些工具 (校验+缓存+fallback).
        """
        self._external_executor = executor

    def register_capability(self, data_type: str, tool_id: str, priority: int = 1) -> None:
        """显式登记能力 (扩展能力矩阵)."""
        bucket = self.CAPABILITY_MATRIX.setdefault(data_type, [])
        # 去重: 同 tool_id 取更小 priority
        for i, (tid, _) in enumerate(bucket):
            if tid == tool_id:
                bucket[i] = (tool_id, min(bucket[i][1], priority))
                break
        else:
            bucket.append((tool_id, priority))
            bucket.sort(key=lambda x: x[1])
        self._TOOL_DATA_TYPE[tool_id] = data_type
        self._metrics.register_tool(tool_id)

    def resolve(self, data_type: str) -> List[Dict[str, Any]]:
        """数据需求 → 候选工具 (按优先级). 供 Planner 生成 data_fetch_manifest.

        Returns: [{"tool_id": str, "priority": int}, ...]
        """
        return [
            {"tool_id": tid, "priority": prio}
            for tid, prio in self.CAPABILITY_MATRIX.get(data_type, [])
        ]

    def data_type_of(self, tool_id: str) -> str:
        """反查工具对应的 data_type (确定缓存 TTL)."""
        return self._TOOL_DATA_TYPE.get(tool_id, "")

    def validate(self, tool_id: str, params: dict, market: str = "",
                 approval_granted: bool = False) -> tuple:
        """前置校验 (委托 preconditions.validate_precondition)."""
        return validate_precondition(tool_id, params, market,
                                     approval_granted=approval_granted)

    async def execute(self, call, snapshot=None) -> Any:
        """治理执行: 校验 → 缓存 → 执行 → fallback → 缓存写回 → 记指标.

        Args:
            call: ToolCall (schemas.contracts) 或 dict {tool_id, params, market}
            snapshot: 可选 Snapshot (本 Phase 暂不优先读, 留 Phase3 预取衔接)

        Returns:
            ToolResult (schemas.contracts)
        """
        from ...schemas.contracts import ToolResult

        # 归一化输入 (兼容 ToolCall dataclass 与 dict)
        if hasattr(call, "tool_id"):
            tool_id = call.tool_id
            params = call.params or {}
            market = getattr(call, "market", "")
        else:
            tool_id = call.get("tool_id") or call.get("tool", "")
            params = call.get("params", call) or {}
            market = call.get("market", "")

        data_type = self.data_type_of(tool_id)

        # ── L3: 前置校验 ───────────────────────────────────────────────
        ok, reason = self.validate(tool_id, params, market)
        if not ok:
            self._metrics.record_invalid(tool_id, reason)
            return ToolResult(status="invalid", reason=reason, tool_id=tool_id)

        # ── L2: 查共享缓存 ─────────────────────────────────────────────
        ckey = make_cache_key(tool_id, params)
        cached = self._cache.get(ckey)
        if cached is not None:
            self._metrics.record(tool_id, status="cached", from_cache=True)
            return ToolResult(status="cached", data=cached, tool_id=tool_id,
                              cache_key=ckey, from_cache=True)

        # ── 执行: 注册 callable 优先, 否则外部 executor ────────────────
        result = await self._dispatch(tool_id, params)
        if result is None:
            return ToolResult(status="failed", reason=f"无可用执行器: {tool_id}",
                              tool_id=tool_id, cache_key=ckey)

        # ── 结果有效性校验 (§4.6.3: 空/garbage 拦截) ───────────────────
        if not is_valid_result(result.data if isinstance(result, ToolResult) else result):
            # 尝试 fallback chain
            fb_result = await self._try_fallback(tool_id, params, market, data_type)
            if fb_result is not None:
                return fb_result
            self._metrics.record(tool_id, status="failed")
            return ToolResult(status="failed", reason="结果无效且无 fallback",
                              tool_id=tool_id, cache_key=ckey)

        # 归一化为 data
        data = result.data if isinstance(result, ToolResult) else result

        # ── L2: 写缓存 (按 data_type TTL) ──────────────────────────────
        if self._is_cacheable(tool_id):
            self._cache.set(ckey, data, data_type=data_type)

        self._metrics.record(tool_id, status="ok")
        return ToolResult(status="ok", data=data, tool_id=tool_id, cache_key=ckey)

    def _is_cacheable(self, tool_id: str) -> bool:
        """计算工具不缓存 (廉价且局部); 网络/查询工具缓存."""
        if self.is_computation_tool(tool_id):
            return False
        return True

    async def _dispatch(self, tool_id: str, params: dict):
        """执行单次工具调用: 注册 callable 优先, 否则外部 executor."""
        func = self._tools.get(tool_id)
        if func is not None:
            try:
                import inspect
                if inspect.iscoroutinefunction(func):
                    data = await func(params)
                else:
                    data = func(params)
                return data
            except Exception as e:
                logger.warning("[ToolRegistry] 执行失败 %s: %s", tool_id, e)
                return None
        # 外部 executor (expert_tools.ToolExecutor 分发的工具)
        if self._external_executor is not None:
            try:
                import inspect
                if inspect.iscoroutinefunction(self._external_executor):
                    data = await self._external_executor(tool_id, params)
                else:
                    data = self._external_executor(tool_id, params)
                return data
            except Exception as e:
                logger.warning("[ToolRegistry] 外部执行失败 %s: %s", tool_id, e)
                return None
        return None

    async def _try_fallback(self, tool_id: str, params: dict, market: str,
                            data_type: str):
        """按 fallback chain 降级到候选工具 (§4.6.1 fallback)."""
        from ...schemas.contracts import ToolResult

        if not data_type:
            return None
        candidates = self.CAPABILITY_MATRIX.get(data_type, [])
        for tid, prio in candidates:
            if tid == tool_id:
                continue
            ok, _ = self.validate(tid, params, market)
            if not ok:
                continue
            data = await self._dispatch(tid, params)
            if data is not None and is_valid_result(
                    data.data if isinstance(data, ToolResult) else data):
                real = data.data if isinstance(data, ToolResult) else data
                ckey = make_cache_key(tid, params)
                if self._is_cacheable(tid):
                    self._cache.set(ckey, real, data_type=data_type)
                self._metrics.record(tid, status="degraded")
                logger.info("[ToolRegistry] fallback %s → %s 成功", tool_id, tid)
                return ToolResult(status="degraded", data=real, tool_id=tid,
                                  reason=f"fallback from {tool_id}", cache_key=ckey)
        return None

    # ── 诊断 ──────────────────────────────────────────────────────────
    def metrics_summary(self) -> dict:
        """返回工具利用率报告 (含缓存全局统计)."""
        return self._metrics.merge_cache_stats(self._cache.snapshot())

    def clear_cache(self) -> None:
        """清空共享缓存 (新分析任务开始时调用)."""
        self._cache.clear()
        self._metrics.reset()


# ── 进程级单例 (保持原导出名, 向后兼容) ────────────────────────────────────
tool_registry = ToolRegistry()

# 启动时把能力矩阵反查表建好
for _dt, _pairs in ToolRegistry.CAPABILITY_MATRIX.items():
    for _tid, _ in _pairs:
        ToolRegistry._TOOL_DATA_TYPE[_tid] = _dt
        tool_metrics.register_tool(_tid)
