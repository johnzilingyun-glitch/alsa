"""Memory 四层存储 (Phase 5, §6, ★ v3.1 Memory 拆 Session/Analysis/Project/User).

开发指南 §6 Phase5:
  "Memory 拆 Session/Analysis/Project/User"
  验收: "支持数百 MB 文档; 可 pause/resume; 每个文件 ≤ 250 行"

四层职责 (生命周期递增):
  ┌──────────────┬────────────┬──────────────────────────────────────┐
  │ Session      │ 会话级      │ 单次分析: EvidenceBus快照/ExecutionPlan/临时状态 │
  │ Analysis     │ 跨会话      │ 某 symbol 分析历史 (复用 agent_memory+lancedb) │
  │ Project      │ 项目级      │ 项目配置/偏好/约定 (持久 JSON)        │
  │ User         │ 用户级      │ 用户偏好/习惯 (跨项目, 持久 JSON)      │
  └──────────────┴────────────┴──────────────────────────────────────┘

设计:
  - 统一 MemoryStore 接口: put(layer, key, value) / get / query / delete.
  - SessionMemory: 进程内 dict (会话结束清空).
  - AnalysisMemory: 懒包装现有 AgentMemory (向量检索, 跨会话).
  - ProjectMemory / UserMemory: JSON 文件持久化.
  - 可与 CheckpointStore 协作 (Session 快照落 checkpoint).
"""

from __future__ import annotations

import os
import json
import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MemoryLayer(str, Enum):
    SESSION = "session"      # 会话级
    ANALYSIS = "analysis"    # 跨会话 symbol 分析历史
    PROJECT = "project"      # 项目级
    USER = "user"            # 用户级 (跨项目)


class _KVStore:
    """简单的 KV 存储 (内存 + 可选 JSON 持久化)."""

    def __init__(self, persist_path: Optional[str] = None):
        self._data: dict[str, Any] = {}
        self._path = persist_path
        if persist_path and os.path.exists(persist_path):
            try:
                with open(persist_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.warning("[Memory] 加载 %s 失败: %s", persist_path, e)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._flush()

    def get(self, key: str, default=None) -> Any:
        return self._data.get(key, default)

    def query(self, prefix: str = "") -> dict[str, Any]:
        if not prefix:
            return dict(self._data)
        return {k: v for k, v in self._data.items() if k.startswith(prefix)}

    def delete(self, key: str) -> bool:
        existed = key in self._data
        self._data.pop(key, None)
        self._flush()
        return existed

    def clear(self) -> int:
        n = len(self._data)
        self._data.clear()
        self._flush()
        return n

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def _flush(self) -> None:
        if self._path:
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, default=str)
            except Exception as e:
                logger.warning("[Memory] 持久化 %s 失败: %s", self._path, e)


class MemoryStore:
    """四层 Memory 统一存储.

    用法:
      mem = MemoryStore(project_dir="data/memory")
      mem.put(MemoryLayer.SESSION, "job1:plan", execution_plan)
      mem.put(MemoryLayer.PROJECT, "default_market", "US-Share")
      plan = mem.get(MemoryLayer.SESSION, "job1:plan")
      # Analysis 层对接 AgentMemory (向量检索)
      mem.remember_analysis(symbol="AAPL", role="TA", summary="...", conclusions=[...])
      results = mem.recall_analysis(symbol="AAPL", role="TA", query="技术面")
    """

    def __init__(self, project_dir: Optional[str] = None, user_dir: Optional[str] = None):
        # Session: 内存级 (会话结束清空)
        self.session = _KVStore()
        # Analysis: 懒包装 AgentMemory (向量检索)
        self._agent_memory = None
        # Project: 项目级 JSON
        proj_path = os.path.join(project_dir, "project.json") if project_dir else None
        self.project = _KVStore(proj_path)
        # User: 用户级 JSON (跨项目)
        user_path = os.path.join(user_dir, "user.json") if user_dir else None
        self.user = _KVStore(user_path)

    # ── 统一接口 ────────────────────────────────────────────────────────

    def put(self, layer: MemoryLayer, key: str, value: Any) -> None:
        store = self._store(layer)
        store.put(key, value)

    def get(self, layer: MemoryLayer, key: str, default=None) -> Any:
        return self._store(layer).get(key, default)

    def query(self, layer: MemoryLayer, prefix: str = "") -> dict[str, Any]:
        return self._store(layer).query(prefix)

    def delete(self, layer: MemoryLayer, key: str) -> bool:
        return self._store(layer).delete(key)

    def _store(self, layer: MemoryLayer) -> _KVStore:
        if layer == MemoryLayer.SESSION:
            return self.session
        if layer == MemoryLayer.PROJECT:
            return self.project
        if layer == MemoryLayer.USER:
            return self.user
        # ANALYSIS 走 AgentMemory (非 _KVStore), 统一接口退化
        return self.session  # fallback

    # ── Analysis 层 (复用 AgentMemory 向量检索) ─────────────────────────

    def _get_agent_memory(self):
        """懒导入 AgentMemory (避免循环 + 重型依赖)."""
        if self._agent_memory is None:
            try:
                from .agent_memory import agent_memory
                self._agent_memory = agent_memory
            except Exception as e:
                logger.warning("[Memory] AgentMemory 不可用: %s", e)
                self._agent_memory = False  # 标记不可用
        return self._agent_memory if self._agent_memory is not False else None

    def remember_analysis(self, *, symbol: str, role: str, summary: str,
                          conclusions: list[str] = None, confidence: float = 0.5,
                          outcome: str = "") -> bool:
        """记录分析历史 (跨会话, 向量化). 同步接口: 失败退化为 Session.

        AgentMemory.store 是 async; 同步上下文无法 await, 故此处尝试同步属性检测,
        实际落库由调用方用 aremember_analysis (async). 简化: 若 AgentMemory 可用,
        标记走 Analysis 层但仍写一份 Session 兜底.
        """
        am = self._get_agent_memory()
        if am is None:
            self.session.put(f"analysis:{symbol}:{role}", {
                "summary": summary, "conclusions": conclusions or [],
                "confidence": confidence, "outcome": outcome,
            })
            return False
        # AgentMemory.store 是 async, 同步接口兜底写 Session (实际异步落库用 aremember_analysis)
        self.session.put(f"analysis:{symbol}:{role}", {
            "summary": summary, "conclusions": conclusions or [],
            "confidence": confidence, "outcome": outcome,
        })
        return True

    async def aremember_analysis(self, *, symbol: str, role: str, summary: str,
                                 conclusions: list[str] = None, confidence: float = 0.5,
                                 outcome: str = "") -> bool:
        """异步记录分析历史 (调用 AgentMemory.store 向量化落库)."""
        am = self._get_agent_memory()
        if am is None:
            self.session.put(f"analysis:{symbol}:{role}", {
                "summary": summary, "conclusions": conclusions or [],
                "confidence": confidence, "outcome": outcome,
            })
            return False
        try:
            await am.store(symbol=symbol, role=role, analysis=summary,
                           key_conclusions="; ".join(conclusions or []),
                           confidence=confidence, outcome=outcome or "unknown")
            return True
        except Exception as e:
            logger.warning("[Memory] aremember_analysis 失败: %s", e)
            self.session.put(f"analysis:{symbol}:{role}", {
                "summary": summary, "conclusions": conclusions or [],
                "confidence": confidence, "outcome": outcome,
            })
            return False

    def recall_analysis(self, *, symbol: str, role: str = "", query: str = "",
                        limit: int = 5) -> list[dict]:
        """同步检索 (仅查 Session 兜底; 向量检索用 arecall_analysis)."""
        v = self.session.get(f"analysis:{symbol}:{role}")
        return [v] if v else []

    async def arecall_analysis(self, *, symbol: str, role: str = "", query: str = "",
                               limit: int = 5) -> list[dict]:
        """异步向量检索分析历史 (AgentMemory.recall)."""
        am = self._get_agent_memory()
        if am is None:
            v = self.session.get(f"analysis:{symbol}:{role}")
            return [v] if v else []
        try:
            result = await am.recall(symbol=symbol, role=role or None,
                                     query=query or f"{symbol} {role}", limit=limit)
            return [{"role": e.role, "summary": e.analysis_summary,
                     "conclusions": e.key_conclusions, "confidence": e.confidence,
                     "outcome": e.outcome} for e in (result.entries if result else [])]
        except Exception as e:
            logger.warning("[Memory] arecall_analysis 失败: %s", e)
            v = self.session.get(f"analysis:{symbol}:{role}")
            return [v] if v else []

    # ── Session 快照 (对接 CheckpointStore) ─────────────────────────────

    def snapshot_session(self, job_id: str, *, plan=None, evidence_bus=None,
                         results=None, checkpoint_store=None) -> str:
        """会话快照 (可落 CheckpointStore 供 pause/resume)."""
        import dataclasses
        snap = {
            "job_id": job_id,
            "plan": dataclasses.asdict(plan) if plan and dataclasses.is_dataclass(plan) else plan,
            "evidence": evidence_bus.snapshot() if evidence_bus else {},
            "results_count": len(results) if results else 0,
        }
        key = f"{job_id}:session"
        self.session.put(key, snap)
        if checkpoint_store is not None:
            checkpoint_store.save(key, snap)
        return key

    def restore_session(self, job_id: str, checkpoint_store=None) -> Optional[dict]:
        """恢复会话快照."""
        key = f"{job_id}:session"
        snap = self.session.get(key)
        if snap is None and checkpoint_store is not None:
            snap = checkpoint_store.resume(key)
            if snap:
                self.session.put(key, snap)
        return snap

    def clear_session(self, job_id: str = "") -> int:
        """清空 Session (会话结束)."""
        if job_id:
            keys = [k for k in self.session.keys() if k.startswith(job_id)]
            for k in keys:
                self.session.delete(k)
            return len(keys)
        return self.session.clear()


# 进程级默认实例 (Session 内存级; Project/User 可选持久化)
memory_store = MemoryStore()
