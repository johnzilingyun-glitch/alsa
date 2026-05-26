"""Event-driven backtest engine.

Processes signals sequentially, applies the execution simulator and cost model,
maintains a portfolio ledger, and computes performance metrics.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .costs import CostModel, CostParams
from .simulator import ExecutionSimulator, OrderRequest, FillResult


@dataclass
class BacktestConfig:
    initial_cash: float
    start_date: str
    end_date: str
    cost_params: CostParams = field(default_factory=CostParams)


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    avg_cost: float = 0.0
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis


@dataclass
class TradeRecord:
    date: str
    symbol: str
    side: str
    quantity: int
    price: float
    cost: float
    pnl: float = 0.0  # Realized PnL for sells


class BacktestEngine:
    """Simple event-driven backtest engine with cost model."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.cash = config.initial_cash
        self.positions: Dict[str, Position] = {}
        self.trades: List[TradeRecord] = []
        self.equity_curve: List[Dict] = []
        self.cost_model = CostModel(config.cost_params)
        self.simulator = ExecutionSimulator()
        self.total_costs = 0.0
        self.realized_pnl = 0.0

    def process_signal(
        self,
        date: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        market_price: float,
        limit_up: float,
        limit_down: float,
        is_suspended: bool = False,
    ) -> Optional[FillResult]:
        """Process a trading signal through execution simulator."""
        order = OrderRequest(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            market_price=market_price,
            limit_up=limit_up,
            limit_down=limit_down,
            is_suspended=is_suspended,
        )

        fill = self.simulator.execute(order)
        if fill.status != "FILLED":
            return fill

        # Apply fill to portfolio
        notional = fill.filled_quantity * fill.fill_price
        trade_pnl = 0.0

        if side == "BUY":
            cost = self.cost_model.buy_cost(notional)
            self.cash -= notional + cost
            self.total_costs += cost

            # Update position
            pos = self.positions.get(symbol, Position(symbol=symbol))
            total_cost_basis = pos.avg_cost * pos.quantity + notional
            pos.quantity += fill.filled_quantity
            pos.avg_cost = total_cost_basis / pos.quantity if pos.quantity > 0 else 0
            pos.current_price = fill.fill_price
            self.positions[symbol] = pos

        elif side == "SELL":
            cost = self.cost_model.sell_cost(notional)
            self.cash += notional - cost
            self.total_costs += cost

            # Calculate realized PnL
            pos = self.positions.get(symbol)
            if pos:
                trade_pnl = (fill.fill_price - pos.avg_cost) * fill.filled_quantity - cost
                pos.quantity -= fill.filled_quantity
                if pos.quantity <= 0:
                    del self.positions[symbol]
                self.realized_pnl += trade_pnl

        self.trades.append(TradeRecord(
            date=date,
            symbol=symbol,
            side=side,
            quantity=fill.filled_quantity,
            price=fill.fill_price,
            cost=cost,
            pnl=trade_pnl,
        ))

        return fill

    def mark_to_market(self, date: str, prices: Dict[str, float]) -> None:
        """Update position market prices and record equity snapshot."""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].current_price = price

        equity = self._total_equity()
        self.equity_curve.append({"date": date, "equity": equity})

    def get_equity_curve(self) -> List[Dict]:
        return self.equity_curve

    def compute_metrics(self) -> Dict:
        """Compute backtest performance metrics."""
        total_equity = self._total_equity()
        total_pnl = total_equity - self.config.initial_cash

        winning_trades = [t for t in self.trades if t.side == "SELL" and t.pnl > 0]
        losing_trades = [t for t in self.trades if t.side == "SELL" and t.pnl <= 0]
        sell_trades = [t for t in self.trades if t.side == "SELL"]

        hit_rate = len(winning_trades) / len(sell_trades) if sell_trades else 0.0

        return {
            "total_trades": len(self.trades),
            "total_pnl": total_pnl,
            "realized_pnl": self.realized_pnl,
            "total_costs": self.total_costs,
            "final_equity": total_equity,
            "return_pct": total_pnl / self.config.initial_cash * 100,
            "hit_rate": hit_rate,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
        }

    def _total_equity(self) -> float:
        """Cash + sum of all position market values."""
        position_value = sum(pos.market_value for pos in self.positions.values())
        return self.cash + position_value
