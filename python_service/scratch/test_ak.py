import akshare as ak
import pandas as pd

def test():
    symbol = "300274"
    print(f"Testing {symbol}...")
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
        print("stock_zh_a_hist success:")
        print(df.tail(2))
    except Exception as e:
        print(f"stock_zh_a_hist failed: {e}")

    try:
        df = ak.stock_individual_info_em(symbol=symbol)
        print("stock_individual_info_em success:")
        print(df)
    except Exception as e:
        print(f"stock_individual_info_em failed: {e}")

if __name__ == "__main__":
    test()
