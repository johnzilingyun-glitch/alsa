from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from ..db.repositories.alert_repo import AlertRepository
from ..db.models import Catalyst
from sqlmodel import Session, select
from ..db.sqlite import session_factory

class AlertCreate(BaseModel):
    symbol: str
    name: str
    market: str
    entry_price: float
    target_price: float
    stop_loss: float
    currency: Optional[str] = "CNY"

router = APIRouter(prefix="/alerts", tags=["alerts"])

def get_repo():
    from ...main import get_alert_repo
    return get_alert_repo()

@router.post("/", status_code=201)
async def create_alert(payload: AlertCreate, repo: AlertRepository = Depends(get_repo)):
    return repo.create(
        payload.symbol, 
        payload.name, 
        payload.market, 
        payload.entry_price, 
        payload.target_price, 
        payload.stop_loss,
        payload.currency
    )

@router.get("/")
async def list_alerts(repo: AlertRepository = Depends(get_repo)):
    items = repo.list_active()
    return {"items": items}

@router.get("/closed")
async def list_closed_alerts(repo: AlertRepository = Depends(get_repo)):
    items = repo.list_closed()
    return {"items": items}

@router.delete("/{alert_id}")
async def delete_alert(alert_id: int, repo: AlertRepository = Depends(get_repo)):
    repo.delete_by_id(alert_id)
    return {"success": True}

@router.patch("/{alert_id}/status")
async def update_alert_status(alert_id: int, status: str, repo: AlertRepository = Depends(get_repo)):
    repo.update_status(alert_id, status)
    return {"success": True}


class PostmortemCreate(BaseModel):
    exit_price: float
    outcome_category: str  # TRUE_POSITIVE/FALSE_POSITIVE/MISSED/REGIME_MISMATCH
    mae_pct: Optional[float] = None
    mfe_pct: Optional[float] = None
    notes: Optional[str] = None
    decision_quality: Optional[int] = None  # 1-10


@router.post("/{alert_id}/postmortem")
async def record_postmortem(alert_id: str, payload: PostmortemCreate, repo: AlertRepository = Depends(get_repo)):
    if payload.outcome_category not in ("TRUE_POSITIVE", "FALSE_POSITIVE", "MISSED", "REGIME_MISMATCH"):
        raise HTTPException(400, "outcome_category must be one of: TRUE_POSITIVE, FALSE_POSITIVE, MISSED, REGIME_MISMATCH")
    if payload.decision_quality is not None and not (1 <= payload.decision_quality <= 10):
        raise HTTPException(400, "decision_quality must be between 1 and 10")
    result = repo.record_postmortem(
        alert_id=alert_id,
        exit_price=payload.exit_price,
        outcome_category=payload.outcome_category,
        mae_pct=payload.mae_pct,
        mfe_pct=payload.mfe_pct,
        notes=payload.notes,
        decision_quality=payload.decision_quality,
    )
    if not result:
        raise HTTPException(404, "Alert not found")
    return result


class ThesisUpdate(BaseModel):
    thesis: Optional[str] = None
    invalidation_criteria: Optional[str] = None
    thesis_stage: Optional[str] = None
    lessons_learned: Optional[str] = None


@router.patch("/{alert_id}/thesis")
async def update_thesis(alert_id: str, payload: ThesisUpdate, repo: AlertRepository = Depends(get_repo)):
    if payload.thesis_stage and payload.thesis_stage not in ("IDEA", "WATCHING", "ENTERED", "EXITED", "POSTMORTEM"):
        raise HTTPException(400, "thesis_stage must be one of: IDEA, WATCHING, ENTERED, EXITED, POSTMORTEM")
    result = repo.update_thesis(
        alert_id=alert_id,
        thesis=payload.thesis,
        invalidation_criteria=payload.invalidation_criteria,
        thesis_stage=payload.thesis_stage,
        lessons_learned=payload.lessons_learned,
    )
    if not result:
        raise HTTPException(404, "Alert not found")
    return result


# --- Catalyst Calendar ---

class CatalystCreate(BaseModel):
    alert_id: str
    symbol: str
    event_type: str  # earnings/product_launch/regulatory/macro/conference/other
    description: str
    expected_date: Optional[str] = None
    impact_direction: Optional[str] = None
    impact_magnitude: Optional[str] = None


@router.post("/catalysts", status_code=201)
async def create_catalyst(payload: CatalystCreate):
    from datetime import datetime as dt
    with session_factory() as session:
        cat = Catalyst(
            alert_id=payload.alert_id,
            symbol=payload.symbol,
            event_type=payload.event_type,
            description=payload.description,
            expected_date=dt.fromisoformat(payload.expected_date) if payload.expected_date else None,
            impact_direction=payload.impact_direction,
            impact_magnitude=payload.impact_magnitude,
        )
        session.add(cat)
        session.commit()
        session.refresh(cat)
        return cat


@router.get("/catalysts/{symbol}")
async def list_catalysts(symbol: str):
    with session_factory() as session:
        statement = select(Catalyst).where(
            Catalyst.symbol == symbol,
            Catalyst.status == "pending"
        ).order_by(Catalyst.expected_date)
        items = session.exec(statement).all()
        return {"items": items}


@router.patch("/catalysts/{catalyst_id}")
async def update_catalyst(catalyst_id: str, status: Optional[str] = None, actual_result: Optional[str] = None):
    with session_factory() as session:
        cat = session.get(Catalyst, catalyst_id)
        if not cat:
            raise HTTPException(404, "Catalyst not found")
        if status:
            cat.status = status
        if actual_result:
            cat.actual_result = actual_result
        session.add(cat)
        session.commit()
        session.refresh(cat)
        return cat
