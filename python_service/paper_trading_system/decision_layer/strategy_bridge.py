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
        current_time = self.trade_calendar.get_trade_time()
        
        # Get account state
        account = self.get_agent_account()
        cash = account.get_cash()
        
        # In Qlib, get_positions returns a dictionary where keys are symbols and values are Position objects
        current_positions = account.get_positions()
        
        # 1. Ask the AI agent for target allocation (budget per stock)
        # Note: We pass trade_exchange context if agent needs current prices
        target_allocation_value = self.agent.predict(current_time, current_positions, cash, context=self.trade_exchange)
        
        # 2. Calculate deltas and format standard Qlib Orders
        order_list = self._calculate_delta_and_format_orders(
            current_positions, 
            target_allocation_value, 
            current_time
        )
        
        return TradeDecisionWO(order_list, self)
        
    def _calculate_delta_and_format_orders(self, current_pos: dict, target_alloc: Dict[str, float], current_time: pd.Timestamp) -> List[Order]:
        orders = []
        
        # First, sell positions that are not in target_alloc or need to be reduced
        for symbol, pos_obj in current_pos.items():
            if symbol == 'cash':
                continue
                
            # Current price from exchange to estimate value and calculate shares
            try:
                # Need to use self.trade_exchange to get the close price for the current step
                current_price = self.trade_exchange.get_quote_info(symbol, current_time, "close")
            except Exception:
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
                try:
                    current_price = self.trade_exchange.get_quote_info(symbol, current_time, "close")
                except Exception:
                    continue
                
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
