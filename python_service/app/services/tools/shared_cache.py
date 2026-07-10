"""跨 Agent 共享工具缓存 (Phase 1, §4.6.2 L2 层).

开发指南 §4.6.2 三层调用治理:
  L1 预取层 — Planner 预取写入 snapshot, Agent 优先读
  L2 缓存层 — 跨 Agent 共享缓存, cache_key=(tool_id, sorted(params))  ← 本模块
  L3 校验层 — 前置条件校验 (preconditions.py)

本模块把 Phase 0 的「会话级去重缓存」升级为「跨 Agent 共享缓存」:
  - 进程级单例, 同一分析任务内所有 Agent 共享.
  - 按 data_type 分 TTL (行情 30s / 财务 3600s / 新闻 300s), 避免过期数据.
  - 线程安全 (asyncio 场景下也安全, 因为不 await).
  - 提供 snapshot() 供 metrics 监控缓存命中率.

与现有代码衔接:
  - 复用 expert_tools.ToolExecutor._dedup_key 的归一化思路 (tool + sorted params).
  - 升级后 ToolRegistry.execute 优先查本缓存, 命中直接返回 (status="cached").
  - 现有 ToolExecutor._result_cache / _financial_cache 可逐步迁移到本缓存.
"""

from __future__ import annotations

import os
import time
import threading
from typing import Any, Optional


# ── TTL 配置 (开发指南 §7.6) ──────────────────────────────────────────────
# 按 data_type 分 TTL: 行情数据秒级过期, 财务数据小时级, 新闻分钟级.
_DEFAULT_TTLS = {
    "realtime_quote": 30,      # TOOL_CACHE_TTL_QUOTE
    "history_kline": 120,      # K 线 2 分钟 (日内不频繁变)
    "financial_stmt": 3600,    # TOOL_CACHE_TTL_FINANCIAL
    "news": 300,               # TOOL_CACHE_TTL_NEWS
    "announcement": 300,
    "industry_data": 600,
    "macro_indicator": 1800,
    "deep_content": 60,        # 抓取内容, 短 TTL
}
_DEFAULT_TTL = 300  # 未识别 data_type 的兜底 TTL (秒)


def _ttl_for(data_type: str) -> int:
    """从环境变量或默认表取 TTL."""
    env_map = {
        "realtime_quote": "TOOL_CACHE_TTL_QUOTE",
        "financial_stmt": "TOOL_CACHE_TTL_FINANCIAL",
        "news": "TOOL_CACHE_TTL_NEWS",
    }
    if data_type in env_map:
        try:
            return int(os.getenv(env_map[data_type], _DEFAULT_TTLS[data_type]))
        except (ValueError, TypeError):
            return _DEFAULT_TTLS[data_type]
    return _DEFAULT_TTLS.get(data_type, _DEFAULT_TTL)


def make_cache_key(tool_id: str, params: dict) -> str:
    """规范化缓存键: (tool_id, sorted(params)).

    与 expert_tools.ToolExecutor._dedup_key 思路一致:
    tool + 关键参数归一化 (strip + lower + 空格折叠), 使平凡差异的查询合并.
    """
    import re
    parts = [tool_id]
    # 按 key 排序保证参数顺序不影响命中
    for k in sorted(params.keys()):
        v = params[k]
        if v is None:
            continue
        s = str(v).strip().lower()
        s = re.sub(r"\s+", " ", s)
        if s:
            parts.append(f"{k}={s}")
    return "|".join(parts)


class _CacheEntry:
    __slots__ = ("data", "expire_at", "tool_id")

    def __init__(self, data: Any, ttl: int, tool_id: str):
        self.data = data
        self.expire_at = time.monotonic() + ttl
        self.tool_id = tool_id

    @property
    def expired(self) -> bool:
        return time.monotonic() > self.expire_at


class SharedToolCache:
    """跨 Agent 共享工具缓存.

    线程安全 (threading.Lock). 进程级单例 `shared_tool_cache`.
    每个 Agent 调用 ToolRegistry.execute 时共享同一份缓存, 消除跨 Agent 重复调用.
    """

    def __init__(self, max_entries: int = 2000):
        self._store: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._max = max_entries
        # 统计 (供 metrics 读取)
        self.hits = 0
        self.misses = 0
        self.sets = 0

    def get(self, cache_key: str) -> Optional[Any]:
        """查缓存. 返回 data 或 None (未命中/过期)."""
        with self._lock:
            entry = self._store.get(cache_key)
            if entry is None:
                self.misses += 1
                return None
            if entry.expired:
                # 惰性过期清理
                del self._store[cache_key]
                self.misses += 1
                return None
            self.hits += 1
            return entry.data

    def set(self, cache_key: str, data: Any, data_type: str = "", ttl: Optional[int] = None) -> None:
        """写缓存. ttl 由 data_type 决定, 可显式覆盖."""
        if ttl is None:
            ttl = _ttl_for(data_type) if data_type else _DEFAULT_TTL
        with self._lock:
            # 容量上限: 简单 LRU 驱逐 (随机删 10% 最旧条目)
            if len(self._store) >= self._max:
                self._evict()
            self._store[cache_key] = _CacheEntry(data, ttl, cache_key.split("|", 1)[0])
            self.sets += 1

    def invalidate(self, cache_key: str) -> bool:
        """显式失效单条缓存."""
        with self._lock:
            return self._store.pop(cache_key, None) is not None

    def invalidate_prefix(self, tool_id: str) -> int:
        """失效某工具的所有缓存 (如数据源切换)."""
        prefix = f"{tool_id}|"
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    def clear(self) -> None:
        """清空全部缓存 (新分析任务开始时调用)."""
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
            self.sets = 0

    def _evict(self) -> None:
        """容量超限时驱逐最旧条目."""
        if not self._store:
            return
        # 按 expire_at 升序, 删前 10%
        sorted_items = sorted(self._store.items(), key=lambda kv: kv[1].expire_at)
        n = max(1, len(sorted_items) // 10)
        for k, _ in sorted_items[:n]:
            del self._store[k]

    def snapshot(self) -> dict:
        """返回缓存统计快照 (供 metrics 合并)."""
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 4) if total else 0.0,
                "sets": self.sets,
            }


# 进程级单例: 同一分析任务内所有 Agent 共享
shared_tool_cache = SharedToolCache()
