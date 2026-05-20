from ..lake.parquet_store import ParquetMarketStore
from typing import List, Dict, Any
import asyncio
import os
import pandas as pd

# Only import akshare if enabled (geo-blocked from non-China servers)
AKSHARE_ENABLED = os.getenv("AKSHARE_ENABLED", "false").lower() == "true"
if AKSHARE_ENABLED:
    import akshare as ak
    from ..utils.network import safe_ak_call

class MarketSnapshotService:
    def __init__(self, store: ParquetMarketStore):
        self.store = store

    async def create_snapshot(self, market: str, symbol: str) -> Dict[str, Any]:
        """
        Fetches market data and saves it to the Parquet lake.
        Parallelizes independent data fetches for speed.
        """
        import time
        t0 = time.time()
        print(f"Creating snapshot for {market} stock: {symbol}")
        try:
            from .market_data_service import market_data_service

            # --- Define all independent fetch tasks ---

            async def _fetch_history():
                df = pd.DataFrame()
                if market == "A-Share":
                    if AKSHARE_ENABLED:
                        try:
                            df = await safe_ak_call(ak.stock_zh_a_hist, symbol=symbol, period="daily", adjust="qfq")
                            if df is not None and not df.empty:
                                col_map = {
                                    '日期': 'trade_date', '开盘': 'open', '收盘': 'close', 
                                    '最高': 'high', '最低': 'low', '成交量': 'volume'
                                }
                                df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
                            else:
                                df = pd.DataFrame()
                        except Exception as e:
                            print(f"AkShare history fetch failed for {symbol}: {e}. Attempting yfinance fallback...")
                            df = pd.DataFrame()

                    if df.empty:
                        import yfinance as yf
                        yf_symbol = f"{symbol}.SS" if symbol.startswith('6') else f"{symbol}.SZ"
                        ticker = yf.Ticker(yf_symbol)
                        df = await asyncio.to_thread(ticker.history, period="6mo")
                        if not df.empty:
                            df = df.reset_index()
                            df = df.rename(columns={'Date': 'trade_date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
                else:
                    import yfinance as yf
                    yf_symbol = symbol
                    if market == "HK-Share":
                        clean_symbol = symbol.replace(".HK", "").zfill(4)
                        yf_symbol = f"{clean_symbol}.HK"
                    ticker = yf.Ticker(yf_symbol)
                    df = await asyncio.to_thread(ticker.history, period="6mo")
                    if not df.empty:
                        df = df.reset_index()
                        df = df.rename(columns={'Date': 'trade_date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})

                if not df.empty and 'trade_date' in df.columns:
                    trade_dates = pd.to_datetime(df['trade_date'], errors='coerce')
                    df['trade_date'] = trade_dates.dt.strftime('%Y-%m-%d')
                    df = df.dropna(subset=['trade_date'])
                return df

            async def _fetch_valuation():
                if market != "A-Share" or not AKSHARE_ENABLED:
                    return {}
                try:
                    val_df = await safe_ak_call(ak.stock_individual_info_em, symbol=symbol)
                    if val_df is not None and not val_df.empty:
                        return dict(zip(val_df['item'], val_df['value']))
                except Exception as e:
                    print(f"Valuation fetch failed for {symbol}: {e}")
                return {}

            async def _fetch_financials():
                return await market_data_service.get_financial_summary(symbol, market)

            async def _fetch_quotes():
                quotes = await market_data_service.get_quotes([symbol])
                return quotes[0] if quotes else {}

            # --- Run all fetches in parallel ---
            history_result, valuation, financials, quote = await asyncio.gather(
                _fetch_history(),
                _fetch_valuation(),
                _fetch_financials(),
                _fetch_quotes(),
            )

            df = history_result
            if df is None or df.empty:
                print(f"Snapshot: no history data for {symbol}")
                return {}

            rows = df.tail(120).to_dict(orient="records")
            self.store.write_ohlc("ohlc", market, symbol, rows)

            # A+H cross-listing check (depends on quote name, so runs after)
            cross_listing = None
            if market == "A-Share":
                cross_listing = await self._get_ah_cross_listing(quote.get("name", ""), symbol)

            elapsed = time.time() - t0
            print(f"Snapshot created for {symbol} in {elapsed:.1f}s")

            return {
                "name": quote.get("name", symbol),
                "price": quote.get("price"),
                "changePercent": quote.get("changePercent"),
                "currency": quote.get("currency"),
                "history": rows,
                "valuation": valuation,
                "financials": financials,
                "quote": quote,
                "crossListing": cross_listing,
            }
        except Exception as e:
            print(f"Snapshot creation failed for {symbol}: {e}")
            return {}

    async def _get_ah_cross_listing(self, stock_name: str, symbol: str) -> dict | None:
        """Check if an A-share stock has a corresponding H-share listing."""
        if not AKSHARE_ENABLED:
            return None
        try:
            df = await safe_ak_call(ak.stock_zh_ah_name)
            if df is None or df.empty:
                return None
            # Match by name (strip "股份" suffix for fuzzy match)
            clean_name = stock_name.replace("股份", "").strip()
            match = df[df['名称'].str.contains(clean_name, na=False)]
            if match.empty and len(clean_name) >= 2:
                # Try shorter prefix match (first 2 chars)
                match = df[df['名称'].str.startswith(clean_name[:2], na=False)]
                # Filter further if multiple matches
                if len(match) > 1:
                    match = match[match['名称'].str.contains(clean_name[:3], na=False)] if len(clean_name) >= 3 else match.head(1)
            if not match.empty:
                hk_code = match.iloc[0]['代码']
                hk_name = match.iloc[0]['名称']
                return {
                    "market": "HK",
                    "symbol": f"{hk_code}.HK",
                    "name": hk_name,
                    "type": "A+H"
                }
            return None
        except Exception as e:
            print(f"A+H cross-listing check failed for {symbol}: {e}")
            return None

# Singleton instance
from ..lake.parquet_store import ParquetMarketStore
parquet_store = ParquetMarketStore()
market_snapshot_service = MarketSnapshotService(parquet_store)
