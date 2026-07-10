"""Trace — 全链路可观测性 (§10.3 #4 P2, ★ 剩余优化项).

开发指南 §10.3 #4:
  "当前有 failure_capture, 可加全链路 trace (每个 handoff/tool 调用)"

设计 (span 模型, 类似 OpenTelemetry):
  - 一次分析任务一个 trace_id, 多个 span 组成调用树.
  - Span kind: agent_run / handoff / tool_call / subagent / reflection / decision / report
  - 每个 span: span_id / parent_id / name / kind / start / end / duration / status / attributes
  - 复用现有 metrics (record 耗时) + audit (log 关键事件).

用法:
  tracer = Tracer()
  with tracer.span("agent_run", kind="agent", parent_id=ctx.root_id) as span:
      span.set("role", "Technical Analyst")
      ...  # 业务逻辑
      span.set("status", "ok")
  # span 自动 end + record 耗时
  summary = tracer.summary()  # 调用树 + 耗时统计
"""

from __future__ import annotations

import os
import time
import uuid
import logging
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """单个调用 span (调用树节点)."""
    span_id: str
    trace_id: str
    parent_id: Optional[str] = None
    name: str = ""
    kind: str = "generic"       # agent_run/handoff/tool_call/subagent/reflection/decision/report
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    status: str = "ok"          # ok/degraded/failed/skipped
    attributes: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def event(self, name: str, **attrs) -> None:
        self.events.append({"name": name, "time": time.time(), **attrs})

    @property
    def ended(self) -> bool:
        return self.end_time > 0


class Tracer:
    """全链路 trace 管理器.

    一次分析任务一个 Tracer 实例 (或用 new_trace() 开新 trace).
    """

    def __init__(self, trace_id: Optional[str] = None, *,
                 metrics_collector=None, audit_logger=None):
        self.trace_id = trace_id or uuid.uuid4().hex[:16]
        self._spans: list[Span] = []
        self._metrics = metrics_collector  # 可注入 observability.metrics
        self._audit = audit_logger          # 可注入 observability.audit
        # root span (一次分析的根)
        self.root_id: Optional[str] = None

    def start_span(self, name: str, kind: str = "generic",
                   parent_id: Optional[str] = None) -> Span:
        """开启一个 span (需手动 end_span, 或用 span() contextmanager)."""
        span = Span(
            span_id=uuid.uuid4().hex[:12],
            trace_id=self.trace_id,
            parent_id=parent_id or self.root_id,
            name=name, kind=kind,
            start_time=time.time(),
        )
        if self.root_id is None and kind in ("agent", "agent_run", "root"):
            self.root_id = span.span_id
        self._spans.append(span)
        return span

    def end_span(self, span: Span, status: str = "ok") -> Span:
        """结束 span + 记录耗时."""
        if span.ended:
            return span
        span.end_time = time.time()
        span.duration_ms = round((span.end_time - span.start_time) * 1000, 2)
        span.status = status
        # 对接 metrics (record 耗时)
        if self._metrics is not None:
            try:
                self._metrics.record(f"span.{span.kind}.duration", span.duration_ms,
                                     {"status": status, "name": span.name})
            except Exception:
                pass
        # 对接 audit (关键事件)
        if self._audit is not None and status in ("failed", "degraded"):
            try:
                self._audit.log("trace_span", span.kind,
                                {"name": span.name, "status": status, "ms": span.duration_ms})
            except Exception:
                pass
        return span

    @contextmanager
    def span(self, name: str, kind: str = "generic",
             parent_id: Optional[str] = None, status: str = "ok"):
        """contextmanager: 自动 end_span."""
        sp = self.start_span(name, kind, parent_id)
        try:
            yield sp
            self.end_span(sp, sp.status or status)
        except Exception as e:
            sp.event("exception", error=str(e))
            self.end_span(sp, "failed")
            raise

    def record_event(self, span: Span, name: str, **attrs) -> None:
        """在 span 上记录事件 (不结束 span)."""
        span.event(name, **attrs)

    # ── 查询 ──────────────────────────────────────────────────────────

    def spans(self) -> list[Span]:
        return list(self._spans)

    def by_kind(self, kind: str) -> list[Span]:
        return [s for s in self._spans if s.kind == kind]

    def summary(self) -> dict:
        """调用树 + 耗时统计."""
        total_ms = sum(s.duration_ms for s in self._spans if s.ended)
        by_kind: dict[str, dict] = {}
        for s in self._spans:
            d = by_kind.setdefault(s.kind, {"count": 0, "total_ms": 0.0,
                                            "ok": 0, "failed": 0, "degraded": 0})
            d["count"] += 1
            d["total_ms"] += s.duration_ms
            if s.status in d:
                d[s.status] += 1
        return {
            "trace_id": self.trace_id,
            "span_count": len(self._spans),
            "total_duration_ms": round(total_ms, 2),
            "by_kind": {k: {**v, "total_ms": round(v["total_ms"], 2)} for k, v in by_kind.items()},
            "failed_spans": [s.name for s in self._spans if s.status == "failed"],
        }

    def tree(self) -> dict:
        """返回 span 树 (parent → children)."""
        nodes = {s.span_id: {"span": s, "children": []} for s in self._spans}
        roots = []
        for s in self._spans:
            if s.parent_id and s.parent_id in nodes:
                nodes[s.parent_id]["children"].append(s.span_id)
            else:
                roots.append(s.span_id)

        def _build(sid):
            n = nodes[sid]
            return {
                "name": n["span"].name, "kind": n["span"].kind,
                "status": n["span"].status, "ms": n["span"].duration_ms,
                "children": [_build(c) for c in n["children"]],
            }
        return {"trace_id": self.trace_id, "roots": [_build(r) for r in roots]}


# 进程级默认 (单 trace 场景; 多任务各自 new Tracer)
tracer = Tracer()
