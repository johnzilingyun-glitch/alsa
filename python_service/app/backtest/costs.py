"""Transaction cost model for backtesting.

Supports China A-share cost structure:
- Commission (万三 typical, with minimum)
- Stamp tax (千一, sell-side only)
- Slippage estimation based on participation rate
"""
from dataclasses import dataclass
import math


@dataclass
class CostParams:
    commission_rate: float = 0.0003   # 万三
    stamp_tax_rate: float = 0.001     # 千一 (sell only)
    min_commission: float = 5.0       # 最低佣金


class CostModel:
    """Calculate transaction costs for buy/sell."""

    def __init__(self, params: CostParams):
        self.params = params

    def buy_cost(self, notional: float) -> float:
        """Buy side: commission only."""
        commission = max(notional * self.params.commission_rate, self.params.min_commission)
        return commission

    def sell_cost(self, notional: float) -> float:
        """Sell side: commission + stamp tax."""
        commission = max(notional * self.params.commission_rate, self.params.min_commission)
        stamp_tax = notional * self.params.stamp_tax_rate
        return commission + stamp_tax

    def estimate_slippage_bps(
        self,
        order_value: float,
        adv: float,
        volatility: float,
        base_spread_bps: float = 5.0,
    ) -> float:
        """Estimate market impact slippage in basis points.
        
        SlippageBps = BaseSpread + k1 * ParticipationRate + k2 * Volatility + k3 * sqrt(OrderValue/ADV)
        """
        if adv <= 0:
            return base_spread_bps + 50.0  # Illiquid penalty

        participation_rate = order_value / adv
        k1 = 100.0   # Participation impact coefficient
        k2 = 500.0   # Volatility coefficient
        k3 = 30.0    # Square-root impact coefficient

        slippage = (
            base_spread_bps
            + k1 * participation_rate
            + k2 * volatility
            + k3 * math.sqrt(order_value / adv)
        )
        return slippage
