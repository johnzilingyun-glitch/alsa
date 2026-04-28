import akshare as ak
import pandas as pd

def test_profit_sheet(symbol="002532"):
    try:
        print(f"Testing stock_profit_sheet_by_report_em for {symbol}...")
        df = ak.stock_profit_sheet_by_report_em(symbol=symbol)
        if df is not None and not df.empty:
            print("Columns:")
            print(df.columns.tolist())
            print("\nLatest 2 rows:")
            print(df.head(2).to_dict(orient="records"))
        else:
            print("Returned None or empty.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_profit_sheet("002532")
