import akshare as ak
import pandas as pd

def test_indicator(symbol="600519"):
    try:
        print(f"Testing stock_financial_analysis_indicator_em for {symbol}...")
        df = ak.stock_financial_analysis_indicator_em(symbol=symbol)
        if df is not None and not df.empty:
            print("Columns:")
            print(df.columns.tolist())
            print("\nLatest data:")
            print(df.iloc[0].to_dict())
        else:
            print("Returned None or empty.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_indicator("600519")
    test_indicator("002532")
