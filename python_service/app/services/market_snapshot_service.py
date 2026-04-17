from ..lake.parquet_store import ParquetMarketStore
from typing import List, Dict, Any
import akshare as ak
import pandas as pd

class MarketSnapshotService:
    def __init__(self, store: ParquetMarketStore):
        self.store = store

    async def create_snapshot(self, market: str, symbol: str) -> Dict[str, Any]:
        """
        Fetches market data and saves it to the Parquet lake.
        """
        # In a real setup, we'd have robust fetching. Reuse some akshare logic.
        try:
            # Fetch daily history (A-Share example)
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
            if df.empty:
                return {}
            
            # Map columns to standard names
            col_map = {
                '日期': 'trade_date', '开盘': 'open', '收盘': 'close', 
                '最高': 'high', '最低': 'low', '成交量': 'volume'
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            
            rows = df.tail(120).to_dict(orient="records")
            
            # Save to Parquet
            self.store.write_ohlc("ohlc", market, symbol, rows)
            
            # Fetch valuation
            val_df = ak.stock_individual_info_em(symbol=symbol)
            valuation = dict(zip(val_df['item'], val_df['value']))
            
            return {
                "history": rows,
                "valuation": valuation
            }
        except Exception as e:
            print(f"Snapshot creation failed for {symbol}: {e}")
            return {}
