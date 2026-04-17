from fastapi.testclient import TestClient
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app

def test_admin_requires_token():
    client = TestClient(app)
    resp = client.get("/api/admin/stack-status")
    assert resp.status_code == 403

def test_admin_passes_with_correct_token():
    client = TestClient(app)
    # Default is "change-me"
    resp = client.get("/api/admin/stack-status", headers={"x-admin-token": "change-me"})
    assert resp.status_code == 200
    assert resp.json()["fastapi"] == "active"
