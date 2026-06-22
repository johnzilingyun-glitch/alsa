import sys
import pandas as pd
import math
import logging
from typing import List, Dict

try:
    from qlib.strategy.base import BaseStrategy
    from qlib.backtest.decision import TradeDecisionWO, OrderDir, Order
except ImportError:
    # Fallback for type hinting or testing if qlib is not installed
    class BaseStrategy:
        def __init__(self, **kwargs): pass
    class TradeDecisionWO:
        def __init__(self, order_list, strategy): pass
    class OrderDir:
        BUY = 1
        SELL = -1
    class Order:
        def __init__(self, stock_id, amount, start_time, end_time, direction, factor): pass

from .agent_models import BaseAgent
from ..execution_layer.market_configs import get_exchange_kwargs

logger = logging.getLogger(__name__)


class AIAgentStrategy(BaseStrategy):
    def __init__(self, agent_model: BaseAgent, market_type: str = "CN", **kwargs):
        super().__init__(**kwargs)
        self.agent = agent_model
        self.market_type = market_type
        
        # Load market constraints
        market_cfg = get_exchange_kwargs(market_type)
        self.trade_unit = market_cfg.get("trade_unit", 1)

    def generate_trade_decision(self, execute_result=None):
        """
        Qlib engine calls this at each step.
        """
        # get_step_time returns (start_time, end_time) tuple
        time_range = self.trade_calendar.get_step_time()
        current_time = time_range[0]  # Use start time
        
        # Get account state via Qlib 0.9.7 API
        account = self.common_infra.get("trade_account")
        cash = account.get_cash()
        
        # Get current positions from trade_position
        current_positions = {}
        pos = self.trade_position
        if pos is not None:
            # Qlib 0.9.7: use get_stock_amount_dict() and get_stock_price()
            amounts = pos.get_stock_amount_dict()
            for stock_id, amount in amounts.items():
                if amount > 0:
                    try:
                        price = pos.get_stock_price(stock_id)
                    except Exception:
                        price = 0.0
                    current_positions[stock_id] = type('Pos', (), {'amount': amount, 'price': price})()
        
        # 1. Ask the AI agent for target allocation (budget per stock)
        target_allocation_value = self.agent.predict(current_time, current_positions, cash, context=self.trade_exchange)
        # Normalize symbols to lowercase for Qlib compatibility
        target_allocation_value = {k.lower(): v for k, v in target_allocation_value.items()}
        print(f"DEBUG MockAgent: time={current_time} cash={cash:.0f} target_alloc={target_allocation_value}", file=sys.stderr)
        
        # 2. Calculate deltas and format standard Qlib Orders
        order_list = self._calculate_delta_and_format_orders(
            current_positions, 
            target_allocation_value, 
            current_time
        )
        
        return TradeDecisionWO(order_list, self)

    def _get_price(self, symbol: str, current_time: pd.Timestamp) -> float:
        """Get close price from Qlib data API (fallback if exchange.get_quote_info fails)."""
        try:
            # Try exchange first
            price = self.trade_exchange.get_quote_info(symbol, current_time, current_time, "close")
            if price is not None and price > 0:
                return float(price)
        except Exception:
            pass
        # Fallback: query Qlib data directly
        try:
            from qlib.data import D
            df = D.features([symbol], ["$close"], start_time=current_time, end_time=current_time)
            if df is not None and not df.empty:
                val = df.iloc[0, 0]
                if not (isinstance(val, float) and (pd.isna(val) or val <= 0)):
                    return float(val)
        except Exception:
            pass
        return 0.0

    def _calculate_delta_and_format_orders(self, current_pos: dict, target_alloc: Dict[str, float], current_time: pd.Timestamp) -> List[Order]:
        orders = []
        
        # First, sell positions that are not in target_alloc or need to be reduced
        for symbol, pos_obj in current_pos.items():
            if symbol == 'cash':
                continue
                
            # Current price from exchange to estimate value and calculate shares
            current_price = self._get_price(symbol, current_time)
            if current_price <= 0:
                current_price = pos_obj.price if hasattr(pos_obj, 'price') else 0.0
            if current_price <= 0:
                continue

            current_shares = pos_obj.amount
            # A-Share specific: we can only sell what's available today (YD position + intraday buy if T+0)
            # In Qlib SimulatorExecutor, usually `amount` is total, `sell_amount` or `can_sell` depends on rules.
            # Qlib's Account handles T+1 internally if configured correctly in Exchange. 
            
            target_val = target_alloc.get(symbol, 0.0)
            target_shares = target_val / current_price
            
            # Apply trade unit rounding (downward to be safe on cash, or nearest round lot)
            # Example for A-Share: trade_unit = 100
            target_shares_rounded = int(target_shares // self.trade_unit) * self.trade_unit
            
            delta_shares = target_shares_rounded - current_shares
            
            if delta_shares < 0:
                # We need to SELL
                sell_amount = abs(delta_shares)
                # Ensure we round sell amount to trade unit (unless it's a full liquidation, but for safety keep unit)
                sell_amount = int(sell_amount // self.trade_unit) * self.trade_unit
                if sell_amount > 0:
                    orders.append(
                        Order(
                            stock_id=symbol,
                            amount=sell_amount,
                            start_time=current_time,
                            end_time=current_time,
                            direction=OrderDir.SELL,
                            factor=1.0,
                        )
                    )
            elif delta_shares > 0:
                # We need to BUY
                buy_amount = delta_shares
                buy_amount = int(buy_amount // self.trade_unit) * self.trade_unit
                if buy_amount > 0:
                    orders.append(
                        Order(
                            stock_id=symbol,
                            amount=buy_amount,
                            start_time=current_time,
                            end_time=current_time,
                            direction=OrderDir.BUY,
                            factor=1.0,
                        )
                    )
        
        # Now handle newly added symbols not in current_pos
        for symbol, target_val in target_alloc.items():
            if symbol not in current_pos:
                current_price = self._get_price(symbol, current_time)
                if current_price <= 0:
                    continue
                    
                target_shares = target_val / current_price
                buy_amount = int(target_shares // self.trade_unit) * self.trade_unit
                
                if buy_amount > 0:
                    orders.append(
                        Order(
                            stock_id=symbol,
                            amount=buy_amount,
                            start_time=current_time,
                            end_time=current_time,
                            direction=OrderDir.BUY,
                            factor=1.0,
                        )
                    )
                    
        return orders
