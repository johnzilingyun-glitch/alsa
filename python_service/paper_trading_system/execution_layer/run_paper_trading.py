import qlib
from qlib.constant import REG_CN
from qlib.backtest.account import Account
from qlib.backtest.executor import SimulatorExecutor
from qlib.backtest.exchange import Exchange
import pandas as pd
import logging
import pickle
import os

from paper_trading_system.decision_layer.agent_models import MockAgent
from paper_trading_system.decision_layer.strategy_bridge import AIAgentStrategy
from paper_trading_system.execution_layer.market_configs import get_exchange_kwargs

logger = logging.getLogger(__name__)

def get_state_path(market: str) -> str:
    os.makedirs("output/state", exist_ok=True)
    return f"output/state/account_state_{market}.pkl"

def load_or_create_account(market: str, initial_cash: float = 1000000.0) -> Account:
    state_path = get_state_path(market)
    if os.path.exists(state_path):
        logger.info(f"Loading existing account state from {state_path}")
        with open(state_path, "rb") as f:
            account = pickle.load(f)
        return account
    else:
        logger.info(f"Creating new account with {initial_cash} cash for {market}")
        return Account(init_cash=initial_cash)

def save_account(account: Account, market: str):
    state_path = get_state_path(market)
    with open(state_path, "wb") as f:
        pickle.dump(account, f)
    logger.info(f"Account state saved to {state_path}")

def daily_forward_step(
    date_str: str, 
    market: str = "CN",
    provider_uri: str = "~/.qlib/qlib_data/cn_data"
):
    """
    Run a single day forward paper trading step.
    """
    qlib.init(provider_uri=provider_uri, region=REG_CN)
    current_time = pd.Timestamp(date_str)
    
    # 1. Load State
    account = load_or_create_account(market)
    logger.info(f"Initial Cash: {account.get_cash()}")
    
    # 2. Setup AI and Strategy
    agent = MockAgent(market_type=market)
    strategy = AIAgentStrategy(agent_model=agent, market_type=market)
    
    # In Qlib, Strategy needs access to TradeCalendar and Exchange.
    # Normally `backtest()` handles this wiring. For daily stepping, we wire it manually.
    exchange_kwargs = get_exchange_kwargs(market)
    exchange = Exchange(
        freq="day",
        **exchange_kwargs
    )
    
    # Dummy calendar for the single step
    class DummyCalendar:
        def get_trade_time(self):
            return current_time
    
    strategy.trade_exchange = exchange
    strategy.trade_calendar = DummyCalendar()
    strategy.portfolio_account = account
    
    # 3. Generate Orders
    logger.info("Generating Trade Decisions via AI Agent...")
    decision = strategy.generate_trade_decision()
    orders = decision.get_decision()
    
    logger.info(f"Generated {len(orders)} orders.")
    for o in orders:
        logger.info(f"Order: {o.stock_id}, Dir: {o.direction}, Amount: {o.amount}")
    
    # 4. Execute Orders
    logger.info("Executing orders in SimulatorExecutor...")
    executor = SimulatorExecutor(
        time_per_step="day",
        **exchange_kwargs
    )
    
    # executor.execute returns (trade_account, return_value)
    # We pass a list of orders (since executor step usually takes a list)
    # Actually executor expects TradeDecision obj, but simple step can take lists depending on qlib version.
    # In Qlib `executor.execute` takes (trade_account, trade_decision, ...). 
    
    try:
        # Mocking the execution step manually since true execution needs continuous data
        # For true paper trading, you'd apply the orders to the account against current market prices.
        # This is a basic simulation of the execute step for forward paper trading.
        executor.trade_exchange = exchange
        
        # Simple simulated fill
        for order in orders:
            try:
                # get closing price
                price = exchange.get_quote_info(order.stock_id, current_time, "close")
                
                # Check limits etc (omitted for brevity, handled by executor normally)
                trade_val = price * order.amount
                
                if order.direction == 1: # BUY
                    cost = trade_val * (1 + exchange_kwargs.get("open_cost", 0))
                    if account.get_cash() >= cost:
                        account.update_cash(-cost)
                        account.update_position(order.stock_id, order.amount, price, current_time)
                else: # SELL
                    cost = trade_val * exchange_kwargs.get("close_cost", 0)
                    account.update_cash(trade_val - cost)
                    account.update_position(order.stock_id, -order.amount, price, current_time)
            except Exception as e:
                logger.error(f"Failed to execute {order.stock_id}: {e}")
                
    except Exception as e:
        logger.error(f"Execution engine error: {e}")

    # 5. Save State
    logger.info(f"Final Cash: {account.get_cash()}")
    save_account(account, market)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Example usage:
    # daily_forward_step("2023-11-01", "CN")
