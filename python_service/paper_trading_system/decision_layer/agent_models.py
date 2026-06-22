from typing import Dict, Any, List
import pandas as pd
import numpy as np

class BaseAgent:
    """Base interface for AI/RL Agent."""
    def __init__(self, market_type: str = "CN"):
        self.market_type = market_type

    def predict(self, current_time: pd.Timestamp, current_positions: Dict[str, Any], cash: float, context: Any = None) -> Dict[str, float]:
        """
        Input:
            current_time: The current simulation date/time.
            current_positions: Dictionary of {symbol: Position_Object}
            cash: Available cash in the account.
            context: Additional market data or Qlib Dataset context.
        Output:
            Dict[str, float]: Target cash value to allocate for each symbol.
            Example: {"SH600000": 50000.0, "SZ000001": 20000.0}
        """
        raise NotImplementedError


class MockAgent(BaseAgent):
    """
    A simple mock agent that randomly selects 3 stocks from a predefined universe 
    and allocates cash evenly among them, for testing the full pipeline.
    """
    def __init__(self, market_type: str = "CN", universe: List[str] = None):
        super().__init__(market_type)
        if universe is None:
            if market_type == "CN":
                self.universe = ["sh600000", "sh600519", "sz000001", "sz000858", "sh601318"]
            elif market_type == "US":
                self.universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
            elif market_type == "HK":
                self.universe = ["0700.HK", "9988.HK", "3690.HK", "1299.HK", "0941.HK"]
        else:
            self.universe = universe

    def predict(self, current_time: pd.Timestamp, current_positions: Dict[str, Any], cash: float, context: Any = None) -> Dict[str, float]:
        # Always pick 3 random stocks from universe
        np.random.seed(current_time.year * 10000 + current_time.month * 100 + current_time.day)
        selected_symbols = np.random.choice(self.universe, size=min(3, len(self.universe)), replace=False)
        
        # Calculate total portfolio value (rough estimate assuming current_positions has 'price' or using amount)
        # For true mock, we just use cash + 10% for churn if already invested
        # Let's keep it simple: we aim to invest 90% of available cash evenly into the 3 stocks.
        target_allocation = {}
        budget_per_stock = (cash * 0.9) / len(selected_symbols) if cash > 0 else 0
        
        for sym in selected_symbols:
            target_allocation[sym] = budget_per_stock
            
        return target_allocation
