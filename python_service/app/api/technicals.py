from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from ..quant.polars_indicators import compute_indicator_frame

router = APIRouter()

class IndicatorRequest(BaseModel):
    data: List[Dict[str, Any]]

@router.post("/indicators/calculate")
async def calculate_indicators(request: IndicatorRequest):
    try:
        df = compute_indicator_frame(request.data)
        if df.is_empty():
            return {"success": False, "error": "Unable to compute indicators"}
        return {"success": True, "data": df.to_dicts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
