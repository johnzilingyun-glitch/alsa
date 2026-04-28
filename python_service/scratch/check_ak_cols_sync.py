import akshare as ak
import pandas as pd

def test():
    symbol = "300274"
    print(f"Testing {symbol} financials (sync)...")
    try:
        df = ak.stock_financial_analysis_indicator_em(symbol=symbol)
        if df is None:
            print("Result is None")
            return
        print("Columns in stock_financial_analysis_indicator_em:")
        print(df.columns.tolist())
        print("\nLatest record:")
        print(df.iloc[0].to_dict())
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test()
