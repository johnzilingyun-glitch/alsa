"""P2-2: Reconciliation — daily position/cash/fill audit.

Tests for:
- Position reconciliation between internal ledger and broker
- Cash reconciliation
- Fill matching (internal order → broker fill)
- Discrepancy detection and reporting
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from python_service.app.reconciliation.engine import (
    ReconciliationEngine,
    InternalPosition,
    BrokerPosition,
    ReconciliationResult,
    Discrepancy,
)


class TestReconciliationEngine:
    """Verify daily account reconciliation."""

    def test_matching_positions_pass(self):
        """No discrepancy when internal and broker agree."""
        engine = ReconciliationEngine()
        result = engine.reconcile_positions(
            internal=[
                InternalPosition(symbol="MSFT", quantity=100, avg_cost=400.0),
                InternalPosition(symbol="AAPL", quantity=50, avg_cost=180.0),
            ],
            broker=[
                BrokerPosition(symbol="MSFT", quantity=100, market_value=42000.0),
                BrokerPosition(symbol="AAPL", quantity=50, market_value=9500.0),
            ],
        )
        assert result.is_reconciled
        assert result.discrepancies == []

    def test_quantity_mismatch_detected(self):
        """Detect when internal quantity differs from broker."""
        engine = ReconciliationEngine()
        result = engine.reconcile_positions(
            internal=[InternalPosition(symbol="MSFT", quantity=100, avg_cost=400.0)],
            broker=[BrokerPosition(symbol="MSFT", quantity=95, market_value=39900.0)],
        )
        assert not result.is_reconciled
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].symbol == "MSFT"
        assert result.discrepancies[0].field == "quantity"

    def test_missing_position_in_broker(self):
        """Detect internal position not reflected in broker."""
        engine = ReconciliationEngine()
        result = engine.reconcile_positions(
            internal=[
                InternalPosition(symbol="MSFT", quantity=100, avg_cost=400.0),
                InternalPosition(symbol="TSLA", quantity=20, avg_cost=250.0),
            ],
            broker=[
                BrokerPosition(symbol="MSFT", quantity=100, market_value=42000.0),
            ],
        )
        assert not result.is_reconciled
        assert any(d.symbol == "TSLA" and d.field == "missing_in_broker" for d in result.discrepancies)

    def test_extra_position_in_broker(self):
        """Detect broker position not in internal ledger."""
        engine = ReconciliationEngine()
        result = engine.reconcile_positions(
            internal=[InternalPosition(symbol="MSFT", quantity=100, avg_cost=400.0)],
            broker=[
                BrokerPosition(symbol="MSFT", quantity=100, market_value=42000.0),
                BrokerPosition(symbol="NVDA", quantity=30, market_value=36000.0),
            ],
        )
        assert not result.is_reconciled
        assert any(d.symbol == "NVDA" and d.field == "missing_in_internal" for d in result.discrepancies)

    def test_cash_reconciliation_pass(self):
        engine = ReconciliationEngine()
        result = engine.reconcile_cash(internal_cash=500_000.0, broker_cash=500_000.0, tolerance=0.01)
        assert result.is_reconciled

    def test_cash_reconciliation_fail(self):
        engine = ReconciliationEngine()
        result = engine.reconcile_cash(internal_cash=500_000.0, broker_cash=498_000.0, tolerance=0.001)
        assert not result.is_reconciled
        assert any("cash" in d.field for d in result.discrepancies)

    def test_cash_within_tolerance_passes(self):
        """Small rounding differences within tolerance should pass."""
        engine = ReconciliationEngine()
        # 0.1% tolerance: 500000 * 0.001 = 500 allowed diff
        result = engine.reconcile_cash(internal_cash=500_000.0, broker_cash=499_600.0, tolerance=0.001)
        assert result.is_reconciled
