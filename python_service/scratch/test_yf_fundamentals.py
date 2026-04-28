import yfinance as yf
import json

def check_stock(symbol):
    print(f"Checking {symbol} via yfinance...")
    ticker = yf.Ticker(symbol)
    info = ticker.info
    # Keep only a few relevant fields to avoid huge output
    keys = ["marketCap", "trailingPE", "forwardPE", "priceToBook", "totalRevenue", "revenueGrowth", "netIncomeToCommon", "earningsGrowth", "returnOnEquity", "debtToEquity"]
    filtered_info = {k: info.get(k) for k in keys}
    print(json.dumps(filtered_info, indent=2))

if __name__ == "__main__":
    check_stock("CHA")
    check_stock("AAPL")
