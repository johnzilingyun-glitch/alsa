import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "checks" in data
    
    checks = data["checks"]
    assert "database" in checks
    assert "llm_gateway" in checks
    assert "memory" in checks
    assert "disk" in checks
    
    assert checks["database"]["status"] == "healthy"
    assert checks["memory"]["status"] in ("healthy", "warning")
    assert checks["disk"]["status"] in ("healthy", "warning")

def test_readiness_endpoint():
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"

def test_liveness_endpoint():
    response = client.get("/api/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
