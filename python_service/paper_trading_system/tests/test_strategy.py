import pytest
import pandas as pd
from paper_trading_system.decision_layer.agent_models import MockAgent
from paper_trading_system.decision_layer.strategy_bridge import AIAgentStrategy

class MockExchange:
    def get_quote_info(self, symbol, current_time, field):
        # Mock price of 10.0 for all stocks
        return 10.0

class MockAccount:
    def get_cash(self):
        return 100000.0
    def get_positions(self):
        return {}

def test_a_share_trade_unit_rounding():
    agent = MockAgent(market_type="CN")
    strategy = AIAgentStrategy(agent_model=agent, market_type="CN")
    
    strategy.trade_exchange = MockExchange()
    strategy.portfolio_account = MockAccount()
    
    # Force agent to predict a specific allocation
    # Let's say we target 1500 value on AAPL. At price 10.0, it's 150 shares.
    def mock_predict(*args, **kwargs):
        return {"SH600000": 1500.0}
    agent.predict = mock_predict
    
    orders = strategy._calculate_delta_and_format_orders(
        current_pos={}, 
        target_alloc={"SH600000": 1500.0}, 
        current_time=pd.Timestamp("2023-01-01")
    )
    
    assert len(orders) == 1
    # 150 shares should be rounded down to 100 shares for A-Share (unit=100)
    assert orders[0].amount == 100
    assert orders[0].stock_id == "SH600000"

def test_us_share_no_rounding():
    agent = MockAgent(market_type="US")
    strategy = AIAgentStrategy(agent_model=agent, market_type="US")
    
    strategy.trade_exchange = MockExchange()
    strategy.portfolio_account = MockAccount()
    
    orders = strategy._calculate_delta_and_format_orders(
        current_pos={}, 
        target_alloc={"AAPL": 1550.0}, 
        current_time=pd.Timestamp("2023-01-01")
    )
    
    assert len(orders) == 1
    # 155 shares should not be rounded (unit=1)
    assert orders[0].amount == 155
    assert orders[0].stock_id == "AAPL"
