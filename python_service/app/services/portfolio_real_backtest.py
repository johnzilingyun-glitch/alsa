import sqlite3
import pandas as pd
import yfinance as yf
import numpy as np
from typing import Dict, List
from datetime import datetime, timezone
import os
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from .backtest_engine_service import calculate_round_trip_trades
from ..quant.risk_metrics import RiskMetrics

_has_vnpy = False
try:
    from vnpy.trader.object import BarData, TradeData
    from vnpy.trader.constant import Exchange, Interval, Direction
    from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine
    from vnpy_portfoliostrategy.backtesting import BacktestingEngine
    _has_vnpy = True
except ImportError:
    class StrategyTemplate:
        def __init__(self, *args, **kwargs): pass
    class Direction:
        LONG = "LONG"
        SHORT = "SHORT"
    class StrategyEngine: pass
    class TradeData: pass
    class BarData: pass

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
        self.target_symbols = []
        self.pending_rebalance = False

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
        dt_pd = pd.Timestamp(dt).tz_localize(None).normalize()

        # 1. Execute pending rebalance first (transacting at today's prices)
        if self.pending_rebalance:
            # Clear positions not in target
            for vt_symbol in self.vt_symbols:
                if vt_symbol not in self.target_symbols:
                    self.set_target(vt_symbol, 0)
                    
            # Update current equity for allocation
            current_equity = self.cash
            for vt_symbol, bar in bars.items():
                pos = self.get_pos(vt_symbol)
                if pos > 0:
                    current_equity += pos * bar.close_price
                    
            # Allocate to target
            if self.target_symbols:
                allocation = current_equity / len(self.target_symbols)
                for vt_symbol in self.target_symbols:
                    if vt_symbol in bars:
                        price = bars[vt_symbol].close_price
                        shares = int(allocation // price)
                        is_cn = (".SSE" in vt_symbol) or (".SZSE" in vt_symbol)
                        if is_cn:
                            shares = (shares // 100) * 100
                        self.set_target(vt_symbol, max(0, shares))
            
            self.rebalance_portfolio(bars)
            self.pending_rebalance = False
            self.days_since_rebalance = 1
        else:
            if self.days_since_rebalance > 0:
                self.days_since_rebalance += 1

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

        # 2. Schedule rebalance decision (calculating targets to execute tomorrow)
        if self.days_since_rebalance == 0 or self.days_since_rebalance >= self.rebalance_interval:
            # Rebalance logic
            try:
                pe_cross = self.pe_df.loc[dt_pd]
                mc_cross = self.mc_df.loc[dt_pd]
            except KeyError:
                pe_cross = pd.Series(dtype=float)
                mc_cross = pd.Series(dtype=float)
                
            valid_symbols = []
            for vnpy_sym in self.vt_symbols:
                yf_sym = vnpy_sym.replace(".SSE", ".SS").replace(".SZSE", ".SZ")
                if vnpy_sym in bars:
                    pe_val = pe_cross.get(yf_sym, 10.0)
                    mc_val = mc_cross.get(yf_sym, 2000.0)
                    
                    if pd.isna(pe_val): pe_val = 10.0
                    if pd.isna(mc_val): mc_val = 2000.0
                    
                    if pe_val < 20 and mc_val > 1000:
                        valid_symbols.append(vnpy_sym)
            
            # Sort by Market Cap descending and pick top 5
            def get_mc(s):
                yf_sym = s.replace(".SSE", ".SS").replace(".SZSE", ".SZ")
                val = mc_cross.get(yf_sym, 2000.0)
                return 2000.0 if pd.isna(val) else val
                
            sorted_symbols = sorted(valid_symbols, key=get_mc, reverse=True)
            self.target_symbols = sorted_symbols[:5]
            self.pending_rebalance = True

    def update_trade(self, trade: TradeData) -> None:
        super().update_trade(trade)
        # Update our cash manually to track equity snapshots
        if trade.direction == Direction.LONG:
            self.cash -= (trade.price * trade.volume)
        elif trade.direction == Direction.SHORT:
            self.cash += (trade.price * trade.volume)
            
class PortfolioBacktester:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = os.path.join(PROJECT_ROOT, "fundamentals.db")
        else:
            self.db_path = db_path

    def load_fundamentals(self):
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query("SELECT * FROM valuation", conn)
        conn.close()
        
        df['date'] = pd.to_datetime(df['date'])
        pe_df = df.pivot(index='date', columns='symbol', values='pe_ttm')
        mc_df = df.pivot(index='date', columns='symbol', values='market_cap')
        return pe_df, mc_df

    def run_backtest(self, start_date="2020-01-01", end_date="2026-05-31", rebalance_interval=63, initial_capital=1000000.0, commission=0.0003, symbols=None):
        if not symbols:
            symbols = SYMBOLS
        else:
            symbols = [s.strip().replace(".SSE", ".SS").replace(".SZSE", ".SZ") for s in symbols if s.strip()]
            
        if not _has_vnpy:
            return self.run_pandas_portfolio_backtest(
                start_date=start_date,
                end_date=end_date,
                rebalance_interval=rebalance_interval,
                initial_capital=initial_capital,
                commission=commission,
                symbols=symbols
            )
            
        vnpy_symbols = [to_vnpy_symbol(sym) for sym in symbols]

        logger.info("Loading fundamentals from DB...")
        pe_df, mc_df = self.load_fundamentals()
        
        logger.info("Loading K-lines...")
        df = yf.download(symbols, start=start_date, end=end_date, progress=False)
        
        # Use Adj Close for closes to implement perfect front-adjustment
        closes = df['Adj Close'] if 'Adj Close' in df else df['Close']
        if not isinstance(closes, pd.DataFrame):
            closes = pd.DataFrame(closes, columns=[symbols[0]])
        closes = closes.ffill()
        
        pe_df = pe_df.reindex(closes.index).ffill(limit=3)
        mc_df = mc_df.reindex(closes.index).ffill(limit=3)
        
        engine = BacktestingEngine()
        
        # Determine slippage dynamically
        slippages_dict = {}
        for sym in vnpy_symbols:
            if ".SSE" in sym or ".SZSE" in sym:
                slippages_dict[sym] = 0.05  # 5 ticks for A-shares
            else:
                slippages_dict[sym] = 0.02  # 2 ticks for US shares

        # vnpy portfolio needs a single dummy capital, we handle our own cash in strategy for snapshots
        engine.set_parameters(
            vt_symbols=vnpy_symbols,
            interval=Interval.DAILY,
            start=datetime.strptime(start_date, "%Y-%m-%d"),
            end=datetime.strptime(end_date, "%Y-%m-%d"),
            rates={sym: commission for sym in vnpy_symbols},
            slippages=slippages_dict,
            sizes={sym: 1 for sym in vnpy_symbols},
            priceticks={sym: 0.01 for sym in vnpy_symbols},
            capital=initial_capital,
        )
        
        engine.history_data.clear()
        engine.dts.clear()
        
        logger.info("Transforming BarData...")
        for yf_symbol, vnpy_symbol in zip(symbols, vnpy_symbols):
            if isinstance(df.columns, pd.MultiIndex):
                if yf_symbol in df.columns.levels[1]:
                    symbol_df = df.xs(yf_symbol, level='Ticker', axis=1)
                else:
                    symbol_df = pd.DataFrame()
            else:
                symbol_df = df
                
            if symbol_df.empty:
                continue
                
            for dt, row in symbol_df.iterrows():
                close_raw = row.get('Close')
                if pd.isna(close_raw) or close_raw <= 0: 
                    continue
                
                dt_utc = pd.Timestamp(dt).replace(tzinfo=timezone.utc).to_pydatetime()
                engine.dts.add(dt_utc)
                
                adj_close = row.get('Adj Close', close_raw)
                if pd.isna(adj_close):
                    adj_close = close_raw
                    
                adj_factor = float(adj_close / close_raw)
                
                exchange = Exchange.SSE if vnpy_symbol.endswith(".SSE") else (Exchange.SZSE if vnpy_symbol.endswith(".SZSE") else Exchange.SMART)
                
                bar = BarData(
                    symbol=vnpy_symbol.split(".")[0],
                    exchange=exchange,
                    datetime=dt_utc,
                    interval=Interval.DAILY,
                    volume=float(row.get('Volume', 0)),
                    open_price=float(row['Open'] * adj_factor),
                    high_price=float(row['High'] * adj_factor),
                    low_price=float(row['Low'] * adj_factor),
                    close_price=float(adj_close),
                    gateway_name="DB"
                )
                engine.history_data[(dt_utc, vnpy_symbol)] = bar
                
        logger.info("Setting up strategy...")
        engine.add_strategy(CrossSectionalStrategy, {
            "pe_df": pe_df,
            "mc_df": mc_df,
            "rebalance_interval": rebalance_interval,
            "initial_capital": initial_capital
        })
        
        logger.info("Running vnpy portfolio backtesting...")
        engine.run_backtesting()
        df_daily = engine.calculate_result()
        
        # Guard: if calculate_result returned empty/None df, return error early
        if df_daily is None or df_daily.empty or "net_pnl" not in df_daily.columns:
            raise ValueError(
                "组合回测失败：在指定期间内没有产生任何交易结果。"
                "可能原因：K线数据不足、基本面数据缺失、或策略未触发信号。"
            )
        
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
            
        # Benchmark attribution
        is_cn = any(".SS" in sym or ".SZ" in sym or ".SSE" in sym or ".SZSE" in sym for sym in symbols)
        benchmark_symbol = "000300.SS" if is_cn else "^GSPC"
        beta = 1.0
        ann_ret = float(stats.get('annual_return', 0)) / 100.0 if stats.get('annual_return') else 0.0
        alpha = ann_ret - 0.05
        treynor = ann_ret
        info_ratio = float(stats.get('sharpe_ratio', 0))
        
        bench_close = None
        try:
            if df_daily is not None and not df_daily.empty:
                bench_df = yf.download(benchmark_symbol, start=start_date, end=end_date, progress=False)
                if not bench_df.empty:
                    bench_close = bench_df['Adj Close'] if 'Adj Close' in bench_df else bench_df['Close']
                    if isinstance(bench_close, pd.DataFrame):
                        bench_close = bench_close.iloc[:, 0]
                else:
                    bench_close = pd.Series(np.nan, index=df_daily.index)

                if is_cn:
                    try:
                        etf_df = yf.download("510300.SS", start=start_date, end=end_date, progress=False)
                        if not etf_df.empty:
                            etf_close = etf_df['Adj Close'] if 'Adj Close' in etf_df else etf_df['Close']
                            if isinstance(etf_close, pd.DataFrame):
                                etf_close = etf_close.iloc[:, 0]
                            etf_close = etf_close * 1000.0
                            
                            bench_close = bench_close.reindex(df_daily.index)
                            etf_close = etf_close.reindex(df_daily.index).ffill().bfill()
                            bench_close = bench_close.fillna(etf_close)
                    except Exception as e_etf:
                        logger.warning(f"Failed to load ETF fallback in VNPY: {e_etf}")

                bench_close = bench_close.reindex(df_daily.index).ffill().bfill()
                
                bench_df_temp = pd.DataFrame(index=df_daily.index)
                bench_df_temp['return'] = bench_close.pct_change().fillna(0)
                bench_returns = bench_df_temp['return']
                strat_returns = df_daily['return']
                
                cov = np.cov(strat_returns, bench_returns)
                bench_var = np.var(bench_returns)
                if bench_var > 0:
                    beta = float(cov[0, 1] / bench_var)
                
                if len(bench_close) > 0 and bench_close.iloc[0] > 0:
                    total_bench_ret = float(bench_close.iloc[-1] / bench_close.iloc[0]) - 1.0
                else:
                    total_bench_ret = 0.0
                days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
                if days > 0:
                    bench_ann_return = float((1.0 + total_bench_ret) ** (365.25 / days) - 1.0)
                else:
                    bench_ann_return = 0.05
                    
                    rf = 0.02
                    alpha = float(ann_ret - (rf + beta * (bench_ann_return - rf)))
                    treynor = float((ann_ret - rf) / beta) if beta != 0 else 0.0
                    
                    active_returns = strat_returns - bench_returns
                    tracking_error = np.std(active_returns)
                    if tracking_error > 0:
                        info_ratio = float((ann_ret - bench_ann_return) / (tracking_error * np.sqrt(252)))
                    else:
                        info_ratio = 0.0
        except Exception as e:
            logger.warning(f"Failed to calculate risk attribution: {e}")
            
        # Compute Calmar and Sortino for portfolio
        max_dd = float(stats.get('max_drawdown', 0)) / 100.0
        calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0
        
        downside = df_daily['return'][df_daily['return'] < 0] if (df_daily is not None and 'return' in df_daily.columns) else pd.Series()
        downside_std = float(downside.std()) if len(downside) > 1 else 1e-10
        downside_std_ann = downside_std * np.sqrt(252)
        sortino = float((ann_ret - 0.02) / downside_std_ann) if downside_std_ann > 1e-10 else 0.0
        
        # Calculate stats on round trip trades
        round_trips = calculate_round_trip_trades(trades, commission_rate=0.0003)
        wins = [t["pnl"] for t in round_trips if t["pnl"] > 0]
        losses = [t["pnl"] for t in round_trips if t["pnl"] < 0]
        
        win_rate = len(wins) / len(round_trips) if round_trips else 0.0
        
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = abs(float(np.mean(losses))) if losses else 1e-10
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 1e-10 else 0.0
        
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1e-10
        profit_factor = gross_profit / gross_loss if gross_loss > 1e-10 else 0.0
        
        max_consec_loss = 0
        cur_consec_loss = 0
        for t in round_trips:
            if t["pnl"] < 0:
                cur_consec_loss += 1
                max_consec_loss = max(max_consec_loss, cur_consec_loss)
            else:
                cur_consec_loss = 0
                
        hold_days = []
        for t in round_trips:
            if isinstance(t["entry_time"], datetime) and isinstance(t["exit_time"], datetime):
                days = (t["exit_time"] - t["entry_time"]).days
                hold_days.append(days)
        avg_holding_days = float(np.mean(hold_days)) if hold_days else 0.0

        metrics = {
            "annualized_return": {"risk": float(ann_ret)},
            "max_drawdown": {"risk": float(max_dd)},
            "sharpe_ratio": float(stats.get('sharpe_ratio', 0)),
            "win_rate": float(win_rate),
            "mean": {"risk": 0},
            "std": {"risk": 0},
            "alpha": float(alpha),
            "beta": float(beta),
            "treynor_ratio": float(treynor),
            "information_ratio": float(info_ratio),
            "calmar_ratio": float(calmar),
            "sortino_ratio": float(sortino),
            "profit_factor": float(profit_factor),
            "profit_loss_ratio": float(profit_loss_ratio),
            "max_consecutive_loss": int(max_consec_loss),
            "avg_holding_days": float(avg_holding_days)
        }
        
        final_value = df_daily['balance'].iloc[-1] if df_daily is not None else 1_000_000.0
        
        # Map benchmark close to snapshots
        updated_snapshots = []
        bench_close_dict = {}
        if bench_close is not None and not bench_close.empty:
            for dt_idx, val in bench_close.items():
                bench_close_dict[dt_idx.strftime("%Y-%m-%d")] = float(val)
        
        for snap in strat.snapshots:
            d_str = snap["date"]
            updated_snapshots.append({
                "date": d_str,
                "total_equity": snap["total_equity"],
                "cash": snap["cash"],
                "close_price": bench_close_dict.get(d_str, 0.0)
            })
            
        return {
            "start_date": start_date,
            "end_date": end_date,
            "model": "portfolio_cross_sectional_vnpy",
            "market": "CN",
            "final_account": float(final_value),
            "snapshots": updated_snapshots,
            "trades": trades,
            "metrics": metrics
        }
        
    def run_pandas_portfolio_backtest(self, start_date="2020-01-01", end_date="2026-05-31", rebalance_interval=63, initial_capital=1000000.0, commission=0.0003, symbols=None, closes=None):
        if not symbols:
            symbols = SYMBOLS

        # 1. Load fundamentals
        logger.info("Loading fundamentals from DB (pandas mode)...")
        pe_df, mc_df = self.load_fundamentals()
        
        # 2. Fetch closes from yfinance if not provided
        if closes is None:
            logger.info("Loading K-lines (pandas mode)...")
            df = yf.download(symbols, start=start_date, end=end_date, progress=False)
            closes = df['Close'] if 'Close' in df else df
            if not isinstance(closes, pd.DataFrame):
                closes = pd.DataFrame(closes, columns=[symbols[0]])
            closes = closes.ffill().bfill()
        
        pe_df = pe_df.reindex(closes.index).ffill(limit=3).bfill()
        mc_df = mc_df.reindex(closes.index).ffill(limit=3).bfill()
        
        # 3. Simulate rebalancing (decision on day i, execution on day i+1)
        cash = initial_capital
        positions = {sym: 0 for sym in symbols}
        
        portfolio_values = []
        snapshots = []
        trades = []
        
        days_since_rebalance = 0
        pending_rebalance = False
        target_symbols = []
        
        for i in range(len(closes.index)):
            dt = closes.index[i]
            d_str = dt.strftime("%Y-%m-%d")
            current_prices = closes.iloc[i]
            
            # Execute rebalance if scheduled (using current price)
            if pending_rebalance:
                # Sell all existing positions
                for sym in symbols:
                    if positions[sym] > 0:
                        price = current_prices.get(sym, 0.0)
                        if not pd.isna(price) and price > 0:
                            revenue = positions[sym] * price
                            fee = revenue * commission
                            cash += revenue - fee
                            
                            trades.append({
                                "date": d_str,
                                "symbol": sym.split(".")[0],
                                "action": "SELL",
                                "price": float(price),
                                "shares": int(positions[sym]),
                                "fee": float(fee),
                                "realized_pnl": 0.0
                            })
                            positions[sym] = 0
                
                # Buy target positions
                if len(target_symbols) > 0:
                    allocation = cash / len(target_symbols)
                    for sym in target_symbols:
                        price = current_prices.get(sym, 0.0)
                        shares = int(allocation // price)
                        is_cn = (".SS" in sym) or (".SZ" in sym)
                        if is_cn:
                            shares = (shares // 100) * 100
                            
                        if shares > 0:
                            cost = shares * price
                            fee = cost * commission
                            cash -= cost + fee
                            positions[sym] = shares
                            
                            trades.append({
                                "date": d_str,
                                "symbol": sym.split(".")[0],
                                "action": "BUY",
                                "price": float(price),
                                "shares": int(shares),
                                "fee": float(fee),
                                "realized_pnl": 0.0
                            })
                
                pending_rebalance = False
                days_since_rebalance = 1
            else:
                if i > 0:
                    days_since_rebalance += 1
            
            # Calculate current portfolio value AFTER execution
            current_equity = cash
            for sym in symbols:
                if positions[sym] > 0:
                    price = current_prices.get(sym, 0.0)
                    if not pd.isna(price):
                        current_equity += positions[sym] * price
            
            snapshots.append({
                "date": d_str,
                "total_equity": float(current_equity),
                "cash": float(cash)
            })
            portfolio_values.append(current_equity)
            
            # Schedule next rebalance decision
            if days_since_rebalance == 0 or days_since_rebalance >= rebalance_interval:
                dt_pd = pd.Timestamp(dt).tz_localize(None).normalize()
                try:
                    pe_cross = pe_df.loc[dt_pd]
                    mc_cross = mc_df.loc[dt_pd]
                except KeyError:
                    pe_cross = pd.Series(dtype=float)
                    mc_cross = pd.Series(dtype=float)
                
                valid_symbols = []
                for sym in symbols:
                    pe_val = pe_cross.get(sym, 10.0)
                    mc_val = mc_cross.get(sym, 2000.0)
                    if pd.isna(pe_val): pe_val = 10.0
                    if pd.isna(mc_val): mc_val = 2000.0
                    
                    price = current_prices.get(sym, 0.0)
                    if not pd.isna(price) and price > 0:
                        if pe_val < 20 and mc_val > 1000:
                            valid_symbols.append(sym)
                
                sorted_symbols = sorted(valid_symbols, key=lambda s: mc_cross.get(s, 2000.0), reverse=True)
                target_symbols = sorted_symbols[:5]
                pending_rebalance = True
                
            current_equity = cash
            for sym in symbols:
                if positions[sym] > 0:
                    price = current_prices.get(sym, 0.0)
                    if not pd.isna(price):
                        current_equity += positions[sym] * price
            
            snapshots.append({
                "date": d_str,
                "total_equity": float(current_equity),
                "cash": float(cash)
            })
            portfolio_values.append(current_equity)

        final_value = portfolio_values[-1] if portfolio_values else initial_capital
        total_ret = (final_value - initial_capital) / initial_capital
        
        eq_series = pd.Series(portfolio_values)
        daily_returns = eq_series.pct_change().dropna()
        
        ann_ret = ((1 + total_ret) ** (365.25 / max(len(closes.index), 1)) - 1)
        sharpe = RiskMetrics.compute_sharpe(daily_returns)
        
        running_max = eq_series.cummax()
        drawdown = (eq_series - running_max) / running_max
        max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0
        
        round_trips = calculate_round_trip_trades(trades, commission)
        wins = [t["pnl"] for t in round_trips if t["pnl"] > 0]
        losses = [t["pnl"] for t in round_trips if t["pnl"] < 0]
        win_rate = len(wins) / len(round_trips) if round_trips else 0.0
        
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = abs(float(np.mean(losses))) if losses else 1e-10
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 1e-10 else 0.0
        
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1e-10
        profit_factor = gross_profit / gross_loss if gross_loss > 1e-10 else 0.0
        
        max_consec_loss = 0
        cur = 0
        for t in round_trips:
            if t["pnl"] < 0:
                cur += 1
                max_consec_loss = max(max_consec_loss, cur)
            else:
                cur = 0
                
        hold_days = []
        for t in round_trips:
            if isinstance(t.get("entry_time"), datetime) and isinstance(t.get("exit_time"), datetime):
                hold_days.append((t["exit_time"] - t["entry_time"]).days)
        avg_holding_days = float(np.mean(hold_days)) if hold_days else 0.0
        
        beta = 1.0
        alpha = ann_ret - 0.05
        treynor = ann_ret
        info_ratio = sharpe
        
        is_cn = any(".SS" in sym or ".SZ" in sym or ".SSE" in sym or ".SZSE" in sym for sym in symbols)
        benchmark_symbol = "000300.SS" if is_cn else "^GSPC"
        bench_close = None
        try:
            bench_df = yf.download(benchmark_symbol, start=start_date, end=end_date, progress=False)
            if not bench_df.empty:
                bench_close = bench_df['Adj Close'] if 'Adj Close' in bench_df else bench_df['Close']
                if isinstance(bench_close, pd.DataFrame):
                    bench_close = bench_close.iloc[:, 0]
            else:
                bench_close = pd.Series(np.nan, index=closes.index)

            if is_cn:
                try:
                    etf_df = yf.download("510300.SS", start=start_date, end=end_date, progress=False)
                    if not etf_df.empty:
                        etf_close = etf_df['Adj Close'] if 'Adj Close' in etf_df else etf_df['Close']
                        if isinstance(etf_close, pd.DataFrame):
                            etf_close = etf_close.iloc[:, 0]
                        etf_close = etf_close * 1000.0
                        
                        bench_close = bench_close.reindex(closes.index)
                        etf_close = etf_close.reindex(closes.index).ffill().bfill()
                        bench_close = bench_close.fillna(etf_close)
                except Exception as e_etf:
                    logger.warning(f"Failed to load ETF fallback: {e_etf}")

            bench_close = bench_close.reindex(closes.index).ffill().bfill()
            
            bench_df_temp = pd.DataFrame(index=closes.index)
            bench_df_temp['return'] = bench_close.pct_change().fillna(0)
            bench_returns = bench_df_temp['return']
            
            cov = np.cov(daily_returns, bench_returns.values[1:])
            bench_var = np.var(bench_returns)
            if bench_var > 0:
                beta = float(cov[0, 1] / bench_var)
            rf = 0.02
            alpha = float(ann_ret - (rf + beta * (0.05 - rf)))
        except Exception:
            pass
            
        metrics = {
            "annualized_return": {"risk": float(ann_ret)},
            "max_drawdown": {"risk": float(max_dd)},
            "sharpe_ratio": float(sharpe),
            "win_rate": float(win_rate),
            "mean": {"risk": float(daily_returns.mean()) if len(daily_returns) > 0 else 0.0},
            "std": {"risk": float(daily_returns.std()) if len(daily_returns) > 0 else 0.0},
            "alpha": float(alpha),
            "beta": float(beta),
            "treynor_ratio": float(treynor),
            "information_ratio": float(info_ratio),
            "calmar_ratio": float(ann_ret / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0),
            "sortino_ratio": float(RiskMetrics.compute_sortino(daily_returns)),
            "value_at_risk": float(RiskMetrics.compute_var(daily_returns)),
            "profit_factor": float(profit_factor),
            "profit_loss_ratio": float(profit_loss_ratio),
            "max_consecutive_loss": int(max_consec_loss),
            "avg_holding_days": float(avg_holding_days)
        }
        
        bench_close_dict = {}
        try:
            if not bench_df.empty:
                for dt_idx, val in bench_close.items():
                    bench_close_dict[dt_idx.strftime("%Y-%m-%d")] = float(val)
        except Exception:
            pass
            
        for snap in snapshots:
            d_str = snap["date"]
            snap["close_price"] = bench_close_dict.get(d_str, 0.0)
            
        return {
            "start_date": start_date,
            "end_date": end_date,
            "model": "portfolio_cross_sectional_pandas",
            "market": "CN",
            "final_account": float(final_value),
            "snapshots": snapshots,
            "trades": trades,
            "metrics": metrics
        }

if __name__ == "__main__":
    pb = PortfolioBacktester()
    res = pb.run_backtest()
    print("Final Return:", res['metrics']['annualized_return'])
