import akshare as ak
import pandas as pd

try:
    print("Testing ak.forex_spot_em()...")
    df = ak.forex_spot_em()
    if df is not None:
        print("Success! Columns:", df.columns.tolist())
        # Try to find USD/CNY
        # Typical columns for EM are: '代码', '名称', '最新价', '涨跌额', '涨跌幅', ...
        usd_cny = df[df['名称'].str.contains('美元人民币') | df['名称'].str.contains('美元/人民币')]
        if not usd_cny.empty:
            print("USD/CNY Data:")
            print(usd_cny.iloc[0].to_dict())
        else:
            print("USD/CNY not found. Available names:")
            print(df['名称'].head(20).tolist())
    else:
        print("DF is None")
except Exception as e:
    print(f"Error: {e}")

try:
    print("\nTesting ak.fx_spot_quote() again with manual column fix...")
    df = ak.fx_spot_quote()
    if df is not None:
        # Inspect columns without printing them directly if possible
        cols = df.columns.tolist()
        print(f"Found {len(cols)} columns.")
        # Sometimes the columns are: '币种', '最新价', ...
        # Let's try to identify by index if names are garbled
        # Usually 0 is currency, 1 is price
        for idx, row in df.iterrows():
            try:
                name = str(row.iloc[0])
                if '美元人民币' in name:
                    print(f"Match found at row {idx}!")
                    print(f"Currency: {name}, Price: {row.iloc[1]}")
            except:
                continue
except Exception as e:
    print(f"Error in manual check: {e}")
