import akshare as ak
import yfinance as yf

# Test fx_quote_baidu
try:
    df = ak.fx_quote_baidu()
    print('=== fx_quote_baidu ===')
    print(df.head(3))
    print()
except Exception as e:
    print(f'fx_quote_baidu failed: {e}')

# Test stock_sgt_reference_exchange_rate_sse 
try:
    df = ak.stock_sgt_reference_exchange_rate_sse()
    print('=== SSE Exchange Rate ===')
    print(df.head())
    print()
except Exception as e:
    print(f'SSE exchange rate failed: {e}')

# Test yfinance as alternative
t = yf.Ticker('USDCNY=X')
info = t.info
rate1 = info.get("regularMarketPrice")
print(f"yfinance USDCNY=X: {rate1}")

t2 = yf.Ticker('CNY=X')
info2 = t2.info
rate2 = info2.get("regularMarketPrice")
print(f"yfinance CNY=X: {rate2}")

# Test currency_boc_sina
try:
    df = ak.currency_boc_sina(symbol="美元")
    print("\n=== currency_boc_sina ===")
    print(df.head(3))
except Exception as e:
    print(f"currency_boc_sina failed: {e}")
