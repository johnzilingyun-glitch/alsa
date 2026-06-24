import pytest
from unittest.mock import patch
import pandas as pd
from sqlmodel import Session, select
from app.db.database import engine, SQLModel
from app.db.models import DailyKline
from app.services.portfolio_real_backtest import PortfolioBacktester

@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.exec(DailyKline.__table__.delete())
        session.commit()
    yield
    with Session(engine) as session:
        session.exec(DailyKline.__table__.delete())
        session.commit()

def test_get_klines_cached():
    backtester = PortfolioBacktester()

    # Create dummy yfinance data
    dates = pd.date_range(start="2023-01-01", end="2023-01-05", freq="D")
    mock_df = pd.DataFrame(index=dates)
    mock_df["Close"] = [10.0, 10.5, 11.0, 10.8, 11.2]
    mock_df["Adj Close"] = [10.0, 10.5, 11.0, 10.8, 11.2]
    mock_df["Open"] = [9.9, 10.1, 10.6, 10.9, 10.7]
    mock_df["High"] = [10.1, 10.6, 11.1, 11.0, 11.3]
    mock_df["Low"] = [9.8, 10.0, 10.5, 10.7, 10.6]
    mock_df["Volume"] = [1000, 1500, 1200, 1100, 1300]
    
    # mock_df.columns = pd.MultiIndex.from_product([mock_df.columns, ["TEST.SS"]])

    with patch("app.services.portfolio_real_backtest.yf.download") as mock_yf:
        mock_yf.return_value = mock_df
        
        # 1. First call: Cache miss, should download from yfinance and save to DB
        closes1 = backtester.get_klines_cached(["TEST.SS"], "2023-01-01", "2023-01-05")
        
        assert mock_yf.called
        assert len(closes1) == 5
        assert "TEST.SS" in closes1.columns
        assert closes1["TEST.SS"].iloc[-1] == 11.2

        # Verify DB insertion
        with Session(engine) as session:
            count = session.exec(select(DailyKline).where(DailyKline.symbol == "TEST.SS")).all()
            assert len(count) == 5

        # 2. Second call: Cache hit, should NOT download from yfinance
        mock_yf.reset_mock()
        closes2 = backtester.get_klines_cached(["TEST.SS"], "2023-01-01", "2023-01-05")
        
        assert not mock_yf.called
        assert len(closes2) == 5
        assert "TEST.SS" in closes2.columns
        assert closes2["TEST.SS"].iloc[-1] == 11.2
