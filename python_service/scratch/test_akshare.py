import akshare as ak

try:
    df = ak.stock_zh_a_hist(symbol="002156", period="daily", adjust="qfq")
    print(df.head())
except Exception as e:
    print(f"Error: {e}")
