"""Tests for backtest costs and execution simulator."""
import pytest
import math
from python_service.app.backtest.costs import CostModel, CostParams
from python_service.app.backtest.simulator import ExecutionSimulator, OrderRequest, FillResult


# ────────────── Cost Model Tests ──────────────

class TestCostModel:
    """Test transaction cost calculations."""

    def test_buy_cost_commission_only(self):
        model = CostModel(CostParams())
        cost = model.buy_cost(100000)  # 10万
        # Commission = max(100000 * 0.0003, 5) = max(30, 5) = 30
        assert cost == pytest.approx(30.0)

    def test_buy_cost_minimum_commission(self):
        model = CostModel(CostParams())
        cost = model.buy_cost(1000)  # 1000元
        # Commission = max(1000 * 0.0003, 5) = max(0.3, 5) = 5
        assert cost == 5.0

    def test_sell_cost_includes_stamp_tax(self):
        model = CostModel(CostParams())
        cost = model.sell_cost(100000)
        # Commission = 30, Stamp tax = 100000 * 0.001 = 100
        assert cost == pytest.approx(130.0)

    def test_sell_cost_minimum_commission_plus_tax(self):
        model = CostModel(CostParams())
        cost = model.sell_cost(1000)
        # Commission = 5 (min), Stamp tax = 1
        assert cost == pytest.approx(6.0)

    def test_custom_cost_params(self):
        model = CostModel(CostParams(
            commission_rate=0.0005,  # 万五
            stamp_tax_rate=0.0005,  # 千0.5
            min_commission=0,
        ))
        buy = model.buy_cost(100000)
        assert buy == pytest.approx(50.0)
        sell = model.sell_cost(100000)
        assert sell == pytest.approx(100.0)  # 50 commission + 50 tax

    def test_sell_cost_always_greater_than_buy(self):
        model = CostModel(CostParams())
        for notional in [10000, 50000, 100000, 500000]:
            assert model.sell_cost(notional) > model.buy_cost(notional)


class TestSlippageEstimation:
    """Test market impact slippage estimation."""

    def test_basic_slippage(self):
        model = CostModel(CostParams())
        slippage = model.estimate_slippage_bps(
            order_value=100000,
            adv=10000000,  # ADV 1000万
            volatility=0.02,
        )
        assert slippage > 0
        assert slippage < 100  # Should be reasonable

    def test_illiquid_stock_penalty(self):
        model = CostModel(CostParams())
        slippage = model.estimate_slippage_bps(
            order_value=100000,
            adv=0,  # Zero ADV
            volatility=0.02,
        )
        assert slippage >= 55.0  # base_spread + illiquid penalty

    def test_larger_order_more_slippage(self):
        model = CostModel(CostParams())
        small = model.estimate_slippage_bps(10000, 10000000, 0.02)
        large = model.estimate_slippage_bps(1000000, 10000000, 0.02)
        assert large > small

    def test_higher_volatility_more_slippage(self):
        model = CostModel(CostParams())
        low_vol = model.estimate_slippage_bps(100000, 10000000, 0.01)
        high_vol = model.estimate_slippage_bps(100000, 10000000, 0.05)
        assert high_vol > low_vol


# ────────────── Execution Simulator Tests ──────────────

class TestExecutionSimulator:
    """Test order execution simulation."""

    def _make_order(self, **kwargs):
        defaults = {
            "symbol": "600519",
            "side": "BUY",
            "quantity": 100,
            "price": 1800,
            "market_price": 1800,
            "limit_up": 1980,
            "limit_down": 1620,
        }
        defaults.update(kwargs)
        return OrderRequest(**defaults)

    def test_normal_buy_fills(self):
        sim = ExecutionSimulator()
        order = self._make_order(side="BUY", market_price=1800)
        result = sim.execute(order)
        assert result.status == "FILLED"
        assert result.filled_quantity == 100
        assert result.fill_price == 1800

    def test_normal_sell_fills(self):
        sim = ExecutionSimulator()
        order = self._make_order(side="SELL", market_price=1800)
        result = sim.execute(order)
        assert result.status == "FILLED"
        assert result.filled_quantity == 100

    def test_suspended_stock_rejected(self):
        sim = ExecutionSimulator()
        order = self._make_order(is_suspended=True)
        result = sim.execute(order)
        assert result.status == "REJECTED"
        assert result.reject_reason == "suspended"
        assert result.filled_quantity == 0

    def test_buy_at_limit_up_rejected(self):
        sim = ExecutionSimulator()
        order = self._make_order(
            side="BUY",
            market_price=1980,  # At limit up
            limit_up=1980,
        )
        result = sim.execute(order)
        assert result.status == "REJECTED"
        assert result.reject_reason == "limit_up"

    def test_sell_at_limit_down_rejected(self):
        sim = ExecutionSimulator()
        order = self._make_order(
            side="SELL",
            market_price=1620,  # At limit down
            limit_down=1620,
        )
        result = sim.execute(order)
        assert result.status == "REJECTED"
        assert result.reject_reason == "limit_down"

    def test_buy_below_limit_up_fills(self):
        sim = ExecutionSimulator()
        order = self._make_order(
            side="BUY",
            market_price=1979,  # Just below limit up
            limit_up=1980,
        )
        result = sim.execute(order)
        assert result.status == "FILLED"

    def test_sell_above_limit_down_fills(self):
        sim = ExecutionSimulator()
        order = self._make_order(
            side="SELL",
            market_price=1621,  # Just above limit down
            limit_down=1620,
        )
        result = sim.execute(order)
        assert result.status == "FILLED"

    def test_fill_result_contains_symbol(self):
        sim = ExecutionSimulator()
        order = self._make_order(symbol="000001")
        result = sim.execute(order)
        assert result.symbol == "000001"
