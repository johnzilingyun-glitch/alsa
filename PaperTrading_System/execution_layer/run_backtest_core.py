# execution_layer/run_backtest_core.py

import os
import sys
import qlib
from qlib.backtest import backtest, executor
import pandas as pd

# Add parent to sys.path to resolve imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json

from execution_layer.market_configs import GLOBAL_BACKTEST_CONFIG
from decision_layer.mock_agent import MockStockAgent
from decision_layer.strategy_bridge import AIAgentStrategy

def run(start_date=None, end_date=None, model="MockAgent"):
    print("--- Initialize Qlib ---")
    provider_uri = os.path.expanduser("~/.qlib/qlib_data/cn_data")
    qlib.init(provider_uri=provider_uri, region="cn")

    print(f"\n--- Setup Strategy & Agent: {model} ---")
    # For now, always use MockAgent, later connect model
    agent = MockStockAgent(test_stock_list=["SH600000", "SZ000002", "SH600519", "SZ002594", "SH601318"])
    
    market = GLOBAL_BACKTEST_CONFIG["market_type"]
    trade_unit = GLOBAL_BACKTEST_CONFIG["exchange_kwargs"][market]["trade_unit"]
    
    strategy = AIAgentStrategy(
        agent_model=agent, 
        market_type=market, 
        trade_unit=trade_unit
    )

    print("\n--- Configure Backtest Environment ---")
    exchange_kwargs = GLOBAL_BACKTEST_CONFIG["exchange_kwargs"][market]
    
    trade_executor = executor.SimulatorExecutor(
        time_per_step="day",
        generate_portfolio_metrics=True
    )
    
    st_time = start_date or GLOBAL_BACKTEST_CONFIG["start_time"]
    ed_time = end_date or GLOBAL_BACKTEST_CONFIG["end_time"]

    print(f"\n--- Starting Backtest ({st_time} to {ed_time}) ---")
    portfolio_metric_dict, indicator_dict = backtest(
        executor=trade_executor,
        strategy=strategy,
        start_time=st_time,
        end_time=ed_time,
        account=GLOBAL_BACKTEST_CONFIG["init_account"],
        benchmark=GLOBAL_BACKTEST_CONFIG["benchmark"],
        exchange_kwargs={
            "freq": "day",
            "limit_threshold": exchange_kwargs["limit_threshold"],
            "deal_price": exchange_kwargs["deal_price"],
            "open_cost": exchange_kwargs["open_cost"],
            "close_cost": exchange_kwargs["close_cost"],
            "min_cost": exchange_kwargs["min_cost"],
        }
    )

    print("\n--- Backtest Completed ---")
    
    # Generate PortAnaRecord equivalent metrics manually to avoid mlflow dependency
    step_key = list(portfolio_metric_dict.keys())[0]
    report_normal_df, positions_normal = portfolio_metric_dict[step_key]
    
    print("\nAnalysis results of the excess return:")
    
    
    final_account = float(report_normal_df['account'].iloc[-1])
    
    output_data = {
        "start_date": st_time,
        "end_date": ed_time,
        "model": model,
        "final_account": final_account,
        "metrics": {}
    }
    
    try:
        from qlib.contrib.evaluate import risk_analysis
        returns = report_normal_df['return']
        risk_df = risk_analysis(returns)
        
        # Convert series to dict for json
        for k, v in risk_df.items():
            if isinstance(v, pd.Series):
                output_data["metrics"][k] = v.to_dict()
            else:
                output_data["metrics"][k] = float(v)
                
        print("\nPortfolio Risk Analysis:")
        print(risk_df.to_string())
    except Exception as e:
        print(f"\nFallback Metrics (Risk Analysis failed: {e}):")
        
    print("\nFinal Account Value:", final_account)
    
    with open(os.path.join(os.path.dirname(__file__), "results.json"), "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--model", type=str, default="MockAgent")
    args = parser.parse_args()
    
    run(start_date=args.start, end_date=args.end, model=args.model)
