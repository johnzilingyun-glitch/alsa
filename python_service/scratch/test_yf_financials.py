import yfinance as yf

ticker = yf.Ticker("002156.SZ")
info = ticker.info
print("INFO:")
print({k: v for k, v in info.items() if k in ["netIncomeToCommon", "totalRevenue", "revenueGrowth", "earningsGrowth", "capitalExpenditure"]})

try:
    print("FINANCIALS:")
    print(ticker.financials)
    print("QUARTERLY FINANCIALS:")
    print(ticker.quarterly_financials)
except Exception as e:
    print(f"Error: {e}")
