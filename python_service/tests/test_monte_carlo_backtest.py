"""Tests for MonteCarloBacktester — Monte Carlo simulation for strategy robustness."""
import pytest
import pandas as pd
import numpy as np
from python_service.app.services.monte_carlo_backtest import MonteCarloBacktester


def _make_price_data(n=200):
    """Generate synthetic price data."""
    np.random.seed(42)
    dates = pd.date_range('2025-01-01', periods=n)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)  # Prevent negative prices
    return pd.DataFrame({'Close': close, 'Date': dates}).set_index('Date')


def _simple_strategy(df):
    """A simple buy-and-hold strategy for testing."""
    if len(df) < 2:
        return {'total_return': 0, 'sharpe': 0, 'max_drawdown': 0}
    returns = df['Close'].pct_change().dropna()
    total_return = (df['Close'].iloc[-1] / df['Close'].iloc[0]) - 1
    sharpe = returns.mean() / (returns.std() + 1e-10) * np.sqrt(252)
    # Max drawdown
    peak = df['Close'].cummax()
    drawdown = (df['Close'] - peak) / peak
    max_dd = drawdown.min()
    return {
        'total_return': float(total_return),
        'sharpe': float(sharpe),
        'max_drawdown': float(max_dd),
    }


def _failing_strategy(df):
    """A strategy that always raises an error."""
    raise ValueError("Strategy failed")


class TestMonteCarloBacktester:
    """Test Monte Carlo backtesting engine."""

    @pytest.mark.asyncio
    async def test_basic_backtest(self):
        mc = MonteCarloBacktester(n_simulations=50, random_seed=42)
        data = _make_price_data()
        results = await mc.run_backtest(data, _simple_strategy)

        assert "error" not in results
        assert results["n_simulations"] == 50
        assert results["n_successful"] > 0
        assert "return_stats" in results
        assert "risk_metrics" in results
        assert "sharpe_stats" in results
        assert "probabilities" in results

    @pytest.mark.asyncio
    async def test_return_stats_structure(self):
        mc = MonteCarloBacktester(n_simulations=30, random_seed=123)
        data = _make_price_data()
        results = await mc.run_backtest(data, _simple_strategy)

        ret = results["return_stats"]
        assert "mean" in ret
        assert "std" in ret
        assert "min" in ret
        assert "max" in ret
        assert "median" in ret
        assert ret["min"] <= ret["median"] <= ret["max"]

    @pytest.mark.asyncio
    async def test_probability_stats(self):
        mc = MonteCarloBacktester(n_simulations=30, random_seed=42)
        data = _make_price_data()
        results = await mc.run_backtest(data, _simple_strategy)

        prob = results["probabilities"]
        assert 0 <= prob["probability_of_profit"] <= 1
        assert 0 <= prob["probability_of_loss_gt_10pct"] <= 1
        assert 0 <= prob["probability_of_sharpe_gt_1"] <= 1

    @pytest.mark.asyncio
    async def test_all_simulations_fail(self):
        mc = MonteCarloBacktester(n_simulations=10, random_seed=42)
        data = _make_price_data()
        results = await mc.run_backtest(data, _failing_strategy)

        assert "error" in results
        assert results["n_successful"] == 0

    @pytest.mark.asyncio
    async def test_var_computation(self):
        mc = MonteCarloBacktester(n_simulations=100, random_seed=42)
        data = _make_price_data()
        results = await mc.run_backtest(data, _simple_strategy, confidence_level=0.95)

        risk = results["risk_metrics"]
        assert "var_95" in risk
        assert "cvar_95" in risk
        # CVaR should be <= VaR (more negative or equal)
        assert risk["cvar_95"] <= risk["var_95"]


class TestAddNoise:
    """Test noise injection logic."""

    def test_price_noise_changes_close(self):
        mc = MonteCarloBacktester(random_seed=42)
        data = _make_price_data(50)
        noisy = mc._add_noise(data, slippage_range=0.05, timing_range=0)
        # Prices should be different (within 5%)
        assert not data['Close'].equals(noisy['Close'])

    def test_zero_noise_preserves_data(self):
        mc = MonteCarloBacktester(random_seed=42)
        data = _make_price_data(50)
        noisy = mc._add_noise(data, slippage_range=0, timing_range=0)
        # With zero slippage, prices should be multiplied by ~1.0
        # (uniform(1, 1) = 1.0)
        pd.testing.assert_series_equal(data['Close'], noisy['Close'])


class TestGenerateReport:
    """Test report generation."""

    @pytest.mark.asyncio
    async def test_success_report(self):
        mc = MonteCarloBacktester(n_simulations=20, random_seed=42)
        data = _make_price_data()
        results = await mc.run_backtest(data, _simple_strategy)
        report = mc.generate_report(results)

        assert "蒙特卡洛回测报告" in report
        assert "模拟次数" in report
        assert "平均收益" in report
        assert "VaR" in report

    def test_error_report(self):
        mc = MonteCarloBacktester()
        results = {"error": "All simulations failed"}
        report = mc.generate_report(results)
        assert "回测失败" in report


class TestReproducibility:
    """Test that random seed ensures reproducibility."""

    @pytest.mark.asyncio
    async def test_same_seed_same_results(self):
        data = _make_price_data()

        mc1 = MonteCarloBacktester(n_simulations=20, random_seed=42)
        results1 = await mc1.run_backtest(data, _simple_strategy)

        mc2 = MonteCarloBacktester(n_simulations=20, random_seed=42)
        results2 = await mc2.run_backtest(data, _simple_strategy)

        assert results1["return_stats"]["mean"] == pytest.approx(
            results2["return_stats"]["mean"], abs=1e-6
        )
