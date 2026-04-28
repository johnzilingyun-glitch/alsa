import akshare as ak
import pandas as pd
import asyncio

async def test():
    symbol = "300274"
    print(f"Testing {symbol} financials...")
    try:
        df = ak.stock_financial_analysis_indicator_em(symbol=symbol)
        print("Columns in stock_financial_analysis_indicator_em:")
        print(df.columns.tolist())
        print("\nLatest record:")
        print(df.iloc[0].to_dict())
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
