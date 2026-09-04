"""Reviewer feedback → EvolveR bridge.

Professional Reviewer 在多智能体研讨中输出的结构化审计标记（如
``[🟡 Rf_STALE]``、``[🔴 WACC_BLACKBOX]``）此前只随 result_payload 落库，
从不回流进化机制。本模块在每个分析任务结果落库完成后，把这些标记解析成
结构化反馈，喂给 ``BrainManager.process_feedback(role="professional reviewer")``，
让 EvolveR（GEP 式 Prompt 进化）持续收到生产真实反馈。

设计要点：
- fire-and-forget：回流在 daemon 线程中执行，绝不阻塞/延迟主管线
  （process_feedback 内含同步 LLM 调用，可能耗时数十秒或因 402 欠费失败）。
- 整体 try/except：任何失败（解析、LLM 402、Qdrant 不可用）只记 warning。
- 节流在 BrainManager.process_feedback 内部按角色统一实施（见 brain_manager.py）。
"""

import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional

from .brain_manager import brain_manager

logger = logging.getLogger(__name__)

# Discussion 消息中 Professional Reviewer 的 role 标识（含命名变体，全小写）
REVIEWER_GENOME_ROLE = "professional reviewer"
_REVIEWER_MSG_ROLES = {"professional reviewer", "professional_reviewer"}

# 结构化标记形态：[🟢|🟡|🔴] MARKER_NAME。标记名以大写字母开头，
# 允许字母/数字/下划线（兼容 Rf_STALE 这类混合大小写标记；纯中文标记
# 如 "[🟡 信息遗漏]" 不在本正则覆盖范围内）。
# 标记名之后、`]` 之前的尾缀（如 "[🟡 Rf_STALE → 已修正]" 的 "→ 已修正"、
# "[🔴 FATAL: 数据口径错配]" 的 ": 数据口径错配"）不参与标记名提取。
REVIEWER_MARKER_RE = re.compile(r"\[(🟢|🟡|🔴)\s+([A-Z][A-Za-z0-9_]+)[^\]]*\]")

SEVERITY_BY_EMOJI = {"🔴": "critical", "🟡": "warning", "🟢": "ok"}

# 单条反馈中说明摘录的最大长度与标记数量上限（控制 mutate prompt 体积）
_SNIPPET_MAX_CHARS = 300
_MAX_MARKERS_PER_FEEDBACK = 30


def _message_text(msg: Dict[str, Any]) -> str:
    """Normalize a discussion message's content field to plain text."""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return str(content) if content is not None else ""


def parse_reviewer_markers(messages: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """Extract structured audit markers from Professional Reviewer messages.

    Returns a list of ``{"marker": str, "severity": str, "detail": str}``
    where severity is one of critical/warning/ok and detail is the excerpt
    after the marker up to the end of line or the next marker (whichever
    comes first).
    """
    markers: List[Dict[str, str]] = []
    for msg in messages or []:
        role = str(msg.get("role") or "").strip().lower()
        if role not in _REVIEWER_MSG_ROLES:
            continue
        content = _message_text(msg)
        if not content:
            continue

        for match in REVIEWER_MARKER_RE.finditer(content):
            emoji, name = match.group(1), match.group(2)
            next_match = REVIEWER_MARKER_RE.search(content, match.end())
            boundary = next_match.start() if next_match else len(content)
            snippet = content[match.end():boundary]
            # 说明摘录截至行尾（跨行内容属于正文而非该标记的说明）
            newline = snippet.find("\n")
            if newline != -1:
                snippet = snippet[:newline]
            snippet = snippet.strip().lstrip(":：-—| ").strip()
            if len(snippet) > _SNIPPET_MAX_CHARS:
                snippet = snippet[:_SNIPPET_MAX_CHARS] + "…"
            markers.append({
                "marker": name,
                "severity": SEVERITY_BY_EMOJI.get(emoji, "unknown"),
                "detail": snippet,
            })
    return markers


def build_reviewer_feedback(
    markers: List[Dict[str, str]],
    symbol: str,
    market: str,
    job_id: str,
    as_of: Optional[str] = None,
) -> Optional[str]:
    """Assemble the evolution feedback text from parsed audit markers."""
    if not markers:
        return None
    counts = {"critical": 0, "warning": 0, "ok": 0}
    for m in markers:
        counts[m["severity"]] = counts.get(m["severity"], 0) + 1

    lines = [
        "[EvolveR 反馈] Professional Reviewer 结构化评审结果回流",
        f"标的: {symbol} ({market}) | 任务: {job_id} | 日期: {as_of or 'N/A'}",
        (
            f"标记统计: critical={counts['critical']}, warning={counts['warning']}, "
            f"ok={counts['ok']}（共 {len(markers)} 个）"
        ),
        "标记清单:",
    ]
    for m in markers[:_MAX_MARKERS_PER_FEEDBACK]:
        detail = f" — {m['detail']}" if m["detail"] else ""
        lines.append(f"- [{m['severity'].upper()}] {m['marker']}{detail}")
    if len(markers) > _MAX_MARKERS_PER_FEEDBACK:
        lines.append(f"（其余 {len(markers) - _MAX_MARKERS_PER_FEEDBACK} 个标记略）")
    lines.append(
        "请基于以上评审发现改进 professional reviewer 的角色指令：强化对数据时效"
        "（Rf_STALE）、建模白箱化（WACC_BLACKBOX）、口径一致性等系统性问题的审查，"
        "并保持输出可被程序化解析的标准化标记格式。"
    )
    return "\n".join(lines)


def feed_reviewer_feedback_to_brain(
    job_id: str,
    symbol: str,
    market: str,
    discussion_messages: Optional[List[Dict[str, Any]]],
    as_of: Optional[str] = None,
) -> bool:
    """Parse reviewer markers and feed them into EvolveR (synchronous).

    Never raises: any failure is logged as a warning and False is returned so
    the analysis pipeline is never affected. Returns True when
    ``process_feedback`` was actually invoked.
    """
    try:
        markers = parse_reviewer_markers(discussion_messages)
        if not markers:
            return False
        feedback = build_reviewer_feedback(markers, symbol, market, job_id, as_of)
        if not feedback:
            return False
        context = (
            f"professional reviewer audit of {symbol} ({market}), job {job_id}"
            + (f", {as_of}" if as_of else "")
        )
        brain_manager.process_feedback({
            "user_id": "system_reviewer_feedback",
            "role": REVIEWER_GENOME_ROLE,
            "feedback": feedback,
            "context": context,
        })
        logger.info(
            "Reviewer feedback fed to EvolveR for job %s (%s): %d markers",
            job_id, symbol, len(markers),
        )
        return True
    except Exception as e:
        logger.warning("Reviewer feedback → EvolveR failed (non-fatal) for job %s: %s", job_id, e)
        return False


def feed_reviewer_feedback_to_brain_async(
    job_id: str,
    symbol: str,
    market: str,
    discussion_messages: Optional[List[Dict[str, Any]]],
    as_of: Optional[str] = None,
) -> Optional[threading.Thread]:
    """Fire-and-forget wrapper: run the feedback hook on a daemon thread.

    Why a thread (not asyncio.create_task): process_feedback contains
    synchronous LLM calls (DeepSeek → Gemini fallback) that can take tens of
    seconds — running them inside the event loop would block every other
    request, and awaiting them would delay the job pipeline. A daemon thread
    also survives the short-lived asyncio.run() loop of the Celery worker
    execution path. Failures inside the thread are swallowed by
    feed_reviewer_feedback_to_brain's blanket try/except.
    """
    try:
        t = threading.Thread(
            target=feed_reviewer_feedback_to_brain,
            args=(job_id, symbol, market, discussion_messages, as_of),
            name=f"reviewer-brain-{job_id}",
            daemon=True,
        )
        t.start()
        return t
    except Exception as e:
        logger.warning("Failed to launch reviewer feedback thread for job %s: %s", job_id, e)
        return None
