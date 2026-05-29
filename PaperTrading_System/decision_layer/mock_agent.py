# decision_layer/mock_agent.py

class MockStockAgent:
    def __init__(self, test_stock_list=["SH600000", "SZ000001"]):
        self.test_stock_list = test_stock_list

    def predict(self, current_time, current_positions, current_cash):
        """
        Mock logic: Buy a fixed amount of the test stocks every day.
        """
        # Target holding: 100 shares for each test stock
        return {stock: 100 for stock in self.test_stock_list}
