from fastapi.testclient import TestClient
import sys
import os

# Add the project root to sys.path to allow imports from python_service
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app

def test_create_analysis_job():
    client = TestClient(app)
    resp = client.post("/api/analysis/jobs", json={
        "symbol": "600519", 
        "market": "A-Share", 
        "level": "standard"
    })
    assert resp.status_code == 202
    assert resp.json()["job_id"].startswith("job_")
