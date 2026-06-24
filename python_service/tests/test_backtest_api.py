import pytest
from fastapi.testclient import TestClient
import os
import time

from python_service.main import app
from python_service.app.api.backtest import RESULTS_FILE

client = TestClient(app)

# Bypass API token dependency check for testing if needed
# The main.py includes dependecies=[Depends(require_api_token)] on router, but wait!
# Let's see how other tests bypass or handle security tokens.
# Let's check headers in other API tests.

def test_backtest_api_flow():
    # Clear RESULTS_FILE if it exists
    if os.path.exists(RESULTS_FILE):
        try:
            os.remove(RESULTS_FILE)
        except Exception:
            pass

    # Custom configuration parameters
    payload = {
        "start_date": "2020-01-01",
        "end_date": "2020-06-30",
        "model": "MockAgent",
        "market": "CN",
        "config": {
            "initial_capital": 123456.0,
            "commission": 0.0005,
            "strategy_params": {
                "fast_window": 8,
                "slow_window": 24
            }
        }
    }

    # Trigger backtest run
    # Note: main app requires authorization header if it is enabled.
    headers = {"Authorization": "Bearer mock-token"}  # Or check security config
    response = client.post("/api/backtest/run", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "started"

    # Wait for results to be written (background task)
    max_wait = 10
    results_data = None
    for _ in range(max_wait):
        time.sleep(1)
        res_response = client.get("/api/backtest/results", headers=headers)
        assert res_response.status_code == 200
        data = res_response.json()
        if data["status"] == "completed":
            results_data = data["data"]
            break
        elif data["status"] == "error":
            pytest.fail(f"Backtest engine failed: {data.get('message')}")

    assert results_data is not None, "Backtest did not complete in time"
    
    # Assertions on custom parameters
    assert results_data["start_date"] == "2020-01-01"
    assert results_data["end_date"] == "2020-06-30"
    assert results_data["model"] == "MockAgent"
    assert results_data["market"] == "CN"
    
    # Check that initial capital is correctly reflected (or close to it)
    # The stats end_balance or final_account or snapshots should relate to it
    assert "final_account" in results_data


def test_backtest_api_us_shares():
    # Clear RESULTS_FILE if it exists
    if os.path.exists(RESULTS_FILE):
        try:
            os.remove(RESULTS_FILE)
        except Exception:
            pass

    payload = {
        "start_date": "2021-01-01",
        "end_date": "2021-06-30",
        "model": "MockAgent",
        "market": "US",
        "config": {
            "initial_capital": 200000.0,
            "commission": 0.0003,
            "target_symbol": "AAPL",
            "strategy_params": {
                "fast_window": 5,
                "slow_window": 20
            }
        }
    }

    headers = {"Authorization": "Bearer mock-token"}
    response = client.post("/api/backtest/run", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "started"

    # Wait for results to be written (background task)
    max_wait = 20
    results_data = None
    for _ in range(max_wait):
        time.sleep(1)
        res_response = client.get("/api/backtest/results", headers=headers)
        assert res_response.status_code == 200
        data = res_response.json()
        if data["status"] == "completed":
            results_data = data["data"]
            break
        elif data["status"] == "error":
            pytest.fail(f"Backtest engine failed: {data.get('message')}")

    assert results_data is not None, "Backtest did not complete in time"
    assert results_data["start_date"] == "2021-01-01"
    assert results_data["end_date"] == "2021-06-30"
    assert results_data["model"] == "MockAgent"
    assert results_data["market"] == "US"
    assert "final_account" in results_data


def test_backtest_api_custom_rule():
    # Clear RESULTS_FILE if it exists
    if os.path.exists(RESULTS_FILE):
        try:
            os.remove(RESULTS_FILE)
        except Exception:
            pass

    payload = {
        "start_date": "2020-01-01",
        "end_date": "2020-06-30",
        "model": "custom_rule",
        "market": "CN",
        "config": {
            "initial_capital": 1000000.0,
            "commission": 0.0003,
            "target_symbol": "600519",
            "strategy_params": {
                "buy_rules": [
                    {"type": "pe_below", "pe_max": 40.0},
                    {"type": "rsi_oversold", "rsi_period": 14, "rsi_threshold": 50.0},
                    {"type": "momentum_above", "momentum_period": 10, "momentum_threshold": -50.0},
                    {"type": "volatility_above", "volatility_period": 10, "volatility_threshold": 0.01},
                    {"type": "beta_above", "beta_period": 10, "beta_threshold": -1.0}
                ],
                "sell_rules": [
                    {"type": "rsi_overbought", "rsi_period": 14, "rsi_threshold": 70.0},
                    {"type": "momentum_below", "momentum_period": 10, "momentum_threshold": 50.0},
                    {"type": "volatility_below", "volatility_period": 10, "volatility_threshold": 100.0},
                    {"type": "beta_below", "beta_period": 10, "beta_threshold": 1.0}
                ],
                "position_mode": "fixed_shares",
                "position_value": 100.0,
                "stop_loss_pct": 5.0,
                "take_profit_pct": 15.0,
                "trailing_stop_pct": 0.0
            }
        }
    }

    headers = {"Authorization": "Bearer mock-token"}
    response = client.post("/api/backtest/run", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "started"

    # Wait for results to be written (background task)
    max_wait = 20
    results_data = None
    for _ in range(max_wait):
        time.sleep(1)
        res_response = client.get("/api/backtest/results", headers=headers)
        assert res_response.status_code == 200
        data = res_response.json()
        if data["status"] == "completed":
            results_data = data["data"]
            break
        elif data["status"] == "error":
            pytest.fail(f"Backtest engine failed: {data.get('message')}")

    assert results_data is not None, "Backtest did not complete in time"
    assert results_data["start_date"] == "2020-01-01"
    assert results_data["end_date"] == "2020-06-30"
    assert results_data["model"] == "custom_rule"
    assert results_data["market"] == "CN"
    assert "final_account" in results_data
    assert "trades" in results_data
    
    # Assert existence of new risk & performance metrics
    metrics = results_data.get("metrics", {})
    assert "calmar_ratio" in metrics
    assert "sortino_ratio" in metrics
    assert "profit_factor" in metrics
    assert "profit_loss_ratio" in metrics
    assert "max_consecutive_loss" in metrics
    assert "avg_holding_days" in metrics


def test_backtest_api_portfolio_cross_sectional():
    # Clear RESULTS_FILE if it exists
    if os.path.exists(RESULTS_FILE):
        try:
            os.remove(RESULTS_FILE)
        except Exception:
            pass

    payload = {
        "start_date": "2020-01-01",
        "end_date": "2020-06-30",
        "model": "portfolio_cross_sectional",
        "market": "CN",
        "config": {
            "initial_capital": 1000000.0,
            "commission": 0.0003,
            "strategy_params": {
                "rebalance_interval": 63,
                "custom_symbols": [
                    "600519.SS", "601398.SS", "600036.SS", "601318.SS",
                    "000858.SZ", "000333.SZ", "600900.SS", "601012.SS"
                ]
            }
        }
    }

    headers = {"Authorization": "Bearer mock-token"}
    response = client.post("/api/backtest/run", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "started"

    # Wait for results to be written (background task)
    max_wait = 25
    results_data = None
    for _ in range(max_wait):
        time.sleep(1)
        res_response = client.get("/api/backtest/results", headers=headers)
        assert res_response.status_code == 200
        data = res_response.json()
        if data["status"] == "completed":
            results_data = data["data"]
            break
        elif data["status"] == "error":
            pytest.fail(f"Backtest engine failed: {data.get('message')}")

    assert results_data is not None, "Backtest did not complete in time"
    assert results_data["start_date"] == "2020-01-01"
    assert results_data["end_date"] == "2020-06-30"
    assert results_data["model"] in ("portfolio_cross_sectional_pandas", "portfolio_cross_sectional_vnpy")
    assert results_data["market"] == "CN"
    assert "final_account" in results_data
    assert "snapshots" in results_data
    assert "trades" in results_data
    
    # Assert existence of new risk & performance metrics
    metrics = results_data.get("metrics", {})
    assert "calmar_ratio" in metrics
    assert "sortino_ratio" in metrics
    assert "profit_factor" in metrics
    assert "profit_loss_ratio" in metrics
    assert "max_consecutive_loss" in metrics
    assert "avg_holding_days" in metrics


