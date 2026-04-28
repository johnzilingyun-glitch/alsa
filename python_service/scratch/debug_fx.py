import akshare as ak
import pandas as pd

try:
    print("Testing ak.fx_spot_quote()...")
    df = ak.fx_spot_quote()
    if df is not None:
        print("Success! Columns:", df.columns.tolist())
        usd_cny = df[df['币种'] == '美元人民币']
        if not usd_cny.empty:
            print("USD/CNY Data:")
            print(usd_cny.iloc[0].to_dict())
        else:
            print("USD/CNY not found in list. Available currency pairs:")
            print(df['币种'].unique())
    else:
        print("DF is None")
except Exception as e:
    print(f"Error: {e}")

try:
    print("\nTesting fallback ak.currency_boc_sinosure()...")
    df = ak.currency_boc_sinosure()
    if df is not None:
        print("Success! Columns:", df.columns.tolist())
        usd = df[df['英文名称'] == 'USD']
        if not usd.empty:
            print("USD Data:")
            print(usd.iloc[0].to_dict())
except Exception as e:
    print(f"Error: {e}")
