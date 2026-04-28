import akshare as ak
import pandas as pd
import numpy as np

try:
    print("Searching for USD or CNY/USD...")
    df = ak.fx_spot_quote()
    if df is not None:
        for i in range(len(df)):
            row = df.iloc[i].values.tolist()
            row_str = str(row)
            if 'USD' in row_str:
                print(f"USD found: {row}")
            if 'CNY' in row_str:
                # print(f"CNY found: {row}")
                pass
except Exception as e:
    print(f"Error: {e}")
