"""Failure capture utilities for post-mortem troubleshooting.

Every task-level exception should persist a minimal, redacted crash scene so
operators can reproduce and diagnose failures without relying on volatile logs.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging import get_logger

logger = get_logger(__name__)

_SENSITIVE_KEYS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "set-cookie",
    "private_key",
)


def _project_root() -> Path:
    # .../python_service/app/observability/failure_capture.py -> .../alsa
    return Path(__file__).resolve().parents[3]


def _incident_root() -> Path:
    configured = os.getenv("ALSA_INCIDENT_DIR", "").strip()
    if configured:
        p = Path(configured).expanduser().resolve()
    else:
        p = _project_root() / "data" / "incidents"
    # Ensure directory exists on first access
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(marker in key_lower for marker in _SENSITIVE_KEYS)


def _sanitize(value: Any, depth: int = 0, max_depth: int = 8) -> Any:
    if depth > max_depth:
        return "<truncated:max_depth>"

    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            if _is_sensitive_key(key_str):
                result[key_str] = "***REDACTED***"
            else:
                result[key_str] = _sanitize(v, depth + 1, max_depth)
        return result

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        clipped = items[:50]
        sanitized = [_sanitize(item, depth + 1, max_depth) for item in clipped]
        if len(items) > 50:
            sanitized.append(f"<truncated:{len(items) - 50}_items>")
        return sanitized

    if isinstance(value, str):
        if len(value) > 10000:
            return value[:10000] + f"\n...[truncated {len(value) - 10000} chars]"
        return value

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return repr(value)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _walk_for_key(payload: Any, key: str, max_depth: int = 6, depth: int = 0) -> Optional[Any]:
    if depth > max_depth:
        return None
    if isinstance(payload, dict):
        if key in payload:
            return payload.get(key)
        for v in payload.values():
            found = _walk_for_key(v, key, max_depth=max_depth, depth=depth + 1)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for v in payload[:50]:
            found = _walk_for_key(v, key, max_depth=max_depth, depth=depth + 1)
            if found is not None:
                return found
    return None


def _extract_diagnostics(index: Dict[str, Any], incident: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract route/provider diagnostics from incident snapshot payloads.

    Best-effort extraction to support both old and new incident formats.
    """
    provider_used = (
        index.get("provider_used")
        or incident.get("provider_used")
        or _walk_for_key(context, "provider_used")
        or _walk_for_key(context, "_routed_via")
        or _walk_for_key(context, "source")
    )
    fallback_depth = (
        index.get("fallback_depth")
        if index.get("fallback_depth") is not None
        else incident.get("fallback_depth")
    )
    if fallback_depth is None:
        fallback_depth = _walk_for_key(context, "fallback_depth")

    market_detected = (
        index.get("market_detected")
        or incident.get("market_detected")
        or _walk_for_key(context, "market_detected")
        or incident.get("market")
        or index.get("market")
    )

    data_type = (
        index.get("data_type")
        or incident.get("data_type")
        or _walk_for_key(context, "data_type")
    )

    cache_hit = (
        index.get("cache_hit")
        if index.get("cache_hit") is not None
        else incident.get("cache_hit")
    )
    if cache_hit is None:
        cache_hit = _walk_for_key(context, "cache_hit")

    quality_score = (
        index.get("quality_score")
        if index.get("quality_score") is not None
        else incident.get("quality_score")
    )
    if quality_score is None:
        quality_score = _walk_for_key(context, "quality_score")

    quality_threshold = (
        index.get("quality_threshold")
        if index.get("quality_threshold") is not None
        else incident.get("quality_threshold")
    )
    if quality_threshold is None:
        quality_threshold = _walk_for_key(context, "quality_threshold")

    route_meta = {
        "provider_used": provider_used,
        "fallback_depth": fallback_depth,
        "market_detected": market_detected,
        "data_type": data_type,
        "cache_hit": cache_hit,
        "quality_score": quality_score,
        "quality_threshold": quality_threshold,
    }

    return {
        "provider_used": provider_used,
        "fallback_depth": fallback_depth,
        "market_detected": market_detected,
        "data_type": data_type,
        "cache_hit": cache_hit,
        "quality_score": quality_score,
        "quality_threshold": quality_threshold,
        "route_meta": route_meta,
    }


def _build_incident_detail(index_entry: Dict[str, Any]) -> Dict[str, Any]:
    base = _incident_path_from_index(index_entry)
    if not base:
        diagnostics = _extract_diagnostics(index_entry, {}, {})
        enriched_index = {**index_entry, **diagnostics}
        return {
            "index": enriched_index,
            "incident": diagnostics,
            "context": {},
            "traceback": "",
            "diagnostics": diagnostics,
        }

    incident = _read_json(base / "incident.json")
    context = _read_json(base / "context.json")
    traceback_text = ""
    tb_file = base / "traceback.txt"
    if tb_file.exists():
        try:
            traceback_text = tb_file.read_text(encoding="utf-8")
        except Exception:
            traceback_text = ""

    diagnostics = _extract_diagnostics(index_entry, incident, context)
    enriched_index = {**index_entry, **diagnostics}
    enriched_incident = {**incident, **diagnostics}

    return {
        "index": enriched_index,
        "incident": enriched_incident,
        "context": context,
        "traceback": traceback_text,
        "diagnostics": diagnostics,
    }


def _load_index_lines(limit: int = 2000) -> List[Dict[str, Any]]:
    index_file = _incident_root() / "index.jsonl"
    if not index_file.exists():
        return []

    lines: List[Dict[str, Any]] = []
    try:
        with index_file.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        lines.append(parsed)
                except Exception:
                    continue
    except Exception:
        return []

    if len(lines) > limit:
        return lines[-limit:]
    return lines


def _incident_path_from_index(entry: Dict[str, Any]) -> Optional[Path]:
    path_str = str(entry.get("path") or "").strip()
    if not path_str:
        return None
    try:
        return Path(path_str)
    except Exception:
        return None


def get_incident_detail(incident_id: str) -> Optional[Dict[str, Any]]:
    """Fetch full incident detail by incident_id."""
    if not incident_id:
        return None

    entries = _load_index_lines()
    target: Optional[Dict[str, Any]] = None
    for entry in reversed(entries):
        if str(entry.get("incident_id", "")) == incident_id:
            target = entry
            break
    if not target:
        return None

    return _build_incident_detail(target)


def list_incidents_by_job_id(job_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """List incident index entries for a specific job_id (newest first)."""
    if not job_id:
        return []
    entries = _load_index_lines()
    matched = [entry for entry in entries if str(entry.get("job_id", "")) == job_id]
    matched.reverse()
    clipped = matched[: max(1, min(limit, 200))]
    enriched = []
    for row in clipped:
        detail = _build_incident_detail(row)
        enriched.append(detail.get("index", row))
    return enriched


def query_incidents(job_id: Optional[str] = None, incident_id: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Aggregate query helper for management API.

    If incident_id is provided, returns incident detail.
    If job_id is provided, returns incident list and latest detail.
    """
    if incident_id:
        detail = get_incident_detail(incident_id)
        return {
            "query": {"job_id": job_id, "incident_id": incident_id, "limit": limit},
            "items": [detail] if detail else [],
            "latest": detail,
        }

    if job_id:
        rows = list_incidents_by_job_id(job_id, limit=limit)
        latest = get_incident_detail(rows[0].get("incident_id")) if rows else None
        return {
            "query": {"job_id": job_id, "incident_id": incident_id, "limit": limit},
            "items": rows,
            "latest": latest,
        }

    return {
        "query": {"job_id": job_id, "incident_id": incident_id, "limit": limit},
        "items": [],
        "latest": None,
    }


def capture_failure_incident(
    *,
    component: str,
    error: Exception,
    job_id: Optional[str] = None,
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    stage: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    traceback_text: Optional[str] = None,
) -> Dict[str, str]:
    """Persist a redacted failure snapshot and return identifiers.

    Returns:
        {"incident_id": "...", "incident_path": "..."}
    """
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    job_part = (job_id or "unknown_job").replace("/", "_")
    incident_id = f"inc_{now.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}"

    base_dir = _incident_root() / date_part / job_part / incident_id
    tb = traceback_text or traceback.format_exc()

    incident_meta = {
        "incident_id": incident_id,
        "timestamp_utc": now.isoformat(),
        "component": component,
        "job_id": job_id,
        "symbol": symbol,
        "market": market,
        "stage": stage,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "host": socket.gethostname(),
        "python_version": platform.python_version(),
    }
    incident_context = {
        "context": _sanitize(context or {}),
        "metadata": _sanitize(metadata or {}),
    }

    try:
        _write_json(base_dir / "incident.json", incident_meta)
        _write_json(base_dir / "context.json", incident_context)
        with (base_dir / "traceback.txt").open("w", encoding="utf-8") as f:
            f.write(tb or "<no traceback>")

        index_line = {
            "timestamp_utc": now.isoformat(),
            "incident_id": incident_id,
            "component": component,
            "job_id": job_id,
            "symbol": symbol,
            "market": market,
            "stage": stage,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "path": str(base_dir),
        }
        index_file = _incident_root() / "index.jsonl"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        with index_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(index_line, ensure_ascii=False) + "\n")

        logger.error(
            "failure_incident_captured",
            incident_id=incident_id,
            component=component,
            job_id=job_id,
            incident_path=str(base_dir),
        )
    except Exception as persist_error:
        logger.error(
            "failure_incident_capture_failed",
            component=component,
            job_id=job_id,
            error=str(persist_error),
        )

    return {"incident_id": incident_id, "incident_path": str(base_dir)}
