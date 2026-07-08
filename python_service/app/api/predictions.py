from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from typing import List, Optional
from datetime import timedelta
from ..db.database import get_session
from ..db.models import PredictionRecord
from ..time_utils import utc_now

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


from ..services.market_data_service import market_data_service


def _get_horizon_days(horizon: str) -> int:
    """Parse time_horizon string to days."""
    if horizon == "1_month":
        return 30
    elif horizon == "3_months":
        return 90
    elif horizon == "6_months":
        return 180
    elif horizon == "1_year":
        return 365
    try:
        parts = horizon.split("_")
        num = int(parts[0])
        unit = parts[1] if len(parts) > 1 else "days"
        if unit.startswith("day"):
            return num
        elif unit.startswith("month"):
            return num * 30
        elif unit.startswith("year"):
            return num * 365
    except Exception:
        pass
    return 30


def _calc_accuracy(initial: float, target: float, actual: float) -> float:
    """Calculate accuracy score (0-100) for a prediction."""
    expected_direction = 1 if target > initial else -1 if target < initial else 0
    actual_direction = 1 if actual > initial else -1 if actual < initial else 0

    if expected_direction == 0:
        deviation = abs(actual - initial) / initial if initial else 0
        return max(0, 100 - deviation * 1000)

    expected_move = abs(target - initial) / initial if initial else 0
    actual_move = (actual - initial) / initial if initial else 0

    if expected_direction != actual_direction:
        if expected_move > 0:
            return max(0, 50 - (abs(actual_move) / expected_move) * 50)
        return 0

    target_diff = abs(actual - target) / target if target else 0
    return max(0, 100 - (target_diff * 200))


@router.post("/auto_evaluate")
async def auto_evaluate_predictions(session: Session = Depends(get_session)):
    query = select(PredictionRecord).where(PredictionRecord.status == "pending")
    pending_preds = session.exec(query).all()
    if not pending_preds:
        return {"evaluated": 0, "status": "No pending predictions"}

    # Gather symbols
    symbols = list(set([p.symbol for p in pending_preds]))
    quotes = await market_data_service.get_quotes(symbols)
    price_map = {q["symbol"]: q.get("price") for q in quotes if q.get("price")}

    now_dt = utc_now()
    evaluated_count = 0
    for pred in pending_preds:
        current_price = price_map.get(pred.symbol)
        if not current_price:
            continue

        # Update MFE/MAE
        if pred.highest_price_reached is None or current_price > pred.highest_price_reached:
            pred.highest_price_reached = current_price
        if pred.lowest_price_reached is None or current_price < pred.lowest_price_reached:
            pred.lowest_price_reached = current_price

        is_short = pred.target_price < pred.current_price_at_prediction

        target_hit = False
        stop_hit = False
        if is_short:
            if current_price <= pred.target_price:
                target_hit = True
            if pred.stop_loss and current_price >= pred.stop_loss:
                stop_hit = True
        else:
            if current_price >= pred.target_price:
                target_hit = True
            if pred.stop_loss and current_price <= pred.stop_loss:
                stop_hit = True

        # Check if time horizon has passed
        days = _get_horizon_days(pred.time_horizon)
        horizon_dt = pred.created_at.replace(tzinfo=None) + timedelta(days=days)
        horizon_reached = now_dt.replace(tzinfo=None) >= horizon_dt

        should_evaluate = target_hit or stop_hit or horizon_reached

        if should_evaluate:
            pred.actual_price_at_horizon = current_price
            pred.status = "evaluated"

            if target_hit:
                pred.accuracy_score = 100.0
            elif stop_hit:
                pred.accuracy_score = 0.0
            else:
                # Horizon reached without hitting target/stop
                pred.accuracy_score = _calc_accuracy(
                    pred.current_price_at_prediction, pred.target_price, current_price
                )

            session.add(pred)
            evaluated_count += 1
        else:
            session.add(pred)  # save highest/lowest

    session.commit()
    return {"evaluated": evaluated_count, "status": "success"}


@router.post("/{prediction_id}/evaluate", response_model=PredictionRecord)
async def evaluate_prediction(
    prediction_id: str,
    session: Session = Depends(get_session)
):
    pred = session.get(PredictionRecord, prediction_id)
    if not pred:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Prediction not found")

    # Fetch real-time price
    quotes = await market_data_service.get_quotes([pred.symbol])
    if not quotes or not quotes[0].get("price"):
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Could not fetch real-time price")

    actual_price = quotes[0]["price"]

    pred.actual_price_at_horizon = actual_price

    # Calculate accuracy score
    initial = pred.current_price_at_prediction
    target = pred.target_price

    expected_direction = 1 if target > initial else -1 if target < initial else 0
    actual_direction = 1 if actual_price > initial else -1 if actual_price < initial else 0

    if expected_direction == 0:
        deviation = abs(actual_price - initial) / initial
        score = max(0, 100 - deviation * 1000)
    else:
        expected_move = abs(target - initial) / initial
        actual_move = (actual_price - initial) / initial

        if expected_direction != actual_direction:
            score = max(0, 50 - (abs(actual_move) / expected_move) * 50 if expected_move > 0 else 0)
        else:
            target_diff = abs(actual_price - target) / target
            score = max(0, 100 - (target_diff * 200))

    pred.accuracy_score = score
    pred.status = "evaluated"
    session.add(pred)
    session.commit()
    session.refresh(pred)
    return pred


@router.post("/{prediction_id}/reset", response_model=PredictionRecord)
async def reset_prediction(
    prediction_id: str,
    session: Session = Depends(get_session)
):
    """Reset a prediction back to pending status for continued tracking."""
    pred = session.get(PredictionRecord, prediction_id)
    if not pred:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Prediction not found")

    pred.status = "pending"
    pred.actual_price_at_horizon = None
    pred.accuracy_score = None
    session.add(pred)
    session.commit()
    session.refresh(pred)
    return pred
