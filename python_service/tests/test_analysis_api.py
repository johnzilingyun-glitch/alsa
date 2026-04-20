from fastapi.testclient import TestClient
import sys
import os

# Add the project root to sys.path to allow imports from python_service
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app

import time

def test_analysis_job_lifecycle():
    client = TestClient(app)
    # 1. Create job
    resp = client.post("/api/analysis/jobs", json={
        "symbol": "600519", 
        "market": "A-Share"
    })
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert job_id.startswith("job_")
    
    # 2. Check status immediately
    resp = client.get(f"/api/analysis/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] in ["queued", "running", "completed"]
