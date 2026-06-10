import sys
import os
import json

sys.path.append("/home/ubuntu/work/alsa")

from python_service.app.services.backtest_engine_service import BacktestEngine
from python_service.app.api.backtest import BacktestRequest, run_native_backtest, RESULTS_FILE

def run_model_test(model_name, capital, params):
    req = BacktestRequest(
        start_date="2020-01-01",
        end_date="2021-12-31",
        model=model_name,
        market="CN",
        config={
            "initial_capital": capital,
            "commission": 0.0003,
            "strategy_params": params
        }
    )
    print(f"\n==========================================")
    print(f"Running {model_name} backtest...")
    print(f"==========================================")
    
    # Clean previous result
    if os.path.exists(RESULTS_FILE):
        os.remove(RESULTS_FILE)
        
    run_native_backtest(req)
    
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        res = json.load(f)
        
    if res.get("status") == "error":
        print("Failed! Error:", res.get("message"))
    else:
        print("Success!")
        print("Final Account:", res.get("final_account"))
        print("Number of Trades:", len(res.get("trades", [])))
        print("Metrics:")
        print(json.dumps(res.get("metrics"), indent=2, ensure_ascii=False))

def main():
    # Test MockAgent
    run_model_test(
        model_name="MockAgent",
        capital=1000000.0,
        params={"fast_window": 5, "slow_window": 20}
      )
      
    # Test Portfolio
    run_model_test(
        model_name="portfolio_cross_sectional",
        capital=1000000.0,
        params={"rebalance_interval": 63}
    )

if __name__ == "__main__":
    main()
