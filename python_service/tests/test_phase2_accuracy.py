import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from app.services.mock_trading_service import MockTradingService
from app.services.backtest_engine_service import BacktestEngine
from app.services.screening_service import _screen_ashare_sync


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
from unittest.mock import AsyncMock
@patch('akshare.stock_zh_a_spot_em')
@patch('app.services.screening_service._filter_tickers_by_criteria_async', new_callable=AsyncMock)
def test_a_share_screening_flow(mock_filter, mock_ak):
    # Mock AkShare spot data
    mock_ak.return_value = pd.DataFrame([
        {"代码": "600519", "名称": "贵州茅台", "最新价": "1600.0", "市盈率-动态": "25.0", "市净率": "6.0", "涨跌幅": "1.5", "总市值": 2e12},
        {"代码": "000858", "名称": "五粮液", "最新价": "150.0", "市盈率-动态": "18.0", "市净率": "4.0", "涨跌幅": "-0.5", "总市值": 6e11},
    ])

    mock_filter.return_value = [
        {"symbol": "600519.SS", "price": 1600.0, "pe": 25.0, "pb": 6.0, "score": 90.0}
    ]

    criteria = {"pe_max": 30, "pb_max": 8.0}
    res = _screen_ashare_sync("growth", criteria, None, limit=10)

    assert len(res) == 1
    assert res[0]["symbol"] == "600519.SS"
    assert res[0]["name"] == "贵州茅台"
    # Verify A-share symbols got properly mapped to yfinance (.SS / .SZ)
    mock_filter.assert_called_once_with(["600519.SS", "000858.SZ"], criteria, 10)


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
