import logging
import pandas as pd
from typing import Dict, List
from qlib.strategy.base import BaseStrategy
from qlib.backtest.decision import TradeDecisionWO, Order, OrderDir

logger = logging.getLogger(__name__)

class CustomRuleQlibStrategy(BaseStrategy):
    """
    Qlib implementation of the CustomRuleCtaStrategy.
    Evaluates JSON-based buy/sell rules.
    """
    
    def __init__(
        self,
        market: str = "CN",
        buy_rules: List[Dict] = None,
        sell_rules: List[Dict] = None,
        position_mode: str = "fixed_shares",
        position_value: float = 100.0,
        stop_loss_pct: float = 0.0,
        take_profit_pct: float = 0.0,
        trailing_stop_pct: float = 0.0,
        target_symbol: str = "SH600519",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.market = market
        self.buy_rules = buy_rules or []
        self.sell_rules = sell_rules or []
        self.position_mode = position_mode
        self.position_value = position_value
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.target_symbol = target_symbol.upper()
        
        if self.target_symbol.startswith("6"):
            self.target_symbol = f"SH{self.target_symbol.replace('SH', '').replace('.SS', '')}"
        elif self.target_symbol.startswith("0") or self.target_symbol.startswith("3"):
            self.target_symbol = f"SZ{self.target_symbol.replace('SZ', '').replace('.SZ', '')}"

        # State tracking for single stock
        self.entry_price = 0.0
        self.highest_since_entry = 0.0
        
        # Prepare Qlib Dataset expressions
        # We need historical data to compute MACD, RSI, etc.
        # But Qlib's DataHandler can compute these features for us.
        # For simplicity, we fetch the last 30 days of price data at each step
        # and compute the indicators using Pandas/TA-Lib or just basic pandas.
        
    def _compute_rsi(self, series: pd.Series, period: int = 14) -> float:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50.0

    def _compute_macd(self, series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return macd_hist

    def _eval_rule(self, rule: Dict, close_series: pd.Series, current_price: float, is_sell: bool) -> bool:
        rule_type = rule.get("type", "")
        
        try:
            if rule_type == "rsi_oversold":
                period = int(rule.get("rsi_period", 14))
                threshold = float(rule.get("rsi_threshold", 30))
                rsi = self._compute_rsi(close_series, period)
                return rsi < threshold
                
            elif rule_type == "rsi_overbought":
                period = int(rule.get("rsi_period", 14))
                threshold = float(rule.get("rsi_threshold", 70))
                rsi = self._compute_rsi(close_series, period)
                return rsi > threshold
                
            elif rule_type == "macd_golden_cross":
                macd_hist = self._compute_macd(close_series, int(rule.get("fast", 12)), int(rule.get("slow", 26)), int(rule.get("signal", 9)))
                if len(macd_hist) < 2: return False
                return macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0
                
            elif rule_type == "macd_dead_cross":
                macd_hist = self._compute_macd(close_series, int(rule.get("fast", 12)), int(rule.get("slow", 26)), int(rule.get("signal", 9)))
                if len(macd_hist) < 2: return False
                return macd_hist.iloc[-1] < 0 and macd_hist.iloc[-2] >= 0
                
            elif rule_type == "price_above_ma":
                period = int(rule.get("ma_period", 20))
                ma = close_series.rolling(window=period).mean().iloc[-1]
                return current_price > ma
                
            elif rule_type == "price_below_ma":
                period = int(rule.get("ma_period", 20))
                ma = close_series.rolling(window=period).mean().iloc[-1]
                return current_price < ma
                
            elif rule_type == "boll_lower_break":
                period = int(rule.get("boll_period", 20))
                dev = float(rule.get("boll_dev", 2.0))
                ma = close_series.rolling(window=period).mean().iloc[-1]
                std = close_series.rolling(window=period).std().iloc[-1]
                lower = ma - dev * std
                return current_price <= lower
                
            elif rule_type == "boll_upper_break":
                period = int(rule.get("boll_period", 20))
                dev = float(rule.get("boll_dev", 2.0))
                ma = close_series.rolling(window=period).mean().iloc[-1]
                std = close_series.rolling(window=period).std().iloc[-1]
                upper = ma + dev * std
                return current_price >= upper
                
            return True # Unhandled rules don't block
        except Exception as e:
            logger.warning(f"Error evaluating rule {rule_type}: {e}")
            return True

    def generate_trade_decision(self, execute_result=None):
        trade_step = self.trade_calendar.get_trade_step()
        if trade_step >= self.trade_calendar.get_trade_len():
            trade_step = self.trade_calendar.get_trade_step()
        try:
            trade_start_time, trade_end_time = self.trade_calendar.get_step_time(trade_step)
        except IndexError:
            # Fallback for the last day
            return TradeDecisionWO([], self)
        
        orders = []
        
        # We need recent price history for indicators
        # Use D features from Qlib
        from qlib.data import D
        hist_df = D.features([self.target_symbol], ['$close', '$volume'], start_time=trade_start_time - pd.Timedelta(days=60), end_time=trade_end_time)
        
        if hist_df is None or hist_df.empty:
            return TradeDecisionWO(orders, self)
            
        try:
            symbol_df = hist_df.xs(self.target_symbol, level='instrument')
        except KeyError:
            return TradeDecisionWO(orders, self)
            
        if len(symbol_df) < 2:
            return trade_decision
            
        close_series = symbol_df['$close']
        current_price = close_series.iloc[-1]
        volume = symbol_df['$volume'].iloc[-1]
        
        if pd.isna(current_price) or current_price <= 0 or pd.isna(volume) or volume <= 0:
            return TradeDecisionWO(orders, self)
            
        # Track current holdings
        current_holdings = self.trade_position.get_stock_amount_dict().copy()
        current_pos = current_holdings.get(self.target_symbol, 0)
        
        if current_pos > 0:
            self.highest_since_entry = max(self.highest_since_entry, current_price)
            
            should_sell = False
            # Check stop loss
            if self.stop_loss_pct > 0 and self.entry_price > 0:
                loss_pct = (self.entry_price - current_price) / self.entry_price * 100
                if loss_pct >= self.stop_loss_pct:
                    should_sell = True
            
            # Check take profit
            if not should_sell and self.take_profit_pct > 0 and self.entry_price > 0:
                gain_pct = (current_price - self.entry_price) / self.entry_price * 100
                if gain_pct >= self.take_profit_pct:
                    should_sell = True
            
            # Check trailing stop
            if not should_sell and self.trailing_stop_pct > 0 and self.highest_since_entry > 0:
                drawdown_pct = (self.highest_since_entry - current_price) / self.highest_since_entry * 100
                if drawdown_pct >= self.trailing_stop_pct:
                    should_sell = True
            
            # Check rules
            if not should_sell:
                for rule in self.sell_rules:
                    if self._eval_rule(rule, close_series, current_price, is_sell=True):
                        should_sell = True
                        break
                        
            if should_sell:
                order = Order(
                    stock_id=self.target_symbol,
                    amount=current_pos,
                    start_time=trade_start_time,
                    end_time=trade_end_time,
                    direction=OrderDir.SELL,
                    factor=1.0
                )
                orders.append(order)
                self.entry_price = 0.0
                self.highest_since_entry = 0.0
                return TradeDecisionWO(orders, self)
                
        # BUY LOGIC
        if current_pos == 0 and self.buy_rules:
            all_pass = True
            for rule in self.buy_rules:
                if not self._eval_rule(rule, close_series, current_price, is_sell=False):
                    all_pass = False
                    break
                    
            if all_pass:
                # Calculate size
                if self.position_mode == "fixed_shares":
                    size = int(self.position_value)
                elif self.position_mode == "fixed_pct":
                    budget = (self.position_value / 100.0) * self.trade_position.get_cash()
                    size = int(budget / current_price)
                else:
                    size = 100
                    
                # Lot size rounding
                if "CN" in self.market or "A-Share" in self.market:
                    size = (size // 100) * 100
                    
                if size > 0:
                    order = Order(
                        stock_id=self.target_symbol,
                        amount=size,
                        start_time=trade_start_time,
                        end_time=trade_end_time,
                        direction=OrderDir.BUY,
                        factor=1.0
                    )
                    orders.append(order)
                    self.entry_price = current_price
                    self.highest_since_entry = current_price
                    
        return TradeDecisionWO(orders, self)
