import sqlite3
import pandas as pd
import yfinance as yf
import numpy as np
from typing import Dict, List
from datetime import datetime, timezone

from vnpy.trader.object import BarData, TradeData
from vnpy.trader.constant import Exchange, Interval, Direction
from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine
from vnpy_portfoliostrategy.backtesting import BacktestingEngine

SYMBOLS = [
    "600519.SS", "601398.SS", "600036.SS", "601318.SS", "000858.SZ", 
    "000333.SZ", "600900.SS", "601012.SS", "600276.SS", "002594.SZ",
    "601888.SS", "603288.SS", "601166.SS", "600030.SS", "600104.SS",
]

def to_vnpy_symbol(yf_sym: str) -> str:
    if yf_sym.endswith(".SS"): return yf_sym.replace(".SS", ".SSE")
    if yf_sym.endswith(".SZ"): return yf_sym.replace(".SZ", ".SZSE")
    return yf_sym

VNPY_SYMBOLS = [to_vnpy_symbol(sym) for sym in SYMBOLS]

class CrossSectionalStrategy(StrategyTemplate):
    author = "AI Agent"
    
    rebalance_interval = 63
    
    days_since_rebalance = 0

    parameters = ["rebalance_interval"]
    variables = ["days_since_rebalance"]

    def __init__(self, strategy_engine: StrategyEngine, strategy_name: str, vt_symbols: List[str], setting: dict):
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)
        self.pe_df = setting.get("pe_df")
        self.mc_df = setting.get("mc_df")
        self.initial_capital = setting.get("initial_capital", 1000000.0)
        self.cash = self.initial_capital
        self.snapshots = []

    def on_init(self):
        self.write_log("策略初始化")
        self.load_bars(1)

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")
        
    def on_bars(self, bars: Dict[str, BarData]):
        if not bars:
            return
            
        dt = list(bars.values())[0].datetime
        # Use localize/tz-naive conversion appropriately for pandas lookup
        dt_pd = pd.Timestamp(dt).tz_localize(None).normalize()

        # Update equity manually since vnpy portfolio backtester hides it
        current_equity = self.cash
        for vt_symbol, bar in bars.items():
            pos = self.get_pos(vt_symbol)
            if pos > 0:
                current_equity += pos * bar.close_price
                
        self.snapshots.append({
            "date": dt.strftime("%Y-%m-%d"),
            "total_equity": float(current_equity),
            "cash": float(self.cash)
        })

        if self.days_since_rebalance == 0 or self.days_since_rebalance >= self.rebalance_interval:
            # Rebalance logic
            try:
                pe_cross = self.pe_df.loc[dt_pd]
                mc_cross = self.mc_df.loc[dt_pd]
            except KeyError:
                self.days_since_rebalance += 1
                return
                
            valid_symbols = []
            for vnpy_sym in self.vt_symbols:
                yf_sym = vnpy_sym.replace(".SSE", ".SS").replace(".SZSE", ".SZ")
                if vnpy_sym in bars and yf_sym in pe_cross.index and yf_sym in mc_cross.index:
                    if not pd.isna(pe_cross[yf_sym]) and not pd.isna(mc_cross[yf_sym]):
                        if pe_cross[yf_sym] < 20 and mc_cross[yf_sym] > 1000:
                            valid_symbols.append(vnpy_sym)
            
            # Sort by Market Cap descending and pick top 5
            sorted_symbols = sorted(valid_symbols, key=lambda s: mc_cross[s.replace(".SSE", ".SS").replace(".SZSE", ".SZ")], reverse=True)
            target_symbols = sorted_symbols[:5]

            # 1. Clear positions not in target
            for vt_symbol in self.vt_symbols:
                if vt_symbol not in target_symbols:
                    self.set_target(vt_symbol, 0)
                    
            # 2. Allocate to target
            if target_symbols:
                allocation = current_equity / len(target_symbols)
                for vt_symbol in target_symbols:
                    price = bars[vt_symbol].close_price
                    shares = int(allocation // price)
                    # Round down to 100 lot
                    shares = (shares // 100) * 100
                    self.set_target(vt_symbol, shares)
            
            self.rebalance_portfolio(bars)
            self.days_since_rebalance = 1
        else:
            self.days_since_rebalance += 1

    def update_trade(self, trade: TradeData) -> None:
        super().update_trade(trade)
        # Update our cash manually to track equity snapshots
        if trade.direction == Direction.LONG:
            self.cash -= (trade.price * trade.volume)
        elif trade.direction == Direction.SHORT:
            self.cash += (trade.price * trade.volume)
            
class PortfolioBacktester:
    def __init__(self, db_path="fundamentals.db"):
        self.db_path = db_path

    def load_fundamentals(self):
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query("SELECT * FROM valuation", conn)
        conn.close()
        
        df['date'] = pd.to_datetime(df['date'])
        pe_df = df.pivot(index='date', columns='symbol', values='pe_ttm')
        mc_df = df.pivot(index='date', columns='symbol', values='market_cap')
        return pe_df, mc_df

    def run_backtest(self, start_date="2020-01-01", end_date="2026-05-31"):
        print("Loading fundamentals from DB...")
        pe_df, mc_df = self.load_fundamentals()
        
        print("Loading K-lines...")
        df = yf.download(SYMBOLS, start=start_date, end=end_date, progress=False)
        closes = df['Close']
        if not isinstance(closes, pd.DataFrame):
            closes = pd.DataFrame(closes, columns=[SYMBOLS[0]])
        closes = closes.ffill()
        
        pe_df = pe_df.reindex(closes.index).ffill(limit=3)
        mc_df = mc_df.reindex(closes.index).ffill(limit=3)
        
        engine = BacktestingEngine()
        
        # vnpy portfolio needs a single dummy capital, we handle our own cash in strategy for snapshots
        engine.set_parameters(
            vt_symbols=VNPY_SYMBOLS,
            interval=Interval.DAILY,
            start=datetime.strptime(start_date, "%Y-%m-%d"),
            end=datetime.strptime(end_date, "%Y-%m-%d"),
            rates={sym: 0.0003 for sym in VNPY_SYMBOLS},
            slippages={sym: 0.0 for sym in VNPY_SYMBOLS},
            sizes={sym: 1 for sym in VNPY_SYMBOLS},
            priceticks={sym: 0.01 for sym in VNPY_SYMBOLS},
            capital=1_000_000.0,
        )
        
        engine.history_data.clear()
        engine.dts.clear()
        
        print("Transforming BarData...")
        for yf_symbol, vnpy_symbol in zip(SYMBOLS, VNPY_SYMBOLS):
            if isinstance(df.columns, pd.MultiIndex):
                symbol_df = df.xs(yf_symbol, level='Ticker', axis=1)
            else:
                symbol_df = df
                
            for dt, row in symbol_df.iterrows():
                if pd.isna(row['Close']): 
                    continue
                
                dt_utc = pd.Timestamp(dt).replace(tzinfo=timezone.utc).to_pydatetime()
                engine.dts.add(dt_utc)
                
                bar = BarData(
                    symbol=vnpy_symbol.split(".")[0],
                    exchange=Exchange.SSE if vnpy_symbol.endswith(".SSE") else Exchange.SZSE, 
                    datetime=dt_utc,
                    interval=Interval.DAILY,
                    volume=float(row.get('Volume', 0)),
                    open_price=float(row['Open']),
                    high_price=float(row['High']),
                    low_price=float(row['Low']),
                    close_price=float(row['Close']),
                    gateway_name="DB"
                )
                engine.history_data[(dt_utc, vnpy_symbol)] = bar
                
        print("Setting up strategy...")
        engine.add_strategy(CrossSectionalStrategy, {
            "pe_df": pe_df,
            "mc_df": mc_df,
            "rebalance_interval": 63,
            "initial_capital": 1_000_000.0
        })
        
        print("Running vnpy portfolio backtesting...")
        engine.run_backtesting()
        df_daily = engine.calculate_result()
        stats = engine.calculate_statistics()
        
        strat = engine.strategy
        
        trades = []
        for trade in engine.get_all_trades():
            trades.append({
                "date": trade.datetime.strftime("%Y-%m-%d"),
                "symbol": trade.symbol,
                "action": "BUY" if trade.direction == Direction.LONG else "SELL",
                "price": float(trade.price),
                "shares": int(trade.volume),
                "fee": 0,
                "realized_pnl": 0
            })
            
        metrics = {
            "annualized_return": {"risk": float(stats.get('annual_return', 0))},
            "max_drawdown": {"risk": float(stats.get('max_drawdown', 0))},
            "sharpe_ratio": float(stats.get('sharpe_ratio', 0)),
            "win_rate": 0,
            "mean": {"risk": 0},
            "std": {"risk": 0},
            "information_ratio": {"risk": 0}
        }
        
        final_value = df_daily['balance'].iloc[-1] if df_daily is not None else 1_000_000.0
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "model": "portfolio_cross_sectional_vnpy",
            "market": "CN",
            "final_account": float(final_value),
            "snapshots": strat.snapshots,
            "trades": trades,
            "metrics": metrics
        }
        
if __name__ == "__main__":
    pb = PortfolioBacktester()
    res = pb.run_backtest()
    print("Final Return:", res['metrics']['annualized_return'])
