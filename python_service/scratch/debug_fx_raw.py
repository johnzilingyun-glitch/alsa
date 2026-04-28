import akshare as ak
import pandas as pd

try:
    print("Testing ak.fx_spot_quote() raw data...")
    df = ak.fx_spot_quote()
    if df is not None:
        print(f"Columns (raw): {df.columns.tolist()}")
        print("First 10 rows (raw):")
        for i in range(min(10, len(df))):
            print(f"Row {i}: {df.iloc[i].values.tolist()}")
            
        # Try finding USD/CNY by checking if it contains 'USD' or 'CNY' or similar
        for i in range(len(df)):
            row_str = str(df.iloc[i].values.tolist())
            if 'USD' in row_str or 'CNY' in row_str or '美元' in row_str:
                print(f"Candidate row found: {df.iloc[i].values.tolist()}")
except Exception as e:
    print(f"Error: {e}")
