from fastapi.testclient import TestClient

from python_service.main import app


def test_trade_intent_requires_risk_approval_before_submission():
    client = TestClient(app)
    payload = {
        "symbol": "AAPL",
        "market": "US-Share",
        "side": "BUY",
        "quantity": 10,
        "notional": 1500,
        "source_analysis_run_id": "ana_test",
        "thesis": "quality compounder",
        "data_quality_score": 0.40,
        "evidence_quality": 0.90,
        "conflict_level": "C0",
    }

    created = client.post("/api/trade-intents", json=payload).json()["data"]
    assert created["approval_state"] == "risk_rejected"
    assert created["risk_result"]["status"] == "REJECT"

    submitted = client.post(f"/api/trade-intents/{created['intent_id']}/submit")
    assert submitted.status_code == 400


def test_trade_intent_can_be_human_approved_then_submitted(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    client = TestClient(app)
    payload = {
        "symbol": "MSFT",
        "market": "US-Share",
        "side": "BUY",
        "quantity": 5,
        "notional": 1000,
        "source_analysis_run_id": "ana_ok",
        "thesis": "approved setup",
        "data_quality_score": 0.95,
        "evidence_quality": 0.90,
        "conflict_level": "C0",
    }

    created = client.post("/api/trade-intents", json=payload).json()["data"]
    assert created["approval_state"] == "risk_approved"

    approved = client.post(f"/api/trade-intents/{created['intent_id']}/approve", json={"approved_by": "pm"}).json()["data"]
    assert approved["approval_state"] == "human_approved"

    submitted = client.post(f"/api/trade-intents/{created['intent_id']}/submit").json()["data"]
    assert submitted["approval_state"] == "submitted"
