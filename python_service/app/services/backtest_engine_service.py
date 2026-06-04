import asyncio
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy_ctastrategy import CtaTemplate
from vnpy_ctastrategy.backtesting import BacktestingEngine

from vnpy.trader.utility import ArrayManager
from datetime import datetime, timezone

from .data_sync_service import data_sync_service

class MockAgentCtaStrategy(CtaTemplate):
    author = "AI Agent"

    fast_window = 5
    slow_window = 20

    fast_ma0 = 0.0
    fast_ma1 = 0.0
    slow_ma0 = 0.0
    slow_ma1 = 0.0

    parameters = ["fast_window", "slow_window"]
    variables = ["fast_ma0", "fast_ma1", "slow_ma0", "slow_ma1"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.am = ArrayManager()

    def on_init(self):
        self.write_log("策略初始化")
        self.load_bar(10)

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    def on_bar(self, bar: BarData):
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        fast_ma = self.am.sma(self.fast_window, array=True)
        self.fast_ma0 = fast_ma[-1]
        self.fast_ma1 = fast_ma[-2]

        slow_ma = self.am.sma(self.slow_window, array=True)
        self.slow_ma0 = slow_ma[-1]
        self.slow_ma1 = slow_ma[-2]

        cross_over = self.fast_ma0 > self.slow_ma0 and self.fast_ma1 < self.slow_ma1
        cross_below = self.fast_ma0 < self.slow_ma0 and self.fast_ma1 > self.slow_ma1

        size = 1000 if bar.exchange == Exchange.SSE else 100

        if cross_over:
            if self.pos == 0:
                self.buy(bar.close_price * 1.05, size)
            elif self.pos < 0:
                self.cover(bar.close_price * 1.05, abs(self.pos))
                self.buy(bar.close_price * 1.05, size)
        elif cross_below:
            if self.pos == 0:
                self.short(bar.close_price * 0.95, size)
            elif self.pos > 0:
                self.sell(bar.close_price * 0.95, abs(self.pos))
                self.short(bar.close_price * 0.95, size)


class BacktestEngine:
    def __init__(self, init_cash: float = 100000.0, commission: float = 0.0003):
        self.init_cash = init_cash
        self.commission = commission

    async def run(self, start_date: str, end_date: str, strategy: str, market: str):
        if strategy == "portfolio_cross_sectional":
            from .portfolio_real_backtest import PortfolioBacktester
            pb = PortfolioBacktester()
            return pb.run_backtest(start_date=start_date, end_date=end_date)
            
        target_symbol = "600519" if market == "CN" else "AAPL"
        exchange = Exchange.SSE if market == "CN" else Exchange.SMART
        vt_symbol = f"{target_symbol}.{exchange.value}"
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        # 1. Sync data to local SQLite database
        success = await data_sync_service.ensure_local_data(
            target_symbol, exchange, start_dt, end_dt
        )
        if not success:
            print("Data sync failed or no data available. Proceeding might result in empty backtest.")

        # 2. Setup vn.py BacktestingEngine
        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol=vt_symbol,
            interval=Interval.DAILY,
            start=start_dt,
            end=end_dt,
            rate=self.commission,
            slippage=0.01 if market != "CN" else 0.0,
            size=1,
            pricetick=0.01,
            capital=self.init_cash,
        )
        
        engine.add_strategy(MockAgentCtaStrategy, {})
        
        # 3. Load data from local database & Run
        engine.load_data()
        engine.run_backtesting()
        
        # Calculate statistics
        df_daily = engine.calculate_result()
        stats = engine.calculate_statistics(df_daily)
        
        # Extract Results
        snapshots = []
        if df_daily is not None:
            for dt, row in df_daily.iterrows():
                snapshots.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "total_equity": row["balance"],
                    "cash": 0 # vnpy daily result tracks balance, not available cash directly in this df
                })

        trades_list = []
        trades = engine.get_all_trades()
        for t in trades:
            trades_list.append({
                "date": t.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": t.symbol,
                "action": "BUY" if t.direction.value == "多" else "SELL", # vnpy uses Direction.LONG / SHORT
                "shares": t.volume,
                "price": t.price,
                "fee": t.price * t.volume * self.commission,
                "realized_pnl": 0 # CTA standard trades don't attach pnl, the engine calculates it globally
            })

        final_equity = stats.get("end_balance", self.init_cash)
        
        # Default vn.py statistics mapping
        # "annual_return", "max_drawdown", "sharpe_ratio", "win_rate"
        
        ann_ret = stats.get("annual_return", 0) / 100.0 if stats.get("annual_return") else 0
        max_dd = stats.get("max_ddpercent", stats.get("max_drawdown", 0)) / 100.0
        sharpe = stats.get("sharpe_ratio", 0)
        win_rate = stats.get("winning_rate", stats.get("win_rate", 0)) / 100.0
        mean_ret = stats.get("daily_return", 0) / 100.0 if stats.get("daily_return") else 0
        std_ret = stats.get("return_std", 0) / 100.0 if stats.get("return_std") else 0
        
        # We need to map vn.py actions. vn.py direction is an Enum (Direction.LONG, Direction.SHORT)
        # Let's clean up the trade list
        trades_list_clean = []
        for t in trades:
            from vnpy.trader.constant import Direction
            act = "BUY" if t.direction == Direction.LONG else "SELL"
            trades_list_clean.append({
                "date": t.datetime.strftime("%Y-%m-%d"),
                "symbol": t.symbol,
                "action": act,
                "shares": t.volume,
                "price": float(t.price),
                "fee": float(t.price * t.volume * self.commission),
                "realized_pnl": 0 # we leave it 0 or calculate it
            })

        return {
            "start_date": start_date,
            "end_date": end_date,
            "model": strategy,
            "market": market,
            "final_account": float(final_equity),
            "snapshots": snapshots,
            "trades": trades_list_clean,
            "metrics": {
                "annualized_return": {"risk": float(ann_ret)},
                "max_drawdown": {"risk": float(max_dd)},
                "sharpe_ratio": float(sharpe),
                "win_rate": float(win_rate),
                "mean": {"risk": float(mean_ret)},
                "std": {"risk": float(std_ret)},
                "information_ratio": {"risk": float(sharpe)} # Approximation
            }
        }
