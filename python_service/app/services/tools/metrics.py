"""工具利用率监控 (Phase 1, §4.6.4).

开发指南 §4.6.4:
  监控每个工具的调用率/命中率/失败率, 发现"从不调用"的工具.

指标:
  - call_count:    每个工具被调用次数
  - cache_hit:     缓存命中次数
  - cache_hit_rate: 缓存命中率 (过高 = 可能过度调用同一数据)
  - failure_rate:  失败率
  - never_called:  从未被调用的工具 (发现能力浪费)

设计: 线程安全计数器, 进程级单例. 与 SharedToolCache 协作:
  ToolRegistry.execute 每次调用都 record, 缓存命中也 record (区分 cache_hit).
"""

from __future__ import annotations

import threading
from typing import Optional


class ToolMetrics:
    """工具利用率监控计数器."""

    def __init__(self):
        self._lock = threading.Lock()
        # tool_id -> 指标
        self._stats: dict[str, dict] = {}
        # 已注册的全部工具名 (用于发现 never_called)
        self._known_tools: set[str] = set()

    def register_tool(self, tool_id: str) -> None:
        """登记已知工具 (用于 never_called 检测)."""
        with self._lock:
            self._known_tools.add(tool_id)
            self._stats.setdefault(tool_id, self._blank())

    def record(
        self,
        tool_id: str,
        *,
        status: str = "ok",
        from_cache: bool = False,
    ) -> None:
        """记录一次工具调用结果.

        status ∈ {ok, cached, invalid, failed, degraded}.
        from_cache=True 时计 cache_hit.
        """
        with self._lock:
            s = self._stats.setdefault(tool_id, self._blank())
            s["call_count"] += 1
            if from_cache or status == "cached":
                s["cache_hit"] += 1
            if status in ("failed", "invalid"):
                s["failure"] += 1
            elif status == "degraded":
                s["degraded"] += 1

    def record_invalid(self, tool_id: str, reason: str = "") -> None:
        """记录一次被前置校验拦截的无效调用."""
        with self._lock:
            s = self._stats.setdefault(tool_id, self._blank())
            s["call_count"] += 1
            s["invalid"] += 1

    @staticmethod
    def _blank() -> dict:
        return {
            "call_count": 0,
            "cache_hit": 0,
            "failure": 0,
            "degraded": 0,
            "invalid": 0,
        }

    def summary(self, registered_tools: Optional[set[str]] = None) -> dict:
        """返回利用率报告.

        Args:
            registered_tools: 已注册工具集合 (未传则用 register_tool 登记的).
                             用于检测 never_called.
        """
        known = registered_tools or self._known_tools
        with self._lock:
            stats = {k: dict(v) for k, v in self._stats.items()}

        # 补全已知但从未调用的工具
        for t in known:
            if t not in stats:
                stats[t] = self._blank()

        # 派生指标
        report = {}
        never_called = []
        over_called = []  # 缓存命中过高 (>=0.8 且调用 >=5 次)
        for tid, s in stats.items():
            calls = s["call_count"]
            hit = s["cache_hit"]
            fail = s["failure"]
            invalid = s["invalid"]
            hit_rate = round(hit / calls, 4) if calls else 0.0
            fail_rate = round((fail + invalid) / calls, 4) if calls else 0.0
            report[tid] = {
                "call_count": calls,
                "cache_hit": hit,
                "cache_hit_rate": hit_rate,
                "failure_rate": fail_rate,
                "invalid": invalid,
                "degraded": s["degraded"],
            }
            if calls == 0:
                never_called.append(tid)
            elif hit_rate >= 0.8 and calls >= 5:
                over_called.append(tid)

        return {
            "per_tool": report,
            "never_called": never_called,      # 能力浪费: 注册了但从不调用
            "over_called": over_called,        # 过度调用: 缓存命中过高
            "total_tools_registered": len(known),
            "total_tools_called": sum(1 for s in stats.values() if s["call_count"] > 0),
        }

    def reset(self) -> None:
        """清空统计 (新分析任务开始时调用)."""
        with self._lock:
            self._stats.clear()

    def merge_cache_stats(self, cache_snapshot: dict) -> dict:
        """合并 SharedToolCache.snapshot() 到报告 (全局缓存视角)."""
        rep = self.summary()
        rep["cache_global"] = cache_snapshot
        return rep


# 进程级单例
tool_metrics = ToolMetrics()
