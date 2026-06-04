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


def build_analysis_lineage(session: Session, analysis_id: str) -> dict[str, Any] | None:
    run = session.get(AnalysisRun, analysis_id)
    if not run:
        return None
    snapshot = session.get(DataSnapshot, run.snapshot_id) if run.snapshot_id else None
    artifacts = session.exec(select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == analysis_id)).all()
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
        "snapshot": None if not snapshot else {
            "snapshot_id": snapshot.snapshot_id,
            "source": snapshot.source,
            "as_of": snapshot.as_of,
            "quality": snapshot.quality,
            "confidence": snapshot.confidence,
            "payload": json.loads(snapshot.payload_json or "{}"),
        },
        "artifacts": [
            {
                "artifact_id": item.artifact_id,
                "artifact_type": item.artifact_type,
                "storage_path": item.storage_path,
                "content_hash": item.content_hash,
            }
            for item in artifacts
        ],
    }
