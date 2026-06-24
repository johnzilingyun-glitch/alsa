
from python_service.app.db.models import AnalysisArtifact, AnalysisRun, DataSnapshot
from python_service.app.services.lineage_service import build_analysis_lineage, classify_data_quality, should_downgrade_recommendation


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
            approval_state="draft",
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


def test_data_quality_conflicts_downgrade_strong_recommendations():
    assert classify_data_quality(None, stale=False, conflicting=False) == "missing"
    assert classify_data_quality("100", stale=True, conflicting=False) == "delayed"
    assert classify_data_quality("100", stale=False, conflicting=True) == "conflicting"
    assert should_downgrade_recommendation("Buy", ["verified", "conflicting"]) == "Needs Review"
    assert should_downgrade_recommendation("Hold", ["missing"]) == "Hold"
