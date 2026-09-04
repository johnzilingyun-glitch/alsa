from fastapi.testclient import TestClient
import sys
import os
import pytest

# Add the project root to sys.path to allow imports from python_service
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app
from python_service.app.api.analysis import AnalysisJobCreate


def test_analysis_job_lifecycle():
    client = TestClient(app)
    # 1. Create job
    resp = client.post("/api/analysis/jobs", json={
        "symbol": "600519", 
        "market": "A-Share",
        "analysis_level": "standard"
    })
    assert resp.status_code == 202
    data = resp.json()
    assert data["success"] is True
    job_id = data["data"]["job_id"]
    assert job_id.startswith("job_")
    
    # 2. Check status immediately
    resp = client.get(f"/api/analysis/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] in ["queued", "running", "completed"]


def test_analysis_job_rejects_invalid_analysis_level():
    """analysis_level must be one of quick/standard/deep (stock-task levels).

    Regression guard: a stock job sent with analysis_level="sector"/
    "serenity_alpha" used to pass an unconstrained str straight into
    discussion_service, accidentally hitting the sector exemption and
    disabling the unidentifiable-stock early abort. Pydantic must reject it
    with 422 before any job is created."""
    client = TestClient(app)
    for bad_level in ("sector", "serenity_alpha", "scan", "fast", "full", ""):
        resp = client.post("/api/analysis/jobs", json={
            "symbol": "600519",
            "market": "A-Share",
            "analysis_level": bad_level,
        })
        assert resp.status_code == 422, f"analysis_level={bad_level!r} must be rejected"


def test_analysis_job_create_model_accepts_only_stock_levels():
    """Model-level check: all three documented stock levels validate, anything
    else raises ValidationError (keeps the whitelist in sync with the frontend
    AnalysisLevel type: quick | standard | deep)."""
    from pydantic import ValidationError

    for good_level in ("quick", "standard", "deep"):
        payload = AnalysisJobCreate(
            symbol="600519", market="A-Share", analysis_level=good_level
        )
        assert payload.analysis_level == good_level

    # Omitted level falls back to "standard"
    assert AnalysisJobCreate(symbol="600519", market="A-Share").analysis_level == "standard"

    with pytest.raises(ValidationError):
        AnalysisJobCreate(symbol="600519", market="A-Share", analysis_level="sector")
