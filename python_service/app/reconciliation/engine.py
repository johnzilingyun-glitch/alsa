"""Reconciliation engine — daily audit of positions, cash, and fills.

Compares internal portfolio ledger against broker state to detect
discrepancies that could indicate bugs, missed fills, or unauthorized trades.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class InternalPosition:
    symbol: str
    quantity: int
    avg_cost: float


@dataclass
class BrokerPosition:
    symbol: str
    quantity: int
    market_value: float


@dataclass
class Discrepancy:
    symbol: str
    field: str
    internal_value: str
    broker_value: str
    severity: str = "high"


@dataclass
class ReconciliationResult:
    is_reconciled: bool
    discrepancies: List[Discrepancy] = field(default_factory=list)


class ReconciliationEngine:
    """Compares internal state with broker state."""

    def reconcile_positions(
        self,
        internal: List[InternalPosition],
        broker: List[BrokerPosition],
    ) -> ReconciliationResult:
        discrepancies: List[Discrepancy] = []

        internal_map = {p.symbol: p for p in internal}
        broker_map = {p.symbol: p for p in broker}

        # Check internal positions against broker
        for symbol, ipos in internal_map.items():
            if symbol not in broker_map:
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    field="missing_in_broker",
                    internal_value=str(ipos.quantity),
                    broker_value="0",
                ))
            else:
                bpos = broker_map[symbol]
                if ipos.quantity != bpos.quantity:
                    discrepancies.append(Discrepancy(
                        symbol=symbol,
                        field="quantity",
                        internal_value=str(ipos.quantity),
                        broker_value=str(bpos.quantity),
                    ))

        # Check broker positions not in internal
        for symbol in broker_map:
            if symbol not in internal_map:
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    field="missing_in_internal",
                    internal_value="0",
                    broker_value=str(broker_map[symbol].quantity),
                ))

        return ReconciliationResult(
            is_reconciled=len(discrepancies) == 0,
            discrepancies=discrepancies,
        )

    def reconcile_cash(
        self,
        internal_cash: float,
        broker_cash: float,
        tolerance: float = 0.001,
    ) -> ReconciliationResult:
        """Check cash balance within tolerance (relative)."""
        if internal_cash == 0:
            diff_pct = abs(broker_cash)
        else:
            diff_pct = abs(internal_cash - broker_cash) / abs(internal_cash)

        if diff_pct > tolerance:
            return ReconciliationResult(
                is_reconciled=False,
                discrepancies=[Discrepancy(
                    symbol="CASH",
                    field="cash_balance",
                    internal_value=f"{internal_cash:.2f}",
                    broker_value=f"{broker_cash:.2f}",
                    severity="critical",
                )],
            )

        return ReconciliationResult(is_reconciled=True)
