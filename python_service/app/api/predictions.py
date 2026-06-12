from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from typing import List, Optional
from ..db.sqlite import get_session
from ..db.models import PredictionRecord
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/predictions", tags=["Predictions"])

@router.get("/", response_model=List[PredictionRecord])
def list_predictions(
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    query = select(PredictionRecord)
    if symbol:
        query = query.where(PredictionRecord.symbol == symbol)
    if status:
        query = query.where(PredictionRecord.status == status)
    
    query = query.order_by(PredictionRecord.created_at.desc())
    results = session.exec(query).all()
    return results

@router.post("/{prediction_id}/evaluate", response_model=PredictionRecord)
def evaluate_prediction(
    prediction_id: str,
    actual_price: float,
    session: Session = Depends(get_session)
):
    pred = session.get(PredictionRecord, prediction_id)
    if not pred:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Prediction not found")
    
    pred.actual_price_at_horizon = actual_price
    
    # Calculate accuracy score
    # Simple logic: closer to target price = higher score (0-100)
    initial = pred.current_price_at_prediction
    target = pred.target_price
    
    # Direction
    expected_direction = 1 if target > initial else -1 if target < initial else 0
    actual_direction = 1 if actual_price > initial else -1 if actual_price < initial else 0
    
    if expected_direction == 0:
        # Holding strategy, any major deviation is bad
        deviation = abs(actual_price - initial) / initial
        score = max(0, 100 - deviation * 1000)
    else:
        # Expected move %
        expected_move = abs(target - initial) / initial
        actual_move = (actual_price - initial) / initial
        
        if expected_direction != actual_direction:
            # Wrong direction!
            score = max(0, 50 - (abs(actual_move) / expected_move) * 50 if expected_move > 0 else 0)
        else:
            # Right direction, calculate how close to target
            target_diff = abs(actual_price - target) / target
            score = max(0, 100 - (target_diff * 200)) # 5% off target = 90 score
            
    pred.accuracy_score = score
    pred.status = "evaluated"
    session.add(pred)
    session.commit()
    session.refresh(pred)
    return pred
