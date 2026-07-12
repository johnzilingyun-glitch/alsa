import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.mock_trading_service import MockTradingService
from app.services.backtest_engine_service import BacktestEngine
from app.services.screening_service import _fetch_ashare_candidates


# 1. Test Position cost basis math (Task 3)
def test_mock_trading_cost_basis():
    mock_repo = MagicMock()
    mock_account = MagicMock(initial_balance=100000.0, current_cash=100000.0, currency="CNY", status="active")
    mock_repo.get_account.return_value = mock_account
    mock_repo.get_position.return_value = None  # Initially flat
    mock_repo.get_today_bought_shares.return_value = 0

    service = MockTradingService(session=MagicMock())
    service.repo = mock_repo
    service._get_exchange_rate = MagicMock(return_value=1.0)

    # Multiples of 100 shares for A-Share
    res = service.execute_trade(
        account_id="test_acc",
        symbol="600519",
        market="A-Share",
        action="BUY",
        shares=100,
        execution_price=100.0,
        trigger_source="manual"
    )

    assert res is not None
    # total_cost = 100.0 * 100 + 5.0 = 10005.0. average_cost = 100.05
    mock_repo.upsert_position.assert_any_call("test_acc", "600519", "A-Share", 100, 100.05)


def test_mock_trading_cost_basis_add_long():
    mock_repo = MagicMock()
    mock_account = MagicMock(initial_balance=100000.0, current_cash=100000.0, currency="CNY", status="active")
    mock_repo.get_account.return_value = mock_account
    
    # Already holds 100 shares at 100.0
    existing_position = MagicMock(symbol="600519", market="A-Share", shares=100, average_cost=100.0)
    mock_repo.get_position.return_value = existing_position
    mock_repo.get_today_bought_shares.return_value = 0

    service = MockTradingService(session=MagicMock())
    service.repo = mock_repo
    service._get_exchange_rate = MagicMock(return_value=1.0)

    res = service.execute_trade(
        account_id="test_acc",
        symbol="600519",
        market="A-Share",
        action="BUY",
        shares=100,
        execution_price=100.0,
        trigger_source="manual"
    )

    assert res is not None
    # new_shares = 200
    # total_cost = (100 * 100.0) + (100 * 100.0) + 5.0 = 10000.0 + 10000.0 + 5.0 = 20005.0
    # average_cost = 20005.0 / 200 = 100.025
    mock_repo.upsert_position.assert_any_call("test_acc", "600519", "A-Share", 200, 100.025)


# 2. Test A-Share screening flow (Task 2)
@pytest.mark.skip(reason="Screening service needs refactoring for DataRouter format")
@patch('app.services.screening_service.data_router.get_history')
def test_a_share_screening_flow(mock_get_history):
    # Mock history data
    mock_get_history.return_value = pd.DataFrame([
        {"date": "2024-01-01", "open": 1500, "high": 1600, "low": 1450, "close": 1580, "volume": 1000000},
    ])

    # Test the data fetching function (runs in executor, no asyncio.run)
    result = _fetch_ashare_candidates("growth")
    
    assert result is not None
    assert "yf_tickers" in result
    assert "symbol_to_name" in result
    # Verify A-share symbols got properly mapped to yfinance (.SS / .SZ)
    assert "600519.SS" in result["yf_tickers"]
    assert "000858.SZ" in result["yf_tickers"]
    assert result["symbol_to_name"]["600519.SS"] == "贵州茅台"
    assert result["symbol_to_name"]["000858.SZ"] == "五粮液"


# 3. Test US Backtest Benchmark Calculations (Task 4)
@pytest.mark.anyio
@patch('yfinance.Ticker')
async def test_us_backtest_benchmark_metrics(mock_ticker_cls):
    # Mock index returns
    mock_ticker = MagicMock()
    mock_ticker_cls.return_value = mock_ticker
    
    # 2 years of daily index data
    dates = pd.date_range(start="2024-01-01", periods=20, freq="D")
    mock_ticker.history.return_value = pd.DataFrame({"Close": np.linspace(4000.0, 4200.0, 20)}, index=dates)

    service = BacktestEngine()
    
    # Mock strategy return details
    df = pd.DataFrame({"Close": np.linspace(100.0, 110.0, 20)}, index=dates)
    
    with patch('yfinance.download') as mock_download:
        mock_download.return_value = df
        
        # Test backtest runs via run
        res = await service.run("2024-01-01", "2024-01-20", "sma_crossover", "US", {"target_symbol": "SPY", "fast_window": 5, "slow_window": 10})
        
        assert res is not None
        assert "metrics" in res
        metrics = res["metrics"]
        assert "alpha" in metrics
        assert "beta" in metrics
        assert "treynor_ratio" in metrics
        assert "information_ratio" in metrics
        assert isinstance(metrics["alpha"], float)
        assert isinstance(metrics["beta"], float)
