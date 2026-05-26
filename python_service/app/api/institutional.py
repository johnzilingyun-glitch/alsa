"""Institutional risk and system control API routes.

Exposes:
- Kill switch status and trigger/reset
- Risk gateway configuration
- System metrics summary
- Audit log queries
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/institutional", tags=["institutional"])


# --- Models ---

class KillSwitchTriggerRequest(BaseModel):
    trigger: str
    reason: str

class KillSwitchResetRequest(BaseModel):
    approval_id: str

class RiskCheckRequest(BaseModel):
    portfolio_id: str
    signal_id: str
    symbol: str
    market: str
    side: str
    requested_quantity: float
    requested_notional: float
    order_type: str
    limit_price: Optional[float] = None
    as_of_date: str
    evidence_quality: float
    data_quality_score: float
    conflict_level: str
    portfolio_value: Optional[float] = None
    existing_position_notional: Optional[float] = None
    daily_new_exposure_so_far: Optional[float] = None


# --- Routes ---

@router.get("/kill-switch")
async def get_kill_switch_status():
    from python_service.main import kill_switch
    return {
        "state": kill_switch.state.value,
        "can_submit_order": kill_switch.can_submit_order(),
        "events_count": len(kill_switch.events),
        "last_event": {
            "trigger": kill_switch.events[-1].trigger.value,
            "reason": kill_switch.events[-1].reason,
            "timestamp": kill_switch.events[-1].timestamp.isoformat(),
        } if kill_switch.events else None,
    }


@router.post("/kill-switch/trigger")
async def trigger_kill_switch(req: KillSwitchTriggerRequest):
    from python_service.main import kill_switch, audit_logger
    from python_service.app.risk.kill_switch import KillSwitchTrigger
    from python_service.app.observability.audit import AuditAction

    try:
        trigger = KillSwitchTrigger(req.trigger)
    except ValueError:
        raise HTTPException(400, f"Invalid trigger: {req.trigger}. Valid: {[t.value for t in KillSwitchTrigger]}")

    kill_switch.trigger(trigger, reason=req.reason)
    audit_logger.log(
        action=AuditAction.KILL_SWITCH_TRIGGERED,
        actor="api",
        details={"trigger": req.trigger, "reason": req.reason},
    )
    return {"state": kill_switch.state.value, "message": "Kill switch activated"}


@router.post("/kill-switch/reset")
async def reset_kill_switch(req: KillSwitchResetRequest):
    from python_service.main import kill_switch, audit_logger
    from python_service.app.observability.audit import AuditAction

    try:
        kill_switch.reset(approval_id=req.approval_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    audit_logger.log(
        action=AuditAction.HUMAN_APPROVAL,
        actor=req.approval_id,
        details={"action": "kill_switch_reset"},
    )
    return {"state": kill_switch.state.value, "message": "Kill switch reset"}


@router.post("/risk/pre-trade-check")
async def pre_trade_check(req: RiskCheckRequest):
    from python_service.main import risk_gateway, kill_switch, audit_logger
    from python_service.app.risk.pre_trade import PreTradeRiskRequest
    from python_service.app.observability.audit import AuditAction

    # Kill switch gate
    if not kill_switch.can_submit_order():
        raise HTTPException(403, "Kill switch active — no new orders allowed")

    risk_req = PreTradeRiskRequest(**req.model_dump())
    result = risk_gateway.check(risk_req)

    audit_logger.log(
        action=AuditAction.RISK_CHECK,
        actor="risk_gateway",
        details={
            "signal_id": req.signal_id,
            "symbol": req.symbol,
            "status": result.status.value,
            "blocking_rules": [r.rule_id for r in result.blocking_rules],
        },
    )

    return result.model_dump()


@router.get("/metrics/summary")
async def get_metrics_summary():
    from python_service.main import metrics_collector
    return {
        "api_latency": metrics_collector.get_stats("api_latency_ms"),
        "llm_calls": metrics_collector.get_stats("llm_call"),
        "llm_success_rate": metrics_collector.get_rate("llm_call", success_tag="status", success_value="success"),
        "risk_rejection_rate": metrics_collector.get_rate("risk_check", success_tag="result", success_value="REJECT"),
    }


@router.get("/audit/recent")
async def get_recent_audit(limit: int = 50):
    from python_service.main import audit_logger
    entries = audit_logger.get_entries()[-limit:]
    return [
        {
            "action": e.action.value,
            "actor": e.actor,
            "details": e.details,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in entries
    ]
