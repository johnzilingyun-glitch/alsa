import json
from typing import Any

from sqlmodel import Session, select

from ..db.models import AnalysisArtifact, AnalysisRun, DataSnapshot


def classify_data_quality(value: Any, *, stale: bool = False, conflicting: bool = False) -> str:
    if value is None or value == "":
        return "missing"
    if conflicting:
        return "conflicting"
    if stale:
        return "delayed"
    return "verified"


def should_downgrade_recommendation(recommendation: str, qualities: list[str]) -> str:
    strong = recommendation.lower() in {"buy", "sell", "overweight", "underweight"}
    weak_quality = any(q in {"missing", "conflicting"} for q in qualities)
    return "Needs Review" if strong and weak_quality else recommendation


def apply_data_quality_review_gate(result: dict[str, Any]) -> dict[str, Any]:
    data_quality = result.get("data_quality") or {}
    warnings = data_quality.get("warnings") or []
    blocking_errors = data_quality.get("blocking_errors") or []
    qualities = _quality_labels_from_snapshot(data_quality)
    original_recommendation = str(result.get("recommendation") or "Hold")
    reviewed_recommendation = should_downgrade_recommendation(original_recommendation, qualities)
    requires_review = reviewed_recommendation != original_recommendation or bool(blocking_errors)

    if requires_review:
        result["recommendation"] = reviewed_recommendation
        result["summary_verdict"] = "watch"
        result["manual_review"] = {
            "required": True,
            "state": "needs_review",
            "reason": "data_quality_issue",
            "quality_labels": qualities,
            "warnings": warnings,
            "blocking_errors": blocking_errors,
            "original_recommendation": original_recommendation,
        }
        trading_plan = result.get("tradingPlan")
        if isinstance(trading_plan, dict):
            trading_plan["_validated"] = False
            trading_plan["_manual_review_required"] = True
    else:
        result.setdefault(
            "manual_review",
            {
                "required": False,
                "state": "not_required",
                "quality_labels": qualities,
                "warnings": warnings,
                "blocking_errors": blocking_errors,
            },
        )
    return result


def build_analysis_lineage(session: Session, analysis_id: str) -> dict[str, Any] | None:
    run = session.get(AnalysisRun, analysis_id)
    if not run:
        return None
    snapshot = session.get(DataSnapshot, run.snapshot_id) if run.snapshot_id else None
    artifacts = session.exec(select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == analysis_id)).all()
    artifact_payload = [
        {
            "artifact_id": item.artifact_id,
            "artifact_type": item.artifact_type,
            "storage_path": item.storage_path,
            "content_hash": item.content_hash,
        }
        for item in artifacts
    ]
    missing_fields = _missing_lineage_fields(run, snapshot, artifact_payload)
    is_complete = not missing_fields
    as_of = snapshot.as_of if snapshot else None
    return {
        "analysis_id": run.analysis_id,
        "job_id": run.job_id,
        "symbol": run.symbol,
        "market": run.market,
        "snapshot_id": run.snapshot_id,
        "prompt_version": run.prompt_version,
        "model_provider": run.model_provider,
        "model_name": run.model_name,
        "model_version": run.model_version,
        "schema_version": run.schema_version,
        "approval_state": run.approval_state,
        "human_reviewer": run.human_reviewer,
        "created_at": run.created_at.isoformat(),
        "as_of": as_of,
        "display_metadata": {
            "snapshotId": run.snapshot_id,
            "asOf": as_of,
            "modelName": run.model_name,
            "modelVersion": run.model_version,
            "promptVersion": run.prompt_version,
            "schemaVersion": run.schema_version,
        },
        "completeness": {
            "is_complete": is_complete,
            "missing_fields": missing_fields,
            "publishable": is_complete and run.approval_state in {"approved", "published"},
        },
        "snapshot": None if not snapshot else {
            "snapshot_id": snapshot.snapshot_id,
            "source": snapshot.source,
            "as_of": snapshot.as_of,
            "quality": snapshot.quality,
            "confidence": snapshot.confidence,
            "payload": json.loads(snapshot.payload_json or "{}"),
        },
        "artifacts": artifact_payload,
    }


def _missing_lineage_fields(run: AnalysisRun, snapshot: DataSnapshot | None, artifacts: list[dict[str, Any]]) -> list[str]:
    missing = []
    required_run_fields = {
        "snapshot_id": run.snapshot_id,
        "prompt_version": run.prompt_version,
        "model_name": run.model_name,
        "schema_version": run.schema_version,
    }
    for field, value in required_run_fields.items():
        if not value or value == "unknown":
            missing.append(field)
    if snapshot is None:
        missing.append("snapshot")
    elif not snapshot.as_of:
        missing.append("snapshot.as_of")
    if not artifacts:
        missing.append("artifacts")
    return missing


def _quality_labels_from_snapshot(data_quality: dict[str, Any]) -> list[str]:
    labels = ["verified"]
    warning_codes = {str(item.get("code", "")).upper() for item in data_quality.get("warnings", []) if isinstance(item, dict)}
    warning_severities = {
        str(item.get("severity", "")).lower() for item in data_quality.get("warnings", []) if isinstance(item, dict)
    }
    if data_quality.get("blocking_errors"):
        labels.append("conflicting")
    if "MISSING_PRICE" in warning_codes or "high" in warning_severities:
        labels.append("missing")
    if "SHORT_HISTORY" in warning_codes:
        labels.append("delayed")
    return labels
