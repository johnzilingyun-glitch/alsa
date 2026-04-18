from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from ..db.repositories.alert_repo import AlertRepository

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

@router.delete("/{alert_id}")
async def delete_alert(alert_id: int, repo: AlertRepository = Depends(get_repo)):
    repo.delete_by_id(alert_id)
    return {"success": True}

@router.patch("/{alert_id}/status")
async def update_alert_status(alert_id: int, status: str, repo: AlertRepository = Depends(get_repo)):
    repo.update_status(alert_id, status)
    return {"success": True}
