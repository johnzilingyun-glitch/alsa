
from python_service.app.db.models import AnalysisArtifact, AnalysisRun, DataSnapshot
from python_service.app.services.lineage_service import (
    apply_data_quality_review_gate,
    build_analysis_lineage,
    classify_data_quality,
    should_downgrade_recommendation,
)


def test_analysis_lineage_includes_snapshot_prompt_model_and_artifacts(session_factory):
    with session_factory() as session:
        snapshot = DataSnapshot(
            snapshot_id="snap_1",
            symbol="AAPL",
            market="US-Share",
            as_of="2026-06-01T00:00:00Z",
            source="fixture",
            quality="verified",
            confidence=0.95,
            payload_json='{"price": 100}',
        )
        run = AnalysisRun(
            analysis_id="ana_1",
            job_id="job_1",
            symbol="AAPL",
            market="US-Share",
            snapshot_id="snap_1",
            summary_verdict="buy",
            score=82,
            risk_level="medium",
            prompt_version="chief-v1",
            model_provider="gemini",
            model_name="gemini-3.1-pro-preview",
            schema_version="analysis.v1",
            approval_state="approved",
        )
        artifact = AnalysisArtifact(analysis_id="ana_1", artifact_type="output_json", storage_path="memory://ana_1")
        session.add(snapshot)
        session.add(run)
        session.add(artifact)
        session.commit()

        lineage = build_analysis_lineage(session, "ana_1")

    assert lineage["analysis_id"] == "ana_1"
    assert lineage["snapshot"]["snapshot_id"] == "snap_1"
    assert lineage["prompt_version"] == "chief-v1"
    assert lineage["model_name"] == "gemini-3.1-pro-preview"
    assert lineage["artifacts"][0]["artifact_type"] == "output_json"
    assert lineage["as_of"] == "2026-06-01T00:00:00Z"
    assert lineage["display_metadata"] == {
        "snapshotId": "snap_1",
        "asOf": "2026-06-01T00:00:00Z",
        "modelName": "gemini-3.1-pro-preview",
        "modelVersion": None,
        "promptVersion": "chief-v1",
        "schemaVersion": "analysis.v1",
    }
    assert lineage["completeness"] == {"is_complete": True, "missing_fields": [], "publishable": True}


def test_data_quality_conflicts_downgrade_strong_recommendations():
    assert classify_data_quality(None, stale=False, conflicting=False) == "missing"
    assert classify_data_quality("100", stale=True, conflicting=False) == "delayed"
    assert classify_data_quality("100", stale=False, conflicting=True) == "conflicting"
    assert should_downgrade_recommendation("Buy", ["verified", "conflicting"]) == "Needs Review"
    assert should_downgrade_recommendation("Hold", ["missing"]) == "Hold"


def test_data_quality_gate_marks_strong_recommendation_for_manual_review():
    result = {
        "recommendation": "Buy",
        "summary_verdict": "buy",
        "data_quality": {
            "score": 0.7,
            "blocking_errors": [],
            "warnings": [{"code": "MISSING_PRICE", "severity": "high", "message": "Latest quote price is missing."}],
        },
        "tradingPlan": {"strategy": "breakout", "_validated": True},
    }

    gated = apply_data_quality_review_gate(result)

    assert gated["recommendation"] == "Needs Review"
    assert gated["summary_verdict"] == "watch"
    assert gated["manual_review"]["required"] is True
    assert gated["manual_review"]["state"] == "needs_review"
    assert gated["manual_review"]["original_recommendation"] == "Buy"
    assert "missing" in gated["manual_review"]["quality_labels"]
    assert gated["tradingPlan"]["_validated"] is False
    assert gated["tradingPlan"]["_manual_review_required"] is True


def test_data_quality_gate_keeps_hold_without_manual_review():
    result = {
        "recommendation": "Hold",
        "summary_verdict": "watch",
        "data_quality": {"score": 0.9, "blocking_errors": [], "warnings": []},
    }

    gated = apply_data_quality_review_gate(result)

    assert gated["recommendation"] == "Hold"
    assert gated["manual_review"]["required"] is False
    assert gated["manual_review"]["state"] == "not_required"


def test_analysis_lineage_reports_missing_publish_requirements(session_factory):
    with session_factory() as session:
        run = AnalysisRun(
            analysis_id="ana_missing",
            job_id="job_missing",
            symbol="MSFT",
            market="US-Share",
            snapshot_id=None,
            summary_verdict="hold",
            score=50,
            risk_level="high",
            prompt_version="",
            model_provider="unknown",
            model_name="unknown",
            schema_version="",
            approval_state="draft",
        )
        session.add(run)
        session.commit()

        lineage = build_analysis_lineage(session, "ana_missing")

    assert lineage["completeness"]["is_complete"] is False
    assert lineage["completeness"]["publishable"] is False
    assert lineage["completeness"]["missing_fields"] == [
        "snapshot_id",
        "prompt_version",
        "model_name",
        "schema_version",
        "snapshot",
        "artifacts",
    ]
