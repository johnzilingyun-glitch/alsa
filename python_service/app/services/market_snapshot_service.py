from ..lake.parquet_store import ParquetMarketStore
from typing import List, Dict, Any
import asyncio
import akshare as ak
import pandas as pd
from ..utils.network import safe_ak_call

class MarketSnapshotService:
    def __init__(self, store: ParquetMarketStore):
        self.store = store

    async def create_snapshot(self, market: str, symbol: str) -> Dict[str, Any]:
        """
        Fetches market data and saves it to the Parquet lake.
        """
        # In a real setup, we'd have robust fetching. Reuse some akshare logic.
        try:
            # 1. Fetch daily history
            if market == "A-Share":
                try:
                    df = await safe_ak_call(ak.stock_zh_a_hist, symbol=symbol, period="daily", adjust="qfq")
                    if df is not None and not df.empty:
                        # Map columns to standard names
                        col_map = {
                            '日期': 'trade_date', '开盘': 'open', '收盘': 'close', 
                            '最高': 'high', '最低': 'low', '成交量': 'volume'
                        }
                        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
                    else:
                        print(f"AkShare history returned empty for {symbol}, trying yfinance fallback...")
                        raise ValueError("Empty AkShare data")
                except Exception as e:
                    print(f"AkShare history fetch failed for {symbol}: {e}. Attempting yfinance fallback...")
                    import yfinance as yf
                    yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                    ticker = yf.Ticker(yf_symbol)
                    df = ticker.history(period="6mo")
                    if not df.empty:
                        df = df.reset_index()
                        df = df.rename(columns={'Date': 'trade_date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
                        if 'trade_date' in df.columns:
                            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
                    else:
                        print(f"yfinance also returned empty for {yf_symbol}")
            else:
                # Use yfinance for US/HK
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="6mo")
                df = df.reset_index()
                df = df.rename(columns={'Date': 'trade_date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
                df['trade_date'] = df['trade_date'].dt.strftime('%Y-%m-%d')

            if df.empty:
                return {}
            
            rows = df.tail(120).to_dict(orient="records")
            
            # Save to Parquet
            self.store.write_ohlc("ohlc", market, symbol, rows)
            
            # Fetch valuation
            valuation = {}
            if market == "A-Share":
                try:
                    val_df = await safe_ak_call(ak.stock_individual_info_em, symbol=symbol)
                    valuation = dict(zip(val_df['item'], val_df['value']))
                except Exception as e:
                    print(f"Valuation fetch failed for {symbol}: {e}")
            
            # Fetch comprehensive financials (Market Cap, Net Profit, Dividends)
            from .market_data_service import market_data_service
            financials = await market_data_service.get_financial_summary(symbol, market)
            
            # Fetch real-time quotes
            quotes = await market_data_service.get_quotes([symbol])
            quote = quotes[0] if quotes else {}
            
            return {
                "name": quote.get("name", symbol),
                "price": quote.get("price"),
                "changePercent": quote.get("changePercent"),
                "currency": quote.get("currency"),
                "history": rows,
                "valuation": valuation,
                "financials": financials,
                "quote": quote
            }
        except Exception as e:
            print(f"Snapshot creation failed for {symbol}: {e}")
            return {}

# Singleton instance
from ..lake.parquet_store import ParquetMarketStore
parquet_store = ParquetMarketStore()
market_snapshot_service = MarketSnapshotService(parquet_store)
