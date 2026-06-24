from fastapi.testclient import TestClient
import sys
import os

# Add the project root to sys.path to allow imports from python_service
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app


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
