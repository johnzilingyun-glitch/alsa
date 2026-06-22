from fastapi.testclient import TestClient
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app

HEADERS = {"Authorization": "Bearer mock-token"}

def test_watchlist_api_flow():
    client = TestClient(app)
    
    # Add
    resp = client.post("/api/watchlist/", json={
        "symbol": "600519", 
        "name": "贵州茅台", 
        "market": "A-Share"
    }, headers=HEADERS)
    assert resp.status_code == 201
    
    # List
    resp = client.get("/api/watchlist/", headers=HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["symbol"] == "600519" for i in items)
    
    # Delete
    resp = client.delete("/api/watchlist/600519?market=A-Share", headers=HEADERS)
    assert resp.status_code == 200
    
    # List again
    resp = client.get("/api/watchlist/", headers=HEADERS)
    items = resp.json()["items"]
    assert not any(i["symbol"] == "600519" for i in items)
