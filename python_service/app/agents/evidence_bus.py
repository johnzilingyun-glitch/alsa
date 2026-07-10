"""EvidenceBus — 异步证据发布/订阅 (Phase 2, §4.2).

开发指南 §4.2.3 与 history_states 的区别:
  EvidenceBus = 异步证据发布/订阅 (Agent 完成后发布, 其他 Agent 可读)
               → 适合「独立并行」的 Agent 共享结论
  Handoff     = 同步委托调用 (Agent A 执行中请求 Agent B 验证某 claim)
               → 适合「有依赖」的 Agent 协作 (见 handoff.py)

替换 Phase 0 的 history_states dict:
  - history_states: 只读上一轮全文, 无结构化, 无 stance 维度
  - EvidenceBus:    结构化 Evidence(claim/stance/confidence/source), 按 role 索引

v3.1 修复落地: Evidence 带 stance(bullish/bearish/neutral), 按 stance 维度聚合.

设计: 进程内单次分析任务级 (一个 analysis job 一个 EvidenceBus 实例).
线程安全. 不持久化 (持久化归 Phase 5 Memory).
"""

from __future__ import annotations

import threading
from typing import Optional

from ..schemas.contracts import Evidence


class EvidenceBus:
    """证据发布/订阅总线.

    用法:
      bus = EvidenceBus()
      # Agent 完成后发布
      bus.publish("Technical Analyst", [Evidence(claim="...", stance="bullish")])
      # 其他 Agent 读取相关证据
      evs = bus.relevant("Fundamental Analyst")   # 读全部 (或按 role 过滤)
      evs = bus.by_role("Technical Analyst")      # 读指定 role
    """

    def __init__(self):
        self._lock = threading.Lock()
        # role -> list[Evidence]
        self._store: dict[str, list[Evidence]] = {}
        # 发布顺序记录 (供 reflection 回溯)
        self._timeline: list[tuple[str, Evidence]] = []

    def publish(self, role: str, evidence: list[Evidence]) -> None:
        """Agent 完成后发布证据. 累加到该 role 的证据列表."""
        if not evidence:
            return
        with self._lock:
            bucket = self._store.setdefault(role, [])
            for e in evidence:
                bucket.append(e)
                self._timeline.append((role, e))

    def by_role(self, role: str) -> list[Evidence]:
        """读取指定 role 发布的全部证据."""
        with self._lock:
            return list(self._store.get(role, []))

    def relevant(self, consumer_role: str, *, exclude_self: bool = True) -> list[Evidence]:
        """读取与某 Agent 相关的证据 (默认排除自己发布的).

        独立并行的 Agent 用此方法共享其他 Agent 的结论.
        """
        with self._lock:
            out: list[Evidence] = []
            for role, evs in self._store.items():
                if exclude_self and role == consumer_role:
                    continue
                out.extend(evs)
            return out

    def all_evidence(self) -> list[Evidence]:
        """读取全部证据 (Evidence Aggregator 用)."""
        with self._lock:
            return [e for evs in self._store.values() for e in evs]

    def roles_published(self) -> list[str]:
        """已发布证据的 role 列表."""
        with self._lock:
            return list(self._store.keys())

    def snapshot(self) -> dict:
        """返回统计快照 (供 observability)."""
        with self._lock:
            return {
                "roles": list(self._store.keys()),
                "total_evidence": sum(len(v) for v in self._store.values()),
                "by_role": {r: len(v) for r, v in self._store.items()},
            }

    def stance_summary(self) -> dict[str, dict[str, int]]:
        """按 role 统计 stance 分布 (供 Reflection 判冲突)."""
        with self._lock:
            out: dict[str, dict[str, int]] = {}
            for role, evs in self._store.items():
                counts = {"bullish": 0, "bearish": 0, "neutral": 0}
                for e in evs:
                    counts[e.stance] = counts.get(e.stance, 0) + 1
                out[role] = counts
            return out

    def clear(self) -> None:
        """清空 (新分析任务开始时调用)."""
        with self._lock:
            self._store.clear()
            self._timeline.clear()


# 进程级默认实例 (单任务场景). 多任务场景各自 new EvidenceBus().
evidence_bus = EvidenceBus()
