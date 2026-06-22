from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Any
from sqlmodel import select, Session
from datetime import datetime
import json

from ..db.database import get_session
from ..db.models import ReflectionMemory

router = APIRouter(prefix="/reflections", tags=["reflections"])

class ReflectionCreate(BaseModel):
    symbol: str
    date: str
    recommendation: str
    score: float
    outcome_status: str
    outcome_return: str
    lessons: List[str]
    agent_reflections: List[dict]
    market_context: str

@router.post("/")
async def create_reflection(
    payload: ReflectionCreate,
    session: Session = Depends(get_session)
):
    try:
        new_memory = ReflectionMemory(
            symbol=payload.symbol,
            date=payload.date,
            recommendation=payload.recommendation,
            score=payload.score,
            outcome_status=payload.outcome_status,
            outcome_return=payload.outcome_return,
            lessons=json.dumps(payload.lessons),
            agent_reflections=json.dumps(payload.agent_reflections),
            market_context=payload.market_context
        )
        session.add(new_memory)
        session.commit()
        session.refresh(new_memory)
        return {"success": True, "id": new_memory.reflection_id}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def get_reflections(
    symbol: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    try:
        query = select(ReflectionMemory)
        if symbol:
            query = query.where(ReflectionMemory.symbol == symbol.upper())
        query = query.order_by(ReflectionMemory.created_at.desc()).limit(limit)
        
        results = session.exec(query).all()
        
        parsed_results = []
        for r in results:
            parsed_results.append({
                "id": r.reflection_id,
                "symbol": r.symbol,
                "date": r.date,
                "recommendation": r.recommendation,
                "score": r.score,
                "outcome_status": r.outcome_status,
                "outcome_return": r.outcome_return,
                "lessons": json.loads(r.lessons),
                "agent_reflections": json.loads(r.agent_reflections),
                "market_context": r.market_context,
                "created_at": r.created_at.isoformat()
            })
            
        return parsed_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
