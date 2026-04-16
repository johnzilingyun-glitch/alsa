import akshare as ak
try:
    df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
    print("Success")
    print(df.head())
except Exception as e:
    print(f"Error: {e}")
