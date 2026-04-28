import akshare as ak
import pandas as pd

def test_spot_single(symbol="002532"):
    try:
        print(f"Testing stock_zh_a_spot_em for {symbol}...")
        # Get all, then filter
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            match = df[df['代码'] == symbol]
            if not match.empty:
                row = match.iloc[0].to_dict()
                print("All columns available in spot data:")
                for k, v in row.items():
                    print(f" - {k}: {v}")
            else:
                print(f"Symbol {symbol} not found.")
        else:
            print("Returned None or empty.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_spot_single("002532")
