import asyncio
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

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

        size = 100
        if bar.volume > 0:
            max_allowed = int(bar.volume * 0.10)
            is_cn = (".SSE" in self.vt_symbol) or (".SZSE" in self.vt_symbol)
            if is_cn:
                max_allowed = (max_allowed // 100) * 100
            size = min(100, max_allowed)

        if size <= 0:
            return

        if cross_over:
            if self.pos == 0:
                self.buy(bar.close_price, size)
            elif self.pos < 0:
                self.cover(bar.close_price, abs(self.pos))
                self.buy(bar.close_price, size)
        elif cross_below:
            if self.pos == 0:
                self.short(bar.close_price, size)
            elif self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
                self.short(bar.close_price, size)


def calculate_round_trip_trades(trades, commission_rate=0.0003):
    """
    Pairs individual execution trades (BUY/SELL) into round-trip trades.
    Supports FIFO matching for both Long and Short positions.
    """
    from collections import defaultdict
    trades_by_symbol = defaultdict(list)
    for t in trades:
        symbol = t.get("symbol") if isinstance(t, dict) else t.symbol
        trades_by_symbol[symbol].append(t)
        
    round_trips = []
    
    for symbol, sym_trades in trades_by_symbol.items():
        long_entries = []  # list of (datetime, price, shares, fee)
        short_entries = [] # list of (datetime, price, shares, fee)
        
        for et in sym_trades:
            is_dict = isinstance(et, dict)
            dt = et.get("date") if is_dict else et.datetime
            if isinstance(dt, str):
                try:
                    dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        dt = datetime.strptime(dt, "%Y-%m-%d")
                    except ValueError:
                        pass
            
            action = et.get("action") if is_dict else et.direction.value
            if not is_dict:
                from vnpy.trader.constant import Direction
                action = "BUY" if et.direction == Direction.LONG else "SELL"
            
            price = float(et.get("price") if is_dict else et.price)
            volume = float(et.get("shares") if is_dict else et.volume)
            fee = float(et.get("fee") if is_dict else (price * volume * commission_rate))
            
            if action == "BUY":
                while volume > 0 and short_entries:
                    ent_dt, ent_price, ent_vol, ent_fee = short_entries[0]
                    match_vol = min(volume, ent_vol)
                    
                    gross_pnl = (ent_price - price) * match_vol
                    entry_fee_share = ent_fee * (match_vol / ent_vol)
                    exit_fee_share = fee * (match_vol / volume)
                    total_fee = entry_fee_share + exit_fee_share
                    net_pnl = gross_pnl - total_fee
                    
                    round_trips.append({
                        "symbol": symbol,
                        "direction": "SHORT",
                        "entry_time": ent_dt,
                        "exit_time": dt,
                        "entry_price": ent_price,
                        "exit_price": price,
                        "volume": match_vol,
                        "pnl": net_pnl,
                        "pnl_pct": (ent_price - price) / ent_price * 100 if ent_price > 0 else 0.0
                    })
                    
                    volume -= match_vol
                    if match_vol == ent_vol:
                        short_entries.pop(0)
                    else:
                        short_entries[0] = (ent_dt, ent_price, ent_vol - match_vol, ent_fee - entry_fee_share)
                
                if volume > 0:
                    long_entries.append((dt, price, volume, fee))
                    
            elif action == "SELL":
                while volume > 0 and long_entries:
                    ent_dt, ent_price, ent_vol, ent_fee = long_entries[0]
                    match_vol = min(volume, ent_vol)
                    
                    gross_pnl = (price - ent_price) * match_vol
                    entry_fee_share = ent_fee * (match_vol / ent_vol)
                    exit_fee_share = fee * (match_vol / volume)
                    total_fee = entry_fee_share + exit_fee_share
                    net_pnl = gross_pnl - total_fee
                    
                    round_trips.append({
                        "symbol": symbol,
                        "direction": "LONG",
                        "entry_time": ent_dt,
                        "exit_time": dt,
                        "entry_price": ent_price,
                        "exit_price": price,
                        "volume": match_vol,
                        "pnl": net_pnl,
                        "pnl_pct": (price - ent_price) / ent_price * 100 if ent_price > 0 else 0.0
                    })
                    
                    volume -= match_vol
                    if match_vol == ent_vol:
                        long_entries.pop(0)
                    else:
                        long_entries[0] = (ent_dt, ent_price, ent_vol - match_vol, ent_fee - entry_fee_share)
                
                if volume > 0:
                    short_entries.append((dt, price, volume, fee))
                    
    return round_trips


class BacktestEngine:
    def __init__(self, init_cash: float = 100000.0, commission: float = 0.0003):
        self.init_cash = init_cash
        self.commission = commission

    async def run(self, start_date: str, end_date: str, strategy: str, market: str, params: Optional[Dict[str, Any]] = None):
        if strategy == "portfolio_cross_sectional":
            from .portfolio_real_backtest import PortfolioBacktester
            pb = PortfolioBacktester()
            rebalance_interval = 63
            custom_symbols = None
            if params:
                rebalance_interval = int(params.get("rebalance_interval", 63))
                custom_symbols = params.get("custom_symbols")
            return pb.run_backtest(
                start_date=start_date,
                end_date=end_date,
                rebalance_interval=rebalance_interval,
                initial_capital=self.init_cash,
                commission=self.commission,
                symbols=custom_symbols
            )
            
        # Extract target symbol dynamically from params
        target_symbol = params.get("target_symbol") if params else None
        if not target_symbol:
            target_symbol = "600519" if market == "CN" else "AAPL"
        else:
            target_symbol = target_symbol.strip()
            
        # Dynamically determine exchange
        if market == "CN":
            if target_symbol.startswith("6"):
                exchange = Exchange.SSE
            elif target_symbol.startswith("0") or target_symbol.startswith("3"):
                exchange = Exchange.SZSE
            else:
                exchange = Exchange.SSE
            slippage = 0.05  # 5 ticks slippage for CN A-shares
        else:
            exchange = Exchange.SMART
            slippage = 0.02  # 2 ticks slippage for US shares
            
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
            slippage=slippage,
            size=1,
            pricetick=0.01,
            capital=self.init_cash,
        )
        
        if strategy == "custom_rule":
            import json
            from .custom_rule_strategy import CustomRuleCtaStrategy
            strategy_settings = {
                "buy_rules_json": json.dumps(params.get("buy_rules", []) if params else []),
                "sell_rules_json": json.dumps(params.get("sell_rules", []) if params else []),
                "position_mode": params.get("position_mode", "fixed_shares") if params else "fixed_shares",
                "position_value": float(params.get("position_value", 100)) if params else 100.0,
                "stop_loss_pct": float(params.get("stop_loss_pct", 0)) if params else 0.0,
                "take_profit_pct": float(params.get("take_profit_pct", 0)) if params else 0.0,
                "trailing_stop_pct": float(params.get("trailing_stop_pct", 0)) if params else 0.0,
            }
            engine.add_strategy(CustomRuleCtaStrategy, strategy_settings)
        else:
            strategy_settings = {}
            if params:
                if "fast_window" in params:
                    strategy_settings["fast_window"] = int(params["fast_window"])
                if "slow_window" in params:
                    strategy_settings["slow_window"] = int(params["slow_window"])
            engine.add_strategy(MockAgentCtaStrategy, strategy_settings)
        
        # 3. Load data from local database & Run
        engine.load_data()
        
        # Guard: if no history data was loaded, return error early
        if not engine.history_data:
            raise ValueError(
                f"回测失败：未能加载到 {vt_symbol} 在 {start_date} 至 {end_date} 期间的K线数据。"
                "请检查数据源是否可用，或确认股票代码和日期范围是否正确。"
            )
        
        engine.run_backtesting()
        
        # Calculate statistics
        df_daily = engine.calculate_result()
        
        # Guard: if calculate_result returned empty/None df, return error early
        if df_daily is None or df_daily.empty or "net_pnl" not in df_daily.columns:
            raise ValueError(
                f"回测失败：{vt_symbol} 在指定期间内没有产生任何交易结果。"
                "可能原因：K线数据不足、策略未触发信号、或数据格式不匹配。"
            )
        
        stats = engine.calculate_statistics(df_daily)
        
        # Extract Results
        snapshots = []
        date_to_close = {}
        for bar in engine.history_data:
            d_str = bar.datetime.strftime("%Y-%m-%d")
            date_to_close[d_str] = float(bar.close_price)

        if df_daily is not None:
            for dt, row in df_daily.iterrows():
                d_str = dt.strftime("%Y-%m-%d")
                snapshots.append({
                    "date": d_str,
                    "total_equity": float(row["balance"]),
                    "close_price": date_to_close.get(d_str, 0.0),
                    "cash": 0
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

        # Benchmark attribution
        benchmark_symbol = "000300.SS" if market == "CN" else "^GSPC"
        beta = 1.0
        alpha = ann_ret - 0.05
        treynor = ann_ret
        info_ratio = sharpe
        
        try:
            if df_daily is not None and not df_daily.empty:
                bench_df = yf.download(benchmark_symbol, start=start_date, end=end_date, progress=False)
                if not bench_df.empty:
                    bench_close = bench_df['Adj Close'] if 'Adj Close' in bench_df else bench_df['Close']
                    if isinstance(bench_close, pd.DataFrame):
                        bench_close = bench_close.iloc[:, 0]
                    bench_df['return'] = bench_close.pct_change().fillna(0)
                    bench_returns = bench_df['return'].reindex(df_daily.index).fillna(0)
                    strat_returns = df_daily['return']
                    
                    cov = np.cov(strat_returns, bench_returns)
                    bench_var = np.var(bench_returns)
                    if bench_var > 0:
                        beta = float(cov[0, 1] / bench_var)
                    
                    total_bench_ret = float(bench_close.iloc[-1] / bench_close.iloc[0]) - 1.0
                    days = (end_dt - start_dt).days
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
            print(f"Failed to calculate risk attribution: {e}")

        # Compute new Vibe-Trading metrics
        calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0
        
        downside = df_daily['return'][df_daily['return'] < 0] if (df_daily is not None and 'return' in df_daily.columns) else pd.Series()
        downside_std = float(downside.std()) if len(downside) > 1 else 1e-10
        downside_std_ann = downside_std * np.sqrt(252)
        sortino = float((ann_ret - 0.02) / downside_std_ann) if downside_std_ann > 1e-10 else 0.0
        
        round_trips = calculate_round_trip_trades(trades_list_clean, self.commission)
        wins = [t["pnl"] for t in round_trips if t["pnl"] > 0]
        losses = [t["pnl"] for t in round_trips if t["pnl"] < 0]
        
        win_rate_calc = len(wins) / len(round_trips) if round_trips else 0.0
        if round_trips:
            win_rate = win_rate_calc
            
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
        }
