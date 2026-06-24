import os
import sys
from fastapi.testclient import TestClient

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app

def test_pipeline_routing_production_default():
    client = TestClient(app)
    
    # Target a mock sector scan start
    payload = {
        "sector_name": "Test Sector",
        "model": "gemini-3.5-flash",
        "date": "2026-06-22",
        "force": True,
        "pipeline_version": "production"
    }
    
    response = client.post("/api/sector/serenity-analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Production should route to SectorAnalysisService returning sector_ prefix
    assert data["data"]["job_id"].startswith("sector_")

def test_pipeline_routing_development():
    client = TestClient(app)
    
    payload = {
        "sector_name": "Test Sector",
        "model": "gemini-3.5-flash",
        "date": "2026-06-22",
        "force": True,
        "pipeline_version": "development"
    }
    
    response = client.post("/api/sector/serenity-analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Development should route to SerenityGraphService returning graph_ prefix
    assert data["data"]["job_id"].startswith("graph_")
