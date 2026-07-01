import json
import os
from typing import Literal

from ..time_utils import utc_now

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..db.models import TradeIntent
from ..db.database import session_factory
from ..risk.pre_trade import PreTradeRiskGateway, PreTradeRiskRequest
from ..utils.responses import success_response

router = APIRouter(prefix="/trade-intents", tags=["trade-intents"])


class TradeIntentCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    market: Literal["A-Share", "HK-Share", "US-Share"]
    side: Literal["BUY", "SELL", "SHORT", "COVER"]
    quantity: float = Field(gt=0)
    notional: float = Field(gt=0)
    source_analysis_run_id: str | None = Field(default=None, max_length=128)
    thesis: str = Field(min_length=8, max_length=4000)
    data_quality_score: float = Field(ge=0.0, le=1.0)
    evidence_quality: float = Field(ge=0.0, le=1.0)
    conflict_level: Literal["C0", "C1", "C2", "C3", "C4"] = "C0"
    portfolio_id: str = Field(default="default_portfolio", min_length=1, max_length=128)

    @field_validator("symbol", "portfolio_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip()


class ApprovalPayload(BaseModel):
    approved_by: str


class SubmitPayload(BaseModel):
    confirm_live_trading: bool = False
    confirmed_by: str


def _serialize(intent: TradeIntent) -> dict:
    return {
        "intent_id": intent.intent_id,
        "symbol": intent.symbol,
        "market": intent.market,
        "side": intent.side,
        "quantity": intent.quantity,
        "notional": intent.notional,
        "source_analysis_run_id": intent.source_analysis_run_id,
        "thesis": intent.thesis,
        "approval_state": intent.approval_state,
        "risk_result": json.loads(intent.risk_result_json or "{}"),
        "approved_by": intent.approved_by,
        "submitted_at": intent.submitted_at.isoformat() if intent.submitted_at else None,
    }


@router.post("")
def create_trade_intent(payload: TradeIntentCreate):
    request = PreTradeRiskRequest(
        portfolio_id=payload.portfolio_id,
        signal_id=payload.source_analysis_run_id or "manual",
        symbol=payload.symbol,
        market=payload.market,
        side=payload.side,
        requested_quantity=payload.quantity,
        requested_notional=payload.notional,
        order_type="MARKET",
        as_of_date=utc_now().date().isoformat(),
        evidence_quality=payload.evidence_quality,
        data_quality_score=payload.data_quality_score,
        conflict_level=payload.conflict_level,
    )
    risk_result = PreTradeRiskGateway().check(request)
    approval_state = "risk_approved" if risk_result.status.value == "PASS" else "risk_rejected"
    intent = TradeIntent(
        symbol=payload.symbol,
        market=payload.market,
        side=payload.side,
        quantity=payload.quantity,
        notional=payload.notional,
        source_analysis_run_id=payload.source_analysis_run_id,
        thesis=payload.thesis,
        approval_state=approval_state,
        risk_result_json=risk_result.model_dump_json(),
    )
    with session_factory() as session:
        session.add(intent)
        session.commit()
        session.refresh(intent)
        return success_response(_serialize(intent))


@router.post("/{intent_id}/approve")
def approve_trade_intent(intent_id: str, payload: ApprovalPayload):
    with session_factory() as session:
        intent = session.get(TradeIntent, intent_id)
        if not intent:
            raise HTTPException(status_code=404, detail="Trade intent not found")
        if intent.approval_state != "risk_approved":
            raise HTTPException(status_code=400, detail="Only risk-approved intents can be human approved")
        intent.approval_state = "human_approved"
        intent.approved_by = payload.approved_by
        session.add(intent)
        session.commit()
        session.refresh(intent)
        return success_response(_serialize(intent))


@router.post("/{intent_id}/submit")
def submit_trade_intent(intent_id: str, payload: SubmitPayload):
    if os.getenv("ENABLE_LIVE_TRADING") != "true":
        raise HTTPException(status_code=400, detail="Live trading is disabled")
    if not payload.confirm_live_trading:
        raise HTTPException(status_code=400, detail="Live trading submission requires explicit confirmation")
    with session_factory() as session:
        intent = session.get(TradeIntent, intent_id)
        if not intent:
            raise HTTPException(status_code=404, detail="Trade intent not found")
        if intent.approval_state == "submitted":
            raise HTTPException(status_code=400, detail="Trade intent has already been submitted")
        if intent.approval_state != "human_approved":
            raise HTTPException(status_code=400, detail="Human approval is required before submission")
        if intent.approved_by != payload.confirmed_by:
            raise HTTPException(status_code=400, detail="Submit confirmation must be performed by the approving user")
        intent.approval_state = "submitted"
        intent.submitted_at = utc_now()
        session.add(intent)
        session.commit()
        session.refresh(intent)
        return success_response(_serialize(intent))
