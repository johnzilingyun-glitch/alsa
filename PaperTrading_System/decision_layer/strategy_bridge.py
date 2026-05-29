# decision_layer/strategy_bridge.py

from qlib.strategy.base import BaseStrategy
from qlib.backtest.decision import TradeDecisionWO, Order, OrderDir

class AIAgentStrategy(BaseStrategy):
    def __init__(self, agent_model, market_type="CN", trade_unit=100, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent_model
        self.market_type = market_type
        self.trade_unit = trade_unit

    def generate_trade_decision(self, execute_result=None):
        """
        Triggered on every tick/day of the Qlib backtest clock.
        """
        step_time = self.trade_calendar.get_step_time()
        current_time = step_time[0]
        
        # 1. Get virtual account state
        current_positions = self.trade_position.get_stock_amount_dict()
        current_cash = self.trade_position.get_cash()
        
        # Filter positions (exclude 'cash' from positions list if present)
        pos_dict = {k: v for k, v in current_positions.items() if k != 'cash'}

        # 2. Call external AI Agent
        target_pos_dict = self.agent.predict(current_time, pos_dict, current_cash)

        # 3. Calculate deltas and align with specific market trade units
        order_list = []
        for stock_id, target_vol in target_pos_dict.items():
            current_vol = current_positions.get(stock_id, 0)
            delta = target_vol - current_vol
            
            if delta == 0:
                continue
                
            # Enforce trade unit constraint
            if self.trade_unit > 1:
                delta = int(delta / self.trade_unit) * self.trade_unit
                if delta == 0:
                    continue

            direction = OrderDir.BUY if delta > 0 else OrderDir.SELL
            
            # Assemble standard Qlib Order object
            qlib_order = Order(
                stock_id=stock_id,
                amount=abs(delta),
                direction=direction,
                start_time=step_time[0],
                end_time=step_time[1]
            )
            order_list.append(qlib_order)

        return TradeDecisionWO(order_list, self)
