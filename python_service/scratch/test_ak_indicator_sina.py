import akshare as ak
import pandas as pd

def test_indicator_sina(symbol="sh600519"):
    try:
        print(f"Testing stock_financial_analysis_indicator for {symbol}...")
        df = ak.stock_financial_analysis_indicator(symbol=symbol)
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
    test_indicator_sina("sh600519")
    test_indicator_sina("sz002532")
