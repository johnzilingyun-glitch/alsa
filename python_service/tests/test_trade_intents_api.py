from fastapi import FastAPI
from fastapi.testclient import TestClient

import python_service.app.api.trade_intents as trade_intents
from python_service.app.api.trade_intents import router
from python_service.app.observability.audit import AuditAction, AuditLogger


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_trade_intent_requires_risk_approval_before_submission():
    client = _client()
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

    submitted = client.post(f"/api/trade-intents/{created['intent_id']}/submit", json={"confirm_live_trading": True, "confirmed_by": "pm"})
    assert submitted.status_code == 400


def test_trade_intent_can_be_human_approved_then_submitted(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    client = _client()
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

    missing_confirmation = client.post(f"/api/trade-intents/{created['intent_id']}/submit", json={"confirmed_by": "pm"})
    assert missing_confirmation.status_code == 400

    wrong_user = client.post(
        f"/api/trade-intents/{created['intent_id']}/submit",
        json={"confirm_live_trading": True, "confirmed_by": "other_pm"},
    )
    assert wrong_user.status_code == 400

    submitted = client.post(
        f"/api/trade-intents/{created['intent_id']}/submit",
        json={"confirm_live_trading": True, "confirmed_by": "pm"},
    ).json()["data"]
    assert submitted["approval_state"] == "submitted"

    duplicate = client.post(
        f"/api/trade-intents/{created['intent_id']}/submit",
        json={"confirm_live_trading": True, "confirmed_by": "pm"},
    )
    assert duplicate.status_code == 400


def test_trade_intent_rejects_invalid_schema_before_risk_gateway():
    client = _client()
    payload = {
        "symbol": "AAPL",
        "market": "US-Share",
        "side": "HOLD",
        "quantity": 10,
        "notional": 1500,
        "source_analysis_run_id": "ana_test",
        "thesis": "quality compounder",
        "data_quality_score": 0.90,
        "evidence_quality": 0.90,
        "conflict_level": "C9",
    }

    response = client.post("/api/trade-intents", json=payload)

    assert response.status_code == 422


def test_trade_intent_writes_audit_entries_for_lifecycle(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    audit = AuditLogger()
    monkeypatch.setattr(trade_intents, "get_audit_logger", lambda: audit)
    client = _client()
    payload = {
        "symbol": "NVDA",
        "market": "US-Share",
        "side": "BUY",
        "quantity": 2,
        "notional": 1000,
        "source_analysis_run_id": "ana_audit",
        "thesis": "audit covered setup",
        "data_quality_score": 0.95,
        "evidence_quality": 0.90,
        "conflict_level": "C0",
    }

    created = client.post("/api/trade-intents", json=payload).json()["data"]
    client.post(f"/api/trade-intents/{created['intent_id']}/approve", json={"approved_by": "pm"})
    client.post(
        f"/api/trade-intents/{created['intent_id']}/submit",
        json={"confirm_live_trading": True, "confirmed_by": "pm"},
    )
    client.post(
        f"/api/trade-intents/{created['intent_id']}/submit",
        json={"confirm_live_trading": True, "confirmed_by": "pm"},
    )

    actions = [entry.action for entry in audit.get_entries()]
    assert actions == [
        AuditAction.ORDER_INTENT_CREATED,
        AuditAction.HUMAN_APPROVAL,
        AuditAction.ORDER_SUBMITTED,
        AuditAction.ORDER_SUBMISSION_REJECTED,
    ]
    rejected = audit.get_entries(AuditAction.ORDER_SUBMISSION_REJECTED)[0]
    assert rejected.details["reason"] == "already_submitted"
    assert rejected.details["intent_id"] == created["intent_id"]
