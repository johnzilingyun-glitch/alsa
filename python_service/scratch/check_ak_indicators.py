import akshare as ak
import pandas as pd

def check_indicators(symbol="002532"):
    try:
        # Try different endpoints
        print("Testing stock_main_financial_indicator_em...")
        df = ak.stock_main_financial_indicator_em(symbol=symbol)
        if df is not None and not df.empty:
            print("Columns in stock_main_financial_indicator_em:")
            print(df.columns.tolist())
            print("\nLatest row data:")
            print(df.iloc[0].to_dict())
            return

        print("\nTesting stock_financial_analysis_indicator_em...")
        df = ak.stock_financial_analysis_indicator_em(symbol=symbol)
        if df is not None and not df.empty:
            print("Columns in stock_financial_analysis_indicator_em:")
            print(df.columns.tolist())
            print("\nLatest row data:")
            print(df.iloc[0].to_dict())
            return
            
        print("\nAll attempts returned None or empty.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_indicators()
