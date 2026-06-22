"""
Shared Strategy Protocol — unified interface for both live mock trading and backtesting.

Both mock_trading_service.py and paper_trading_system/ implement this protocol,
ensuring strategy logic is reusable across live simulation and historical backtest.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    shares: int
    price: float
    reason: str = ""


@dataclass
class Position:
    symbol: str
    shares: int
    average_cost: float
    market: str = "US-Share"


@dataclass
class AccountState:
    cash: float
    positions: List[Position]
    currency: str = "USD"


class TradingStrategy(ABC):
    """Strategy interface shared between live mock trading and backtesting."""

    @abstractmethod
    def should_buy(self, symbol: str, price: float, account: AccountState, market_data: Dict[str, Any]) -> Optional[Order]:
        """Return a BUY order if strategy signals buy, else None."""
        ...

    @abstractmethod
    def should_sell(self, symbol: str, price: float, position: Position, account: AccountState, market_data: Dict[str, Any]) -> Optional[Order]:
        """Return a SELL order if strategy signals sell, else None."""
        ...

    @abstractmethod
    def get_stop_loss(self, symbol: str, entry_price: float) -> Optional[float]:
        """Return stop-loss price, or None if no stop-loss."""
        ...

    @abstractmethod
    def get_take_profit(self, symbol: str, entry_price: float) -> Optional[float]:
        """Return take-profit price, or None if no take-profit."""
        ...


class EqualWeightStrategy(TradingStrategy):
    """Simple equal-weight strategy for demonstration and backtesting."""

    def __init__(self, max_positions: int = 10, position_pct: float = 0.1):
        self.max_positions = max_positions
        self.position_pct = position_pct

    def should_buy(self, symbol: str, price: float, account: AccountState, market_data: Dict[str, Any]) -> Optional[Order]:
        if len(account.positions) >= self.max_positions:
            return None
        # Check if already holding
        if any(p.symbol == symbol for p in account.positions):
            return None
        # Buy if we have enough cash
        target_value = account.cash * self.position_pct
        shares = int(target_value / price) if price > 0 else 0
        if shares > 0:
            return Order(symbol=symbol, side=OrderSide.BUY, shares=shares, price=price)
        return None

    def should_sell(self, symbol: str, price: float, position: Position, account: AccountState, market_data: Dict[str, Any]) -> Optional[Order]:
        # Sell if position exceeds target allocation
        current_value = position.shares * price
        total_equity = account.cash + sum(p.shares * price for p in account.positions)
        if total_equity > 0 and current_value / total_equity > self.position_pct * 1.5:
            excess_shares = int((current_value - total_equity * self.position_pct) / price)
            if excess_shares > 0:
                return Order(symbol=symbol, side=OrderSide.SELL, shares=min(excess_shares, position.shares), price=price)
        return None

    def get_stop_loss(self, symbol: str, entry_price: float) -> Optional[float]:
        return entry_price * 0.92  # 8% stop-loss

    def get_take_profit(self, symbol: str, entry_price: float) -> Optional[float]:
        return entry_price * 1.20  # 20% take-profit
