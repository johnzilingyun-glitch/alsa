"""Execution simulator — models market microstructure constraints.

Handles:
- Normal fills
- Limit-up/limit-down rejection
- Suspended stock rejection
- Partial fills (future extension)
"""
from dataclasses import dataclass


@dataclass
class OrderRequest:
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    price: float
    market_price: float
    limit_up: float
    limit_down: float
    is_suspended: bool = False


@dataclass
class FillResult:
    symbol: str
    side: str
    filled_quantity: int
    fill_price: float
    status: str  # FILLED, REJECTED, PARTIAL
    reject_reason: str = ""


class ExecutionSimulator:
    """Simulates order execution with market constraints."""

    def execute(self, order: OrderRequest) -> FillResult:
        """Attempt to fill an order, respecting market constraints."""

        # Check suspension
        if order.is_suspended:
            return FillResult(
                symbol=order.symbol,
                side=order.side,
                filled_quantity=0,
                fill_price=0.0,
                status="REJECTED",
                reject_reason="suspended",
            )

        # Check limit-up (cannot buy at limit-up)
        if order.side == "BUY" and order.market_price >= order.limit_up:
            return FillResult(
                symbol=order.symbol,
                side=order.side,
                filled_quantity=0,
                fill_price=0.0,
                status="REJECTED",
                reject_reason="limit_up",
            )

        # Check limit-down (cannot sell at limit-down)
        if order.side == "SELL" and order.market_price <= order.limit_down:
            return FillResult(
                symbol=order.symbol,
                side=order.side,
                filled_quantity=0,
                fill_price=0.0,
                status="REJECTED",
                reject_reason="limit_down",
            )

        # Normal fill at market price
        return FillResult(
            symbol=order.symbol,
            side=order.side,
            filled_quantity=order.quantity,
            fill_price=order.market_price,
            status="FILLED",
        )
