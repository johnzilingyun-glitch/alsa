import asyncio
import akshare as ak
import pandas as pd
import json
import sys
import os

# Add parent dir to path to import utils
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.utils.network import safe_ak_call

async def test_fundamentals():
    symbols = ["600519", "000858", "300750"] # 茅台, 五粮液, 宁德时代
    for symbol in symbols:
        print(f"\n--- Testing {symbol} with safe_ak_call ---")
        try:
            # Info
            info_df = await safe_ak_call(ak.stock_individual_info_em, symbol=symbol)
            info = dict(zip(info_df['item'], info_df['value']))
            print(f"Name: {info.get('股票简称')}, Price: {info.get('最新价')}")
            
            # Financials
            indicator_df = await safe_ak_call(ak.stock_financial_analysis_indicator_em, symbol=symbol)
            if not indicator_df.empty:
                latest = indicator_df.head(1).to_dict(orient="records")[0]
                print(f"Net Profit: {latest.get('净利润')}, ROE: {latest.get('净资产收益率')}")
            
            # Dividend
            try:
                dividend_df = await safe_ak_call(ak.stock_history_dividend_detail, symbol=symbol)
                if not dividend_df.empty:
                    print(f"Latest Dividend: {dividend_df.iloc[0].to_dict().get('派息')}")
            except Exception as e:
                print(f"Dividend error: {e}")
                
        except Exception as e:
            print(f"Final error for {symbol} after retries: {e}")

if __name__ == "__main__":
    asyncio.run(test_fundamentals())
