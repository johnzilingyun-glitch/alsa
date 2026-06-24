"""
CustomRuleCtaStrategy — A configurable rule-based CTA strategy for vn.py backtesting.

Users define buy/sell conditions via JSON configuration. The engine evaluates
technical indicator conditions (RSI, MACD, Bollinger, MA) and fundamental
filters (PE, PB, market cap) to generate trading signals.
"""

import os
import sqlite3
import logging
from typing import Dict, List


from vnpy.trader.object import BarData
from vnpy.trader.utility import ArrayManager
from vnpy_ctastrategy import CtaTemplate

logger = logging.getLogger(__name__)

# Path to fundamentals database
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FUNDAMENTALS_DB = os.path.join(PROJECT_ROOT, "fundamentals.db")


class CustomRuleCtaStrategy(CtaTemplate):
    """
    Rule-based strategy that evaluates user-defined buy/sell conditions.

    Configuration is passed via `setting` dict with keys:
        - buy_rules: list of rule dicts, ALL must be true to trigger buy
        - sell_rules: list of rule dicts, ANY true triggers sell
        - position_sizing: dict with mode and params
        - stop_loss_pct: float (percentage, e.g. 5.0 means 5%)
        - take_profit_pct: float
        - trailing_stop_pct: float
    """

    author = "Custom Rule Engine"

    # ── Serializable parameters for vn.py ──
    buy_rules_json: str = "[]"
    sell_rules_json: str = "[]"
    position_mode: str = "fixed_shares"
    position_value: float = 100.0
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    trailing_stop_pct: float = 0.0

    parameters = [
        "buy_rules_json", "sell_rules_json",
        "position_mode", "position_value",
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
    ]
    variables = []

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.am = ArrayManager(size=100)

        # Parse JSON rules
        import json
        self.buy_rules: List[Dict] = json.loads(self.buy_rules_json) if self.buy_rules_json else []
        self.sell_rules: List[Dict] = json.loads(self.sell_rules_json) if self.sell_rules_json else []

        # Internal state
        self.entry_price: float = 0.0
        self.highest_since_entry: float = 0.0

        # Load fundamental data cache
        self._fundamental_cache: Dict[str, Dict[str, float]] = {}
        self._load_fundamentals()

    def _load_fundamentals(self):
        """Pre-load PE/PB data from SQLite into memory for fast lookup."""
        if not os.path.exists(FUNDAMENTALS_DB):
            logger.warning(f"Fundamentals DB not found at {FUNDAMENTALS_DB}")
            return

        # Extract raw symbol from vt_symbol (e.g. "600519.SSE" → "600519.SS")
        raw_symbol = self.vt_symbol.split(".")[0]
        # Convert to yfinance format for DB lookup
        if ".SSE" in self.vt_symbol or ".SZSE" in self.vt_symbol:
            yf_symbol = f"{raw_symbol}.SS" if ".SSE" in self.vt_symbol else f"{raw_symbol}.SZ"
        else:
            yf_symbol = raw_symbol

        try:
            conn = sqlite3.connect(FUNDAMENTALS_DB)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT date, pe_ttm, market_cap FROM valuation WHERE symbol = ? ORDER BY date",
                (yf_symbol,)
            )
            for row in cursor.fetchall():
                date_str, pe, mc = row
                self._fundamental_cache[date_str] = {
                    "pe_ttm": pe if pe else 0,
                    "market_cap": mc if mc else 0,
                }
            conn.close()
            logger.info(f"Loaded {len(self._fundamental_cache)} fundamental records for {yf_symbol}")
        except Exception as e:
            logger.warning(f"Failed to load fundamentals: {e}")

    def _get_fundamental(self, bar: BarData) -> Dict[str, float]:
        """Get the most recent fundamental data on or before the bar date."""
        bar_date = bar.datetime.strftime("%Y-%m-%d")

        # Direct hit
        if bar_date in self._fundamental_cache:
            return self._fundamental_cache[bar_date]

        # Find most recent date before bar_date
        best_date = None
        for d in self._fundamental_cache:
            if d <= bar_date:
                if best_date is None or d > best_date:
                    best_date = d

        if best_date:
            return self._fundamental_cache[best_date]

        return {"pe_ttm": 0, "market_cap": 0}

    def on_init(self):
        self.write_log("自定义规则策略初始化")
        self.load_bar(10)

    def on_start(self):
        self.write_log("自定义规则策略启动")

    def on_stop(self):
        self.write_log("自定义规则策略停止")

    def on_bar(self, bar: BarData):
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        # Volume constraint: don't trade more than 10% of daily volume
        if bar.volume <= 0:
            return

        max_vol = int(bar.volume * 0.10)
        is_cn = (".SSE" in self.vt_symbol) or (".SZSE" in self.vt_symbol)
        if is_cn:
            max_vol = (max_vol // 100) * 100

        # Calculate position size
        size = self._calc_position_size(bar, max_vol)
        if size <= 0:
            return

        # Track highest price since entry for trailing stop
        if self.pos > 0:
            self.highest_since_entry = max(self.highest_since_entry, bar.high_price)

        # Get fundamentals for this bar
        fundamentals = self._get_fundamental(bar)

        # ── SELL logic (check first, any rule triggers sell) ──
        if self.pos > 0:
            should_sell = False

            # Check stop-loss
            if self.stop_loss_pct > 0 and self.entry_price > 0:
                loss_pct = (self.entry_price - bar.close_price) / self.entry_price * 100
                if loss_pct >= self.stop_loss_pct:
                    self.write_log(f"止损触发: 亏损{loss_pct:.1f}% >= {self.stop_loss_pct}%")
                    should_sell = True

            # Check take-profit
            if not should_sell and self.take_profit_pct > 0 and self.entry_price > 0:
                gain_pct = (bar.close_price - self.entry_price) / self.entry_price * 100
                if gain_pct >= self.take_profit_pct:
                    self.write_log(f"止盈触发: 盈利{gain_pct:.1f}% >= {self.take_profit_pct}%")
                    should_sell = True

            # Check trailing stop
            if not should_sell and self.trailing_stop_pct > 0 and self.highest_since_entry > 0:
                drawdown_pct = (self.highest_since_entry - bar.close_price) / self.highest_since_entry * 100
                if drawdown_pct >= self.trailing_stop_pct:
                    self.write_log(f"移动止损触发: 回撤{drawdown_pct:.1f}% >= {self.trailing_stop_pct}%")
                    should_sell = True

            # Check technical sell rules (any one triggers)
            if not should_sell:
                for rule in self.sell_rules:
                    if self._eval_rule(rule, bar, fundamentals, is_sell=True):
                        should_sell = True
                        break

            if should_sell:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0
                self.highest_since_entry = 0.0
                return

        # ── BUY logic (all rules must be satisfied) ──
        if self.pos == 0:
            if not self.buy_rules:
                return  # no rules = no buy

            all_pass = True
            for rule in self.buy_rules:
                if not self._eval_rule(rule, bar, fundamentals, is_sell=False):
                    all_pass = False
                    break

            if all_pass:
                self.buy(bar.close_price, size)
                self.entry_price = bar.close_price
                self.highest_since_entry = bar.close_price

    def _eval_rule(self, rule: Dict, bar: BarData, fundamentals: Dict, is_sell: bool) -> bool:
        """Evaluate a single rule condition."""
        rule_type = rule.get("type", "")

        try:
            # ── RSI ──
            if rule_type == "rsi_oversold":
                period = int(rule.get("rsi_period", 14))
                threshold = float(rule.get("rsi_threshold", 30))
                rsi_val = self.am.rsi(period)
                return rsi_val < threshold

            elif rule_type == "rsi_overbought":
                period = int(rule.get("rsi_period", 14))
                threshold = float(rule.get("rsi_threshold", 70))
                rsi_val = self.am.rsi(period)
                return rsi_val > threshold

            # ── MACD ──
            elif rule_type == "macd_golden_cross":
                fast = int(rule.get("fast", 12))
                slow = int(rule.get("slow", 26))
                signal = int(rule.get("signal", 9))
                macd, macd_signal, macd_hist = self.am.macd(fast, slow, signal, array=True)
                if len(macd_hist) < 2:
                    return False
                return macd_hist[-1] > 0 and macd_hist[-2] <= 0

            elif rule_type == "macd_dead_cross":
                fast = int(rule.get("fast", 12))
                slow = int(rule.get("slow", 26))
                signal = int(rule.get("signal", 9))
                macd, macd_signal, macd_hist = self.am.macd(fast, slow, signal, array=True)
                if len(macd_hist) < 2:
                    return False
                return macd_hist[-1] < 0 and macd_hist[-2] >= 0

            # ── Moving Average ──
            elif rule_type == "price_above_ma":
                period = int(rule.get("ma_period", 20))
                ma_type = rule.get("ma_type", "sma")
                if ma_type == "ema":
                    ma_val = self.am.ema(period)
                else:
                    ma_val = self.am.sma(period)
                return bar.close_price > ma_val

            elif rule_type == "price_below_ma":
                period = int(rule.get("ma_period", 20))
                ma_type = rule.get("ma_type", "sma")
                if ma_type == "ema":
                    ma_val = self.am.ema(period)
                else:
                    ma_val = self.am.sma(period)
                return bar.close_price < ma_val

            # ── Bollinger Bands ──
            elif rule_type == "boll_lower_break":
                period = int(rule.get("boll_period", 20))
                dev = float(rule.get("boll_dev", 2.0))
                upper, lower = self.am.boll(period, dev)
                return bar.close_price <= lower

            elif rule_type == "boll_upper_break":
                period = int(rule.get("boll_period", 20))
                dev = float(rule.get("boll_dev", 2.0))
                upper, lower = self.am.boll(period, dev)
                return bar.close_price >= upper

            # ── Price ──
            elif rule_type == "price_below":
                price_max = float(rule.get("price_max", 10.0))
                return bar.close_price < price_max

            elif rule_type == "price_above":
                price_min = float(rule.get("price_min", 10.0))
                return bar.close_price > price_min

            # ── Fundamental: PE ──
            elif rule_type == "pe_below":
                pe_max = float(rule.get("pe_max", 20))
                pe = fundamentals.get("pe_ttm", 0)
                if pe <= 0:
                    return True  # No data → don't block signal
                return pe < pe_max

            elif rule_type == "pe_above":
                pe_min = float(rule.get("pe_min", 50))
                pe = fundamentals.get("pe_ttm", 0)
                if pe <= 0:
                    return True
                return pe > pe_min

            # ── Fundamental: PB ──
            elif rule_type == "pb_below":
                pb_max = float(rule.get("pb_max", 2.0))
                # PB not in current DB; skip if unavailable
                pb = fundamentals.get("pb", 0)
                if pb <= 0:
                    return True
                return pb < pb_max

            # ── Fundamental: Market Cap ──
            elif rule_type == "market_cap_above":
                mc_min = float(rule.get("mc_min", 100))
                mc = fundamentals.get("market_cap", 0)
                if mc <= 0:
                    return True
                return mc >= mc_min

            # ── Quantitative Factors ──
            # ── Price Momentum (ROC) ──
            elif rule_type == "momentum_above":
                period = int(rule.get("momentum_period", 10))
                threshold = float(rule.get("momentum_threshold", 0.0))
                if len(self.am.close) <= period:
                    return False
                close_t = self.am.close[-1]
                close_prev = self.am.close[-1 - period]
                if close_prev <= 0:
                    return False
                roc = (close_t - close_prev) / close_prev * 100
                return roc > threshold

            elif rule_type == "momentum_below":
                period = int(rule.get("momentum_period", 10))
                threshold = float(rule.get("momentum_threshold", 0.0))
                if len(self.am.close) <= period:
                    return False
                close_t = self.am.close[-1]
                close_prev = self.am.close[-1 - period]
                if close_prev <= 0:
                    return False
                roc = (close_t - close_prev) / close_prev * 100
                return roc < threshold

            # ── Volatility (STD) ──
            elif rule_type == "volatility_above":
                period = int(rule.get("volatility_period", 10))
                threshold = float(rule.get("volatility_threshold", 1.0))
                std_val = self.am.std(period)
                return std_val > threshold

            elif rule_type == "volatility_below":
                period = int(rule.get("volatility_period", 10))
                threshold = float(rule.get("volatility_threshold", 1.0))
                std_val = self.am.std(period)
                return std_val < threshold

            # ── Elasticity (BETA) ──
            elif rule_type == "beta_above":
                period = int(rule.get("beta_period", 10))
                threshold = float(rule.get("beta_threshold", 0.0))
                if len(self.am.close) <= period:
                    return False
                close_t = self.am.close[-1]
                close_prev = self.am.close[-1 - period]
                if close_t <= 0:
                    return False
                beta = (close_t - close_prev) / (period * close_t)
                return beta > threshold

            elif rule_type == "beta_below":
                period = int(rule.get("beta_period", 10))
                threshold = float(rule.get("beta_threshold", 0.0))
                if len(self.am.close) <= period:
                    return False
                close_t = self.am.close[-1]
                close_prev = self.am.close[-1 - period]
                if close_t <= 0:
                    return False
                beta = (close_t - close_prev) / (period * close_t)
                return beta < threshold

            else:
                logger.warning(f"Unknown rule type: {rule_type}")
                return True  # Unknown rules don't block

        except Exception as e:
            logger.warning(f"Rule eval error ({rule_type}): {e}")
            return True  # Errors don't block

    def _calc_position_size(self, bar: BarData, max_vol: int) -> int:
        """Calculate position size based on sizing mode."""
        is_cn = (".SSE" in self.vt_symbol) or (".SZSE" in self.vt_symbol)
        trade_unit = 100 if is_cn else 1

        if self.position_mode == "fixed_shares":
            size = int(self.position_value)
        elif self.position_mode == "fixed_pct":
            # position_value is percentage of capital (e.g. 10 means 10%)
            # We approximate capital from the engine (not directly accessible),
            # so we use a workaround: if no position, estimate from bar price
            budget = self.position_value / 100.0 * self.cta_engine.capital
            size = int(budget / bar.close_price)
        elif self.position_mode == "kelly":
            # Simplified Kelly: f* = (p * b - q) / b
            # where p = win rate, b = avg win / avg loss, q = 1 - p
            # We use a conservative estimate since we can't compute real stats mid-backtest
            # Default to 10% of capital as a safe Kelly approximation
            budget = 0.10 * self.cta_engine.capital
            size = int(budget / bar.close_price)
        else:
            size = 100

        # Round to trade unit
        if is_cn:
            size = (size // trade_unit) * trade_unit

        # Clamp to volume limit
        if max_vol > 0:
            if is_cn:
                max_vol = (max_vol // trade_unit) * trade_unit
            size = min(size, max_vol)

        return max(size, 0)


# ── Preset strategy templates ──

PRESET_TEMPLATES = {
    "value_dip": {
        "name": "价值低估买入",
        "description": "PE低于阈值且RSI超卖时买入，RSI超买或止损时卖出",
        "buy_rules": [
            {"type": "pe_below", "pe_max": 15},
            {"type": "rsi_oversold", "rsi_period": 14, "rsi_threshold": 30},
        ],
        "sell_rules": [
            {"type": "rsi_overbought", "rsi_period": 14, "rsi_threshold": 70},
        ],
        "stop_loss_pct": 5.0,
        "take_profit_pct": 20.0,
        "trailing_stop_pct": 0.0,
        "position_mode": "fixed_pct",
        "position_value": 30.0,
    },
    "trend_follow": {
        "name": "趋势追踪",
        "description": "MACD金叉且价格站上MA20时买入，MACD死叉或跌破MA20时卖出",
        "buy_rules": [
            {"type": "macd_golden_cross", "fast": 12, "slow": 26, "signal": 9},
            {"type": "price_above_ma", "ma_period": 20, "ma_type": "sma"},
        ],
        "sell_rules": [
            {"type": "macd_dead_cross", "fast": 12, "slow": 26, "signal": 9},
            {"type": "price_below_ma", "ma_period": 20, "ma_type": "sma"},
        ],
        "stop_loss_pct": 8.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 12.0,
        "position_mode": "fixed_pct",
        "position_value": 20.0,
    },
    "mean_reversion": {
        "name": "均值回归",
        "description": "价格触碰布林下轨时买入，触碰上轨或止盈时卖出",
        "buy_rules": [
            {"type": "boll_lower_break", "boll_period": 20, "boll_dev": 2.0},
        ],
        "sell_rules": [
            {"type": "boll_upper_break", "boll_period": 20, "boll_dev": 2.0},
        ],
        "stop_loss_pct": 5.0,
        "take_profit_pct": 15.0,
        "trailing_stop_pct": 0.0,
        "position_mode": "fixed_shares",
        "position_value": 100.0,
    },
}
