import sys
import os
import sqlite3
import pandas as pd

sys.path.append("/home/ubuntu/work/alsa")

from python_service.app.services.portfolio_real_backtest import PortfolioBacktester

def main():
    pb = PortfolioBacktester()
    print("Loading fundamentals...")
    pe_df, mc_df = pb.load_fundamentals()
    print("Fundamentals index range:", pe_df.index.min(), "to", pe_df.index.max())
    print("Fundamentals shape:", pe_df.shape)
    
    print("\nValuation table samples (first 5 rows):")
    conn = sqlite3.connect(pb.db_path)
    print(pd.read_sql_query("SELECT * FROM valuation LIMIT 5", conn))
    conn.close()

    print("\nRunning 1-year backtest for portfolio...")
    res = pb.run_backtest(start_date="2020-01-01", end_date="2021-12-31", rebalance_interval=63)
    print("\nBacktest result status: Success!")
    print("Final account:", res.get("final_account"))
    print("Number of trades:", len(res.get("trades")))
    print("Metrics:", res.get("metrics"))

if __name__ == "__main__":
    main()
