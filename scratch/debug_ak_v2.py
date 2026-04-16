import akshare as ak
try:
    df = ak.stock_hsgt_fund_flow_summary_em()
    print("Northbound Success")
    print(df.head())
except Exception as e:
    print(f"Northbound Error: {e}")

try:
    df = ak.stock_zh_a_spot_em()
    print("Spot Success")
    print(df.head())
except Exception as e:
    print(f"Spot Error: {e}")
