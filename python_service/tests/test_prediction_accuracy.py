import pytest
from datetime import timedelta
import pandas as pd
from unittest.mock import AsyncMock, patch
from sqlmodel import Session
from app.db.models import PredictionRecord
from app.services.prediction_service import PredictionService
from app.time_utils import utc_now

def test_get_horizon_days():
    assert PredictionService.get_horizon_days("1_month") == 30
    assert PredictionService.get_horizon_days("3_months") == 90
    assert PredictionService.get_horizon_days("6_months") == 180
    assert PredictionService.get_horizon_days("1_year") == 365
    assert PredictionService.get_horizon_days("10_days") == 10
    assert PredictionService.get_horizon_days("2_years") == 730
    assert PredictionService.get_horizon_days("unknown_format") == 30

@pytest.mark.asyncio
async def test_evaluate_pending_predictions(tmp_path):
    # Setup test DB (using session_factory from main application but we can patch session_factory or run inside the transaction)
    # We patch session_factory to use a clean SQLite memory database or similar.
    from sqlmodel import create_engine, SQLModel
    
    test_db_path = tmp_path / "test_prediction.db"
    test_engine = create_engine(f"sqlite:///{test_db_path}")
    SQLModel.metadata.create_all(test_engine)
    
    mock_session_factory = lambda: Session(test_engine)
    
    # Insert mock records
    now_dt = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    past_dt = now_dt - timedelta(days=32)
    
    with mock_session_factory() as session:
        # Record 1: expired, target price higher than initial
        pred1 = PredictionRecord(
            prediction_id="p1",
            job_id="job1",
            symbol="AAPL",
            market="US",
            target_price=160.0,
            time_horizon="1_month",
            status="pending",
            current_price_at_prediction=150.0,
            created_at=past_dt
        )
        # Record 2: not expired yet
        pred2 = PredictionRecord(
            prediction_id="p2",
            job_id="job2",
            symbol="MSFT",
            market="US",
            target_price=350.0,
            time_horizon="1_month",
            status="pending",
            current_price_at_prediction=300.0,
            created_at=now_dt
        )
        session.add(pred1)
        session.add(pred2)
        session.commit()

    # Mock data_router.get_history
    # Horizon date is past_dt + 30 days = now_dt - 2 days.
    horizon_dt_naive = (past_dt + timedelta(days=30)).replace(tzinfo=None)
    
    mock_history_df = pd.DataFrame([
        {"date": (horizon_dt_naive - timedelta(days=1)).strftime("%Y-%m-%d"), "close": 155.0},
        {"date": horizon_dt_naive.strftime("%Y-%m-%d"), "close": 158.0},
        {"date": (horizon_dt_naive + timedelta(days=1)).strftime("%Y-%m-%d"), "close": 159.0},
    ])
    
    with patch("app.services.prediction_service.session_factory", mock_session_factory), \
         patch("app.services.prediction_service.data_router.get_history", AsyncMock(return_value=mock_history_df)):
         
        await PredictionService.evaluate_pending_predictions()
        
    # Check results
    with mock_session_factory() as session:
        p1_db = session.get(PredictionRecord, "p1")
        p2_db = session.get(PredictionRecord, "p2")
        
        assert p1_db.status == "evaluated"
        assert p1_db.actual_price_at_horizon == 158.0
        assert p1_db.accuracy_score is not None
        assert p1_db.accuracy_score > 0
        
        assert p2_db.status == "pending"
        assert p2_db.actual_price_at_horizon is None
