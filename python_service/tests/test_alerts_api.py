"""Tests for the search alerts API endpoint."""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi.testclient import TestClient
from python_service.main import app

HEADERS = {"Authorization": "Bearer mock-token"}


def test_create_alert():
    client = TestClient(app)
    resp = client.post("/api/alerts/", json={
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "market": "US-Share",
        "entry_price": 180.0,
        "target_price": 220.0,
        "stop_loss": 160.0,
    }, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["status"] == "active"


def test_list_alerts():
    client = TestClient(app)
    client.post("/api/alerts/", json={
        "symbol": "00700", "name": "Tencent", "market": "HK-Share",
        "entry_price": 380, "target_price": 450, "stop_loss": 350,
    }, headers=HEADERS)

    resp = client.get("/api/alerts/", headers=HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert any(i["symbol"] == "00700" for i in items)


def test_delete_alert():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "600519", "name": "茅台", "market": "A-Share",
        "entry_price": 1800, "target_price": 2200, "stop_loss": 1600,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    resp = client.delete(f"/api/alerts/{alert_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_alert_postmortem():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "TSLA", "name": "Tesla", "market": "US-Share",
        "entry_price": 240, "target_price": 300, "stop_loss": 220,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    resp = client.post(f"/api/alerts/{alert_id}/postmortem", json={
        "exit_price": 280,
        "outcome_category": "TRUE_POSITIVE",
        "decision_quality": 8,
        "notes": "Solid run-up on earnings",
    }, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["outcome_category"] == "TRUE_POSITIVE"


def test_alert_postmortem_invalid_category():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "AMD", "name": "AMD", "market": "US-Share",
        "entry_price": 120, "target_price": 150, "stop_loss": 110,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    resp = client.post(f"/api/alerts/{alert_id}/postmortem", json={
        "exit_price": 130,
        "outcome_category": "INVALID",
    }, headers=HEADERS)
    assert resp.status_code == 400


def test_alert_postmortem_invalid_quality():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "NVDA", "name": "NVIDIA", "market": "US-Share",
        "entry_price": 800, "target_price": 1000, "stop_loss": 750,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    resp = client.post(f"/api/alerts/{alert_id}/postmortem", json={
        "exit_price": 950,
        "outcome_category": "TRUE_POSITIVE",
        "decision_quality": 15,
    }, headers=HEADERS)
    assert resp.status_code == 400


def test_update_alert_thesis():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "BABA", "name": "Alibaba", "market": "HK-Share",
        "entry_price": 85, "target_price": 110, "stop_loss": 75,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    resp = client.patch(f"/api/alerts/{alert_id}/thesis", json={
        "thesis": "Cloud growth re-acceleration",
        "thesis_stage": "WATCHING",
    }, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["thesis"] == "Cloud growth re-acceleration"
    assert resp.json()["thesis_stage"] == "WATCHING"


def test_update_alert_thesis_invalid_stage():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "META", "name": "Meta", "market": "US-Share",
        "entry_price": 450, "target_price": 550, "stop_loss": 400,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    resp = client.patch(f"/api/alerts/{alert_id}/thesis", json={
        "thesis_stage": "UNKNOWN",
    }, headers=HEADERS)
    assert resp.status_code == 400


def test_enable_monitoring():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "GOOGL", "name": "Alphabet", "market": "US-Share",
        "entry_price": 170, "target_price": 200, "stop_loss": 155,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    resp = client.post(f"/api/alerts/{alert_id}/enable-monitoring", json={}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_disable_monitoring():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "MSFT", "name": "Microsoft", "market": "US-Share",
        "entry_price": 400, "target_price": 480, "stop_loss": 380,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    client.post(f"/api/alerts/{alert_id}/enable-monitoring", json={}, headers=HEADERS)
    resp = client.post(f"/api/alerts/{alert_id}/disable-monitoring", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_monitoring_status():
    client = TestClient(app)
    client.post("/api/alerts/", json={
        "symbol": "AMZN", "name": "Amazon", "market": "US-Share",
        "entry_price": 180, "target_price": 220, "stop_loss": 165,
    }, headers=HEADERS)

    resp = client.get("/api/alerts/monitoring/status", headers=HEADERS)
    assert resp.status_code == 200
    assert "total_monitored" in resp.json()


def test_list_closed_alerts():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "NFLX", "name": "Netflix", "market": "US-Share",
        "entry_price": 600, "target_price": 700, "stop_loss": 550,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    client.post(f"/api/alerts/{alert_id}/postmortem", json={
        "exit_price": 680,
        "outcome_category": "TRUE_POSITIVE",
    }, headers=HEADERS)

    resp = client.get("/api/alerts/closed", headers=HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["symbol"] == "NFLX" for i in items)


def test_triggered_alerts_remain_in_list():
    client = TestClient(app)
    create_resp = client.post("/api/alerts/", json={
        "symbol": "300750", "name": "宁德时代", "market": "A-Share",
        "entry_price": 200, "target_price": 250, "stop_loss": 180,
    }, headers=HEADERS)
    alert_id = create_resp.json()["alert_id"]

    # Import repo and mark triggered
    from python_service.main import get_alert_repo
    repo = get_alert_repo()
    repo.mark_triggered(alert_id, "target", 255.0)

    # Verify that triggered alert is STILL listed in GET /api/alerts/ and not lost
    resp = client.get("/api/alerts/", headers=HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    found = [i for i in items if i["alert_id"] == alert_id]
    assert len(found) == 1
    assert found[0]["status"] == "triggered"
    assert found[0]["monitoring_enabled"] is True

