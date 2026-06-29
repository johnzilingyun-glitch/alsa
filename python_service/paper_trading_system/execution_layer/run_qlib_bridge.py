import argparse
import json
import sys
import pandas as pd
import numpy as np
from datetime import datetime

import qlib
from qlib.constant import REG_CN
from qlib.backtest import backtest, executor
from qlib.contrib.evaluate import risk_analysis

from paper_trading_system.decision_layer.qlib_custom_strategy import CustomRuleQlibStrategy
from paper_trading_system.execution_layer.market_configs import get_exchange_kwargs

# Monkey-patch: handle missing benchmark gracefully instead of raising ValueError
import qlib.backtest.report as _report_mod
_orig_cal_benchmark = _report_mod.PortfolioMetrics._cal_benchmark

def _safe_cal_benchmark(benchmark_config, freq):
    try:
        return _orig_cal_benchmark(benchmark_config, freq)
    except ValueError:
        return None

_report_mod.PortfolioMetrics._cal_benchmark = staticmethod(_safe_cal_benchmark)


def _check_qlib_data_availability(target_symbol, start_date, end_date):
    """Check if qlib data is available and covers the requested date range.
    
    Returns:
        tuple: (is_available: bool, message: str)
    """
    try:
        from qlib.data import LocalFeatureProvider
        from qlib.data.data import Cal
        
        provider = LocalFeatureProvider()
        cal = Cal.calendar(freq='day')
        
        # Check if we have feature data for this symbol
        try:
            storage = provider.backend_obj(instrument=target_symbol, field='close', freq='day')
        except Exception:
            return False, f"Qlib data not found for {target_symbol}. Please ensure the stock symbol is valid and qlib data is properly installed."
        
        if storage is None:
            return False, f"Qlib data not found for {target_symbol}."
        
        if not hasattr(storage, 'start_index') or not hasattr(storage, 'end_index'):
            return False, f"Qlib data format error for {target_symbol}."
        
        # Check if data is empty
        if storage.start_index is None or storage.end_index is None:
            return False, f"No data available for {target_symbol}."
        
        # Get the date range of available data
        if storage.start_index >= len(cal) or storage.end_index >= len(cal):
            return False, f"Qlib data index out of range for {target_symbol}."
        
        data_start = cal[storage.start_index]
        data_end = cal[storage.end_index]
        
        # Check if requested range is within available data
        req_start = pd.Timestamp(start_date)
        req_end = pd.Timestamp(end_date)
        
        if req_start < data_start:
            return False, f"Requested start date {start_date} is before available data ({data_start.date()}). Qlib data starts from {data_start.date()}."
        
        if req_end > data_end:
            return False, f"Requested end date {end_date} is after available data ({data_end.date()}). Qlib data ends at {data_end.date()}. Please use dates before {data_end.date()} or update qlib data."
        
        return True, f"Data available: {data_start.date()} to {data_end.date()}"
        
    except Exception as e:
        return False, f"Failed to check qlib data: {str(e)}"


def run_bridge():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start_date", type=str, required=True)
    parser.add_argument("--end_date", type=str, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--market", type=str, default="CN")
    parser.add_argument("--initial_cash", type=float, default=100000.0)
    parser.add_argument("--commission", type=float, default=0.0003)
    parser.add_argument("--target_symbol", type=str, default="")
    parser.add_argument("--params", type=str, default="{}")
    args = parser.parse_args()

    # Load params
    params = json.loads(args.params)
    
    # Check if qlib data is available for the target symbol
    target_symbol = args.target_symbol or params.get("target_symbol", "sh600519")
    target_symbol = str(target_symbol).lower()
    if not target_symbol.endswith(".hk") and not target_symbol.startswith(("sh", "sz")):
        if target_symbol.startswith("6"):
            target_symbol = f"sh{target_symbol}"
        elif target_symbol.startswith("0") or target_symbol.startswith("3"):
            target_symbol = f"sz{target_symbol}"

    # Init Qlib first
    provider_uri = "~/.qlib/qlib_data/cn_data"
    try:
        qlib.init(provider_uri=provider_uri, region=REG_CN)
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Qlib init failed: {e}"}))
        sys.exit(1)

    # Check if qlib data is available and covers the requested date range
    data_available, data_message = _check_qlib_data_availability(target_symbol, args.start_date, args.end_date)
    
    if not data_available:
        print(json.dumps({
            "status": "error",
            "message": f"Backtest failed: {data_message}",
            "error_code": "QLIB_DATA_UNAVAILABLE",
            "suggestion": "Please update qlib data or use a different date range within the available data period."
        }))
        sys.exit(1)
        
    # Clamp end_date to avoid SimulatorExecutor crash on the last day of the calendar
    try:
        from qlib.data import D
        cal = D.calendar(freq='day')
        if len(cal) > 1:
            max_end_date = pd.Timestamp(cal[-2]) # Second to last day to allow +1 lookahead
            req_end_date = pd.Timestamp(args.end_date)
            if req_end_date > max_end_date:
                args.end_date = max_end_date.strftime('%Y-%m-%d')
    except Exception:
        pass

    # Setup Strategy
    if args.model == "custom_rule":
        strategy = CustomRuleQlibStrategy(
            market=args.market,
            buy_rules=params.get("buy_rules", []),
            sell_rules=params.get("sell_rules", []),
            position_mode=params.get("position_mode", "fixed_shares"),
            position_value=float(params.get("position_value", 100)),
            stop_loss_pct=float(params.get("stop_loss_pct", 0)),
            take_profit_pct=float(params.get("take_profit_pct", 0)),
            trailing_stop_pct=float(params.get("trailing_stop_pct", 0)),
            target_symbol=target_symbol
        )
    else:
        # Fallback to MockAgent
        from paper_trading_system.decision_layer.agent_models import MockAgent
        from paper_trading_system.decision_layer.strategy_bridge import AIAgentStrategy
        agent = MockAgent(market_type=args.market)
        strategy = AIAgentStrategy(agent_model=agent, market_type=args.market)

    # Setup Executor
    exchange_kwargs = get_exchange_kwargs(args.market)
    trade_executor = executor.SimulatorExecutor(
        time_per_step="day",
        generate_portfolio_metrics=True,
        verbose=False,
        **exchange_kwargs
    )

    # Run Backtest — skip benchmark since qlib data may not have index data
    print("DEBUG: Starting backtest (no benchmark)...", file=sys.stderr)
    try:
        portfolio_metric_dict, indicator_dict = backtest(
            start_time=pd.Timestamp(args.start_date),
            end_time=pd.Timestamp(args.end_date),
            strategy=strategy,
            executor=trade_executor,
            account=args.initial_cash,
            benchmark=None
        )
        print("DEBUG: Backtest finished.", file=sys.stderr)
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(json.dumps({"status": "error", "message": f"Qlib backtest error: {str(e)}", "traceback": err_msg}))
        sys.exit(1)

    # Extract Results
    metrics_df = portfolio_metric_dict["1day"][0]
    
    final_equity = metrics_df["account"].iloc[-1]
    initial_equity = metrics_df["account"].iloc[0]
    
    # ── Compute metrics manually from equity curve instead of relying on
    #    Qlib's risk_analysis(), which returns wildly wrong values when
    #    benchmark=None (e.g. annualized_return = 193 billion %).
    total_return = (final_equity - initial_equity) / initial_equity if initial_equity > 0 else 0.0
    trading_days = len(metrics_df)
    n_years = trading_days / 252.0

    # Annualized return
    if n_years > 0 and (1 + total_return) > 0:
        ann_ret = float((1 + total_return) ** (1.0 / n_years) - 1)
    else:
        ann_ret = 0.0

    # Max drawdown from equity curve
    equity_series = metrics_df["account"]
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    # Sharpe ratio from daily returns
    daily_returns = equity_series.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        rf_daily = 0.03 / 252  # 3% annual risk-free rate
        sharpe = float((daily_returns.mean() - rf_daily) / daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0.0


    # Build snapshots
    snapshots = []
    # Fetch close prices for the target symbol from Qlib data
    close_prices = {}
    high_prices = {}
    low_prices = {}
    try:
        from qlib.data import D
        price_df = D.features([target_symbol], ["$close", "$high", "$low"], start_time=args.start_date, end_time=args.end_date)
        if price_df is not None and not price_df.empty:
            try:
                sym_df = price_df.xs(target_symbol, level="instrument")
            except KeyError:
                sym_df = price_df
            for dt_idx in sym_df.index:
                d_key = dt_idx.strftime("%Y-%m-%d")
                c = sym_df.loc[dt_idx, "$close"]
                h = sym_df.loc[dt_idx, "$high"]
                lo = sym_df.loc[dt_idx, "$low"]
                if not np.isnan(c):
                    close_prices[d_key] = float(c)
                if not np.isnan(h):
                    high_prices[d_key] = float(h)
                if not np.isnan(lo):
                    low_prices[d_key] = float(lo)
    except Exception:
        pass

    for dt, row in metrics_df.iterrows():
        d_str = dt.strftime("%Y-%m-%d")
        snapshots.append({
            "date": d_str,
            "total_equity": float(row["account"]),
            "benchmark_equity": args.initial_cash,
            "cash": float(row.get("cash", 0)),
            "close_price": close_prices.get(d_str, 0),
            "high_price": high_prices.get(d_str, close_prices.get(d_str, 0)),
            "low_price": low_prices.get(d_str, close_prices.get(d_str, 0)),
        })

    trade_list = []
    try:
        indicator_obj = indicator_dict["1day"][1]
        for step_time, step_oi in indicator_obj.order_indicator_his.items():
            deal_amount = step_oi.get_index_data("deal_amount")
            trade_price = step_oi.get_index_data("trade_price")
            trade_dir = step_oi.get_index_data("trade_dir")
            if deal_amount is None or deal_amount.empty:
                continue

            # Convert SingleData/IndexData to pandas Series safely
            if hasattr(deal_amount, 'index') and deal_amount.index is not None:
                if hasattr(deal_amount.index, 'tolist'):
                    index_data = deal_amount.index.tolist()
                elif hasattr(deal_amount.index, 'idx_list'):
                    index_data = deal_amount.index.idx_list
                else:
                    index_data = list(deal_amount.index)
                da_series = pd.Series(deal_amount.data, index=index_data)
                tp_series = pd.Series(trade_price.data, index=index_data) if trade_price is not None else pd.Series()
                td_series = pd.Series(trade_dir.data, index=index_data) if trade_dir is not None else pd.Series()
            else:
                da_series = deal_amount.to_series() if hasattr(deal_amount, 'to_series') else deal_amount
                tp_series = trade_price.to_series() if hasattr(trade_price, 'to_series') else trade_price
                td_series = trade_dir.to_series() if hasattr(trade_dir, 'to_series') else trade_dir

            for stock_id, da in da_series.items():
                if np.isnan(da) or da == 0:
                    continue
                tp = tp_series.get(stock_id, 0) if hasattr(tp_series, 'get') else 0
                td = td_series.get(stock_id, 0) if hasattr(td_series, 'get') else 0
                if np.isnan(tp) or tp <= 0:
                    continue
                trade_list.append({
                    "date": step_time.strftime("%Y-%m-%d") if hasattr(step_time, "strftime") else str(step_time)[:10],
                    "symbol": str(stock_id).upper(),
                    "action": "BUY" if td >= 1 else "SELL",
                    "shares": int(abs(da)),
                    "price": float(tp),
                })
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(f"Warning: Failed to extract trades from indicator: {e}", file=sys.stderr)

    # Compute win_rate from extracted trades
    sell_trades = [t for t in trade_list if t["action"] == "SELL"]
    win_count = 0
    total_pnl = 0.0
    if sell_trades:
        positions = {}  # symbol -> {"shares": 0, "avg_cost": 0.0}
        for t in trade_list:
            sym = t["symbol"]
            if t["action"] == "BUY":
                if sym not in positions:
                    positions[sym] = {"shares": 0, "avg_cost": 0.0}
                curr_shares = positions[sym]["shares"]
                curr_cost = positions[sym]["avg_cost"]
                new_shares = t["shares"]
                new_cost = t["price"]
                total_cost = (curr_shares * curr_cost) + (new_shares * new_cost)
                positions[sym]["shares"] += new_shares
                positions[sym]["avg_cost"] = total_cost / positions[sym]["shares"] if positions[sym]["shares"] > 0 else 0.0
            elif t["action"] == "SELL" and sym in positions and positions[sym]["shares"] > 0:
                avg_cost = positions[sym]["avg_cost"]
                # In Qlib simple execution we might not strictly track partial shares, use t["shares"]
                sell_shares = t["shares"]
                pnl = (t["price"] - avg_cost) * sell_shares
                total_pnl += pnl
                if pnl > 0:
                    win_count += 1
                positions[sym]["shares"] -= sell_shares
    win_rate = (win_count / len(sell_trades)) if sell_trades else 0.0
    total_return = (float(final_equity) - args.initial_cash) / args.initial_cash if args.initial_cash > 0 else 0.0
    
    # Compute real Alpha, Beta, Sortino, Calmar, Profit Factor from equity curve
    strategy_returns = metrics_df["account"].pct_change().dropna()
    beta = 0.0
    alpha = 0.0
    sortino = 0.0
    calmar = 0.0
    profit_factor = 0.0
    max_consecutive_loss = 0
    avg_holding_days = 0
    try:
        # Fetch benchmark returns
        bench_returns = None
        try:
            from qlib.data import D
            bench_df = D.features([target_symbol], ["$close"], start_time=args.start_date, end_time=args.end_date)
            if bench_df is not None and not bench_df.empty:
                try:
                    bench_sym = bench_df.xs(target_symbol, level="instrument")
                except KeyError:
                    bench_sym = bench_df
                bench_close = bench_sym["$close"].dropna()
                bench_returns = bench_close.pct_change().dropna()
                # Align dates
                common_idx = strategy_returns.index.intersection(bench_returns.index)
                if len(common_idx) > 10:
                    sr = strategy_returns.loc[common_idx].values
                    br = bench_returns.loc[common_idx].values
                    cov_mat = np.cov(sr, br)
                    beta = float(cov_mat[0, 1] / cov_mat[1, 1]) if cov_mat[1, 1] != 0 else 1.0
                    rf_daily = 0.03 / 252
                    alpha = float((sr.mean() - rf_daily - beta * (br.mean() - rf_daily)) * 252)
        except Exception:
            pass

        # Sortino ratio (downside deviation)
        rf_daily = 0.03 / 252
        excess = strategy_returns.values - rf_daily
        downside = excess[excess < 0]
        downside_std = float(np.std(downside)) if len(downside) > 0 else 1e-8
        sortino = float(excess.mean() / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

        # Calmar ratio
        calmar = float(ann_ret / abs(max_dd)) if max_dd != 0 else 0.0

        # Profit factor
        sell_trades_pnl = []
        buy_prices = {}
        for t in trade_list:
            if t["action"] == "BUY":
                buy_prices[t["symbol"]] = t["price"]
            elif t["action"] == "SELL" and t["symbol"] in buy_prices:
                pnl = (t["price"] - buy_prices[t["symbol"]]) * t["shares"]
                sell_trades_pnl.append(pnl)
        gross_profit = sum(p for p in sell_trades_pnl if p > 0)
        gross_loss = abs(sum(p for p in sell_trades_pnl if p < 0))
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0

        # Max consecutive losses
        consec = 0
        max_consec = 0
        for pnl in sell_trades_pnl:
            if pnl < 0:
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0
        max_consecutive_loss = max_consec

        # Average holding days
        if sell_trades:
            buy_dates = {}
            holding_days_list = []
            for t in trade_list:
                if t["action"] == "BUY":
                    buy_dates[t["symbol"]] = t["date"]
                elif t["action"] == "SELL" and t["symbol"] in buy_dates:
                    try:
                        bd = datetime.strptime(buy_dates[t["symbol"]], "%Y-%m-%d")
                        sd = datetime.strptime(t["date"], "%Y-%m-%d")
                        holding_days_list.append((sd - bd).days)
                    except Exception:
                        pass
            avg_holding_days = float(np.mean(holding_days_list)) if holding_days_list else 0.0
    except Exception:
        pass

    result = {
        "status": "success",
        "data": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "model": args.model,
            "market": args.market,
            "final_account": float(final_equity),
            "snapshots": snapshots,
            "trades": trade_list,
            "metrics": {
                "annualized_return": {"risk": float(ann_ret)},
                "max_drawdown": {"risk": float(max_dd)},
                "sharpe_ratio": float(sharpe),
                "win_rate": float(win_rate),
                "total_trades": len(trade_list),
                "total_pnl": float(total_pnl),
                "total_return": float(total_return),
                "mean": {"risk": float(ann_ret)},
                "std": {"risk": float(strategy_returns.std() * np.sqrt(252)) if len(strategy_returns) > 0 else 0.0},
                "alpha": float(alpha),
                "beta": float(beta),
                "treynor_ratio": float((ann_ret - 0.03) / beta) if beta != 0 else 0.0,
                "information_ratio": float(sharpe),
                "calmar_ratio": float(calmar),
                "sortino_ratio": float(sortino),
                "profit_factor": float(profit_factor),
                "profit_loss_ratio": float(gross_profit / gross_loss) if gross_loss > 0 else 0.0,
                "max_consecutive_loss": int(max_consecutive_loss),
                "avg_holding_days": float(avg_holding_days),
            }
        }
    }
    
    print(json.dumps(result))

if __name__ == "__main__":
    run_bridge()
