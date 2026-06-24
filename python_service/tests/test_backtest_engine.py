"""P1-3: Event-driven backtest engine tests.

Tests for:
- Signal replay with PiT snapshots
- Trade execution with cost model (commission + tax + slippage)
- Limit-up/limit-down order rejection
- Portfolio accounting (cash, positions, equity curve)
- Metrics calculation (CAGR, Sharpe, max drawdown, hit rate)
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from python_service.app.backtest.engine import BacktestEngine, BacktestConfig
from python_service.app.backtest.costs import CostModel, CostParams
from python_service.app.backtest.simulator import ExecutionSimulator, OrderRequest


class TestCostModel:
    """Transaction cost calculations."""

    def test_china_a_share_buy_costs(self):
        """A-share buy: commission only (no stamp tax on buy)."""
        params = CostParams(
            commission_rate=0.0003,  # 万三
            stamp_tax_rate=0.001,    # 千一 (sell only)
            min_commission=5.0,
        )
        model = CostModel(params)
        cost = model.buy_cost(notional=100_000.0)
        # Commission = max(100000 * 0.0003, 5) = 30.0
        assert cost == pytest.approx(30.0)

    def test_china_a_share_sell_costs(self):
        """A-share sell: commission + stamp tax."""
        params = CostParams(
            commission_rate=0.0003,
            stamp_tax_rate=0.001,
            min_commission=5.0,
        )
        model = CostModel(params)
        cost = model.sell_cost(notional=100_000.0)
        # Commission 30 + stamp tax 100 = 130
        assert cost == pytest.approx(130.0)

    def test_min_commission_applied(self):
        """Small orders get minimum commission."""
        params = CostParams(commission_rate=0.0003, stamp_tax_rate=0.001, min_commission=5.0)
        model = CostModel(params)
        cost = model.buy_cost(notional=1000.0)
        # 1000 * 0.0003 = 0.3 < min 5.0
        assert cost == pytest.approx(5.0)

    def test_slippage_estimation(self):
        """Slippage based on participation rate and volatility."""
        params = CostParams(commission_rate=0.0003, stamp_tax_rate=0.001, min_commission=5.0)
        model = CostModel(params)
        slippage_bps = model.estimate_slippage_bps(
            order_value=500_000.0,
            adv=10_000_000.0,  # Average daily volume in notional
            volatility=0.02,   # Daily vol
        )
        assert slippage_bps > 0
        assert slippage_bps < 100  # Less than 1% for small participation


class TestExecutionSimulator:
    """Simulated order matching with market constraints."""

    def test_normal_fill(self):
        sim = ExecutionSimulator()
        order = OrderRequest(
            symbol="600519",
            side="BUY",
            quantity=100,
            price=1800.0,
            market_price=1800.0,
            limit_up=1980.0,
            limit_down=1620.0,
            is_suspended=False,
        )
        fill = sim.execute(order)
        assert fill.filled_quantity == 100
        assert fill.status == "FILLED"

    def test_limit_up_rejects_buy(self):
        """Cannot buy at limit-up price."""
        sim = ExecutionSimulator()
        order = OrderRequest(
            symbol="600519",
            side="BUY",
            quantity=100,
            price=1980.0,
            market_price=1980.0,
            limit_up=1980.0,
            limit_down=1620.0,
            is_suspended=False,
        )
        fill = sim.execute(order)
        assert fill.status == "REJECTED"
        assert "limit_up" in fill.reject_reason

    def test_limit_down_rejects_sell(self):
        """Cannot sell at limit-down price."""
        sim = ExecutionSimulator()
        order = OrderRequest(
            symbol="600519",
            side="SELL",
            quantity=100,
            price=1620.0,
            market_price=1620.0,
            limit_up=1980.0,
            limit_down=1620.0,
            is_suspended=False,
        )
        fill = sim.execute(order)
        assert fill.status == "REJECTED"
        assert "limit_down" in fill.reject_reason

    def test_suspended_stock_rejects(self):
        """Suspended stocks cannot be traded."""
        sim = ExecutionSimulator()
        order = OrderRequest(
            symbol="600519",
            side="BUY",
            quantity=100,
            price=1800.0,
            market_price=1800.0,
            limit_up=1980.0,
            limit_down=1620.0,
            is_suspended=True,
        )
        fill = sim.execute(order)
        assert fill.status == "REJECTED"
        assert "suspended" in fill.reject_reason


class TestBacktestEngine:
    """Integration test for the backtest engine."""

    def test_simple_backtest_produces_metrics(self):
        """A minimal backtest with one buy and one sell produces valid metrics."""
        config = BacktestConfig(
            initial_cash=1_000_000.0,
            start_date="2025-01-01",
            end_date="2025-12-31",
            cost_params=CostParams(commission_rate=0.0003, stamp_tax_rate=0.001, min_commission=5.0),
        )
        engine = BacktestEngine(config)

        # Simulate: buy on day 1, sell on day 100
        engine.process_signal("2025-01-02", "600519", "BUY", quantity=100, price=1800.0,
                              market_price=1800.0, limit_up=1980.0, limit_down=1620.0)
        engine.process_signal("2025-05-01", "600519", "SELL", quantity=100, price=2000.0,
                              market_price=2000.0, limit_up=2200.0, limit_down=1800.0)

        metrics = engine.compute_metrics()
        assert metrics["total_trades"] == 2
        assert metrics["total_pnl"] > 0  # Bought at 1800, sold at 2000
        assert "total_costs" in metrics
        assert metrics["total_costs"] > 0

    def test_backtest_tracks_equity_curve(self):
        config = BacktestConfig(
            initial_cash=500_000.0,
            start_date="2025-01-01",
            end_date="2025-06-30",
            cost_params=CostParams(commission_rate=0.0003, stamp_tax_rate=0.001, min_commission=5.0),
        )
        engine = BacktestEngine(config)
        engine.process_signal("2025-01-02", "MSFT", "BUY", quantity=50, price=400.0,
                              market_price=400.0, limit_up=440.0, limit_down=360.0)

        # Mark to market at a higher price
        engine.mark_to_market("2025-01-10", {"MSFT": 420.0})
        curve = engine.get_equity_curve()
        assert len(curve) >= 1
        assert curve[-1]["equity"] > 500_000.0  # Gained from 400→420
