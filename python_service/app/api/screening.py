"""Idea Screening API — Multi-factor stock screening endpoint."""
from fastapi import APIRouter, Query
from typing import Optional, Dict, Any
from pydantic import BaseModel
from ..services.screening_service import run_screen, SCREEN_PRESETS

router = APIRouter(prefix="/screen", tags=["screening"])


class ScreenRequest(BaseModel):
    screen_type: str = "value"  # value/growth/quality/short/momentum
    market: str = "US"  # US/A-Share
    sector: Optional[str] = None
    custom_criteria: Optional[Dict[str, Any]] = None
    limit: int = 20


@router.get("/presets")
async def get_presets():
    """Get available screening presets and their criteria."""
    return {"presets": SCREEN_PRESETS}


@router.post("/")
async def execute_screen(request: ScreenRequest):
    """Execute a stock screen with preset or custom criteria."""
    result = await run_screen(
        screen_type=request.screen_type,
        market=request.market,
        sector=request.sector,
        custom_criteria=request.custom_criteria,
        limit=request.limit
    )
    return result
