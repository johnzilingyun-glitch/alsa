import akshare as ak
import pandas as pd

def test_spot():
    try:
        print("Testing stock_zh_a_spot_em...")
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            print("Columns:")
            print(df.columns.tolist())
            match = df[df['代码'] == '002532']
            if not match.empty:
                print("\nData for 002532:")
                print(match.iloc[0].to_dict())
            else:
                print("\n002532 not found in spot data.")
        else:
            print("Returned None or empty.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_spot()
