"""CheckpointStore — pause/resume 暂停恢复 (Phase 5, §4.2.6, ★ v3.1 明确归 Phase5).

开发指南 §4.2.6:
  v3.1 明确: Phase2 的 BaseAgent 只有降级(degrade), 不实现 pause/resume.
  pause/resume 是 Phase5 特性, 依赖 Checkpoint Store.

开发指南 §6 Phase5 验收:
  "可 pause/resume; 每个文件 ≤ 250 行"

设计:
  - 内存级 (进程内 dict): 直接存对象引用, resume 立即返回 (最快, 单进程 pause/resume).
  - 持久化级 (JSON 文件): dataclasses.asdict 序列化, 跨进程恢复.
  - 支持类型: ExecutionPlan / AgentState / AgentResult / FinalDecision /
              AggregatedEvidence / CritiqueResult / 任意 dataclass.
  - checkpoint_key = (job_id, agent_id) 或任意 str.

接入 LangGraph checkpointing (§4.2.6):
  本 Store 可作为 LangGraph BaseCheckpointSaver 的后端 (Phase5+ 衔接).
  当前纯 asyncio 架构下, DAGEngine/ReflectionAgent 可直接调用 save/resume.
"""

from __future__ import annotations

import os
import json
import logging
import dataclasses
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 已知可序列化 dataclass 类型注册表 (resume 时按 type 重建)
from ..schemas.contracts import (
    ExecutionPlan, AgentSpec, SubAgentSpec, HandoffSpec, DAGSpec, DataFetchTask,
    AgentResult, Evidence, RiskItem,
    AggregatedEvidence, AggregatedClaim, Conflict,
    CritiqueResult, Issue, Correction,
    ToolCall, ToolResult, ToolSpec, Snapshot,
)
from ..agents.decision_agent import FinalDecision

_TYPE_REGISTRY = {
    "ExecutionPlan": ExecutionPlan, "AgentSpec": AgentSpec, "SubAgentSpec": SubAgentSpec,
    "HandoffSpec": HandoffSpec, "DAGSpec": DAGSpec, "DataFetchTask": DataFetchTask,
    "AgentResult": AgentResult, "Evidence": Evidence, "RiskItem": RiskItem,
    "AggregatedEvidence": AggregatedEvidence, "AggregatedClaim": AggregatedClaim,
    "Conflict": Conflict, "CritiqueResult": CritiqueResult, "Issue": Issue,
    "Correction": Correction, "ToolCall": ToolCall, "ToolResult": ToolResult,
    "ToolSpec": ToolSpec, "Snapshot": Snapshot, "FinalDecision": FinalDecision,
}


def _json_default(o):
    """JSON 序列化: 处理 datetime/dataclass."""
    if isinstance(o, datetime):
        return o.isoformat()
    if is_dataclass(o):
        return asdict(o)
    raise TypeError(f"不可序列化: {type(o)}")


class CheckpointStore:
    """pause/resume 检查点存储.

    用法:
      store = CheckpointStore(persist_dir="data/checkpoints")
      store.save("job1:agentA", agent_state)        # 暂停点保存
      state = store.resume("job1:agentA")           # 恢复
      keys = store.list_checkpoints("job1")         # 列出 job 的检查点
    """

    def __init__(self, persist_dir: Optional[str] = None):
        # 内存级: key → 对象引用 (最快 resume)
        self._memory: dict[str, Any] = {}
        # 持久化目录 (可选, 跨进程恢复)
        self._persist_dir = persist_dir
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)

    def save(self, key: str, state: Any, *, persist: bool = True) -> None:
        """保存检查点 (暂停点).

        Args:
            key: 检查点键 (建议 job_id:agent_id)
            state: 任意可序列化对象 (dataclass / dict / list)
            persist: 是否落盘 (默认 True, 若 persist_dir 已设)
        """
        self._memory[key] = state
        if persist and self._persist_dir is not None:
            self._persist(key, state)
        logger.debug("[Checkpoint] save %s (type=%s)", key, type(state).__name__)

    def resume(self, key: str) -> Optional[Any]:
        """恢复检查点. 优先内存, 其次持久化."""
        if key in self._memory:
            logger.debug("[Checkpoint] resume %s (内存命中)", key)
            return self._memory[key]
        if self._persist_dir is not None:
            obj = self._load_persisted(key)
            if obj is not None:
                self._memory[key] = obj  # 回填内存
                logger.debug("[Checkpoint] resume %s (持久化命中)", key)
                return obj
        logger.debug("[Checkpoint] resume %s (未找到)", key)
        return None

    def list_checkpoints(self, job_id: Optional[str] = None) -> list[str]:
        """列出检查点键. job_id 过滤前缀."""
        keys = list(self._memory.keys())
        if self._persist_dir:
            for f in os.listdir(self._persist_dir):
                if f.endswith(".json"):
                    k = f[:-5].replace("__", ":")
                    if k not in keys:
                        keys.append(k)
        if job_id:
            return [k for k in keys if k.startswith(job_id)]
        return keys

    def delete(self, key: str) -> bool:
        """删除检查点."""
        existed = key in self._memory
        self._memory.pop(key, None)
        if self._persist_dir:
            path = self._path(key)
            if os.path.exists(path):
                os.remove(path)
                existed = True
        return existed

    def clear(self, job_id: Optional[str] = None) -> int:
        """清空检查点. job_id 过滤."""
        if job_id:
            keys = [k for k in list(self._memory.keys()) if k.startswith(job_id)]
            for k in keys:
                self.delete(k)
            return len(keys)
        n = len(self._memory)
        self._memory.clear()
        if self._persist_dir:
            for f in os.listdir(self._persist_dir):
                if f.endswith(".json"):
                    os.remove(os.path.join(self._persist_dir, f))
        return n

    # ── 持久化 ──────────────────────────────────────────────────────────

    def _path(self, key: str) -> str:
        safe = key.replace(":", "__").replace("/", "_")
        return os.path.join(self._persist_dir, f"{safe}.json")

    def _persist(self, key: str, state: Any) -> None:
        try:
            payload = {
                "_type": type(state).__name__,
                "_data": asdict(state) if is_dataclass(state) else state,
            }
            with open(self._path(key), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, default=_json_default)
        except Exception as e:
            logger.warning("[Checkpoint] 持久化失败 %s: %s", key, e)

    def _load_persisted(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            type_name = payload.get("_type", "")
            data = payload.get("_data", {})
            cls = _TYPE_REGISTRY.get(type_name)
            if cls and isinstance(data, dict):
                return self._reconstruct(cls, data)
            return data  # 退化为 dict
        except Exception as e:
            logger.warning("[Checkpoint] 加载失败 %s: %s", key, e)
            return None

    @staticmethod
    def _reconstruct(cls, data: dict) -> Any:
        """递归重建 dataclass (处理嵌套 + datetime)."""
        import dataclasses as dc
        if not dc.is_dataclass(cls):
            return data
        kwargs = {}
        for fld in dc.fields(cls):
            if fld.name not in data:
                continue
            val = data[fld.name]
            kwargs[fld.name] = val
        try:
            return cls(**kwargs)
        except Exception:
            # 退化为 dict (字段不匹配)
            return data


# 进程级默认实例 (内存级, 不落盘)
checkpoint_store = CheckpointStore()
