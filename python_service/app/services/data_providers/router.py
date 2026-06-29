"""
DataRouter — Market-aware data source router with fallback.

Implements the Strategy Pattern: detects market from ticker and
routes to the optimal data provider. Falls back gracefully on failure.

Routing rules:
  A-Shares (6-digit/.SH/.SZ) → AStockDirectProvider (primary, Tencent+Sina)
  HK (.HK / 4-5 digit)       → YFinanceProvider
  US (alpha / ^prefix)        → YFinanceProvider

NOTE: AkShare fallback disabled — relies on EastMoney which is blocked
from non-China IPs. AStockDirect now has Tencent kline fallback built-in.
"""

import logging
import os
from typing import Dict, Any, Optional, List

import pandas as pd

from .base import DataProvider, QuoteData, MarketType, detect_market
from .a_stock_direct import AStockDirectProvider
from .akshare_fallback import AkShareFallbackProvider
from .yfinance_provider import YFinanceProvider
from .extra_providers import THSDataProvider, SinaDataProvider, IwencaiDataProvider

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import text
from app.db.database import engine

logger = logging.getLogger(__name__)


class DataRouter:
    """
    Intelligent data router that selects the optimal provider based on market.
    Provides a unified interface hiding all underlying API complexity.
    """

    def __init__(self):
        # Provider instances (lazy-init friendly, stateless)
        self._a_stock_primary = AStockDirectProvider()
        self._a_stock_fallback = AkShareFallbackProvider()
        self._yfinance = YFinanceProvider()
        self._ths = THSDataProvider()
        self._sina = SinaDataProvider()
        self._iwencai = IwencaiDataProvider()
        # AkShare fallback disabled by default from overseas (EastMoney geo-blocked)
        self._akshare_enabled = os.environ.get("AKSHARE_ENABLED", "false").lower() in ("true", "1", "yes")

    def _get_providers(self, symbol: str) -> List[DataProvider]:
        """
        Return ordered list of providers for a symbol.
        First = primary, rest = fallbacks.
        """
        market = detect_market(symbol)

        if market == MarketType.A_SHARE:
            if self._akshare_enabled:
                return [self._a_stock_primary, self._a_stock_fallback, self._yfinance, self._ths, self._sina, self._iwencai]
            return [self._a_stock_primary, self._yfinance, self._ths, self._sina, self._iwencai]
        elif market == MarketType.HK_SHARE:
            return [self._a_stock_primary, self._yfinance]
        elif market == MarketType.US_SHARE:
            return [self._yfinance]
        else:
            # Unknown market — try yfinance first, then A-share
            return [self._yfinance, self._a_stock_primary]

    CONCURRENT_TIMEOUT = 30

    async def _fetch_concurrently(self, symbol: str, fetch_func, default_val, validation_func):
        import asyncio
        providers = self._get_providers(symbol)
        
        async def wrap(p):
            try:
                res = await fetch_func(p)
                if validation_func(res):
                    return p.name, res
            except Exception as e:
                logger.warning(f"[Router] {p.name} failed for {symbol}: {e}")
            return p.name, None

        tasks = [asyncio.create_task(wrap(p)) for p in providers]
        
        try:
            result = await asyncio.wait_for(
                self._first_success(tasks),
                timeout=self.CONCURRENT_TIMEOUT
            )
            if result is not None:
                logger.info(f"[Router] Concurrent fetch successful for {symbol}")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[Router] Concurrent fetch timed out ({self.CONCURRENT_TIMEOUT}s) for {symbol}")
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
                    
        logger.error(f"[Router] All concurrent providers failed for {symbol}")
        return default_val

    async def _first_success(self, tasks):
        for fut in asyncio.as_completed(tasks):
            name, res = await fut
            if res is not None:
                return res
        return None

    async def get_history(
        self, symbol: str, period: str = "10y", interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data with concurrent execution and fallback.
        Includes a SQLite-based cache layer for 1d interval to speed up queries.
        """
        # --- Cache Check Layer ---
        if interval == "1d":
            # Run blocking DB operations in a thread
            def _check_db():
                try:
                    # Check the maximum date in the database for this symbol
                    query = f"SELECT MAX(date) as max_date, COUNT(*) as cnt FROM daily_klines WHERE symbol = '{symbol}'"
                    df_meta = pd.read_sql(query, engine)
                    if not df_meta.empty and df_meta['cnt'].iloc[0] > 0:
                        max_date_str = df_meta['max_date'].iloc[0]
                        if max_date_str:
                            max_date = pd.to_datetime(max_date_str).tz_localize(None)
                            # Define cache expiration: 1 business day
                            # If it's the weekend, Friday's data is still fresh until Monday evening.
                            # A simple heuristic: if max_date is within 48 hours, consider it fresh.
                            # (Adjusted slightly to handle weekends/holidays gracefully, up to 3-4 days)
                            age = datetime.now() - max_date
                            if age.days <= 4:
                                logger.info(f"[Router Cache] HIT for {symbol}: max_date {max_date_str} (age {age.days} days)")
                                # Load the cached dataframe
                                df_cache = pd.read_sql(f"SELECT date, open, high, low, close, volume FROM daily_klines WHERE symbol = '{symbol}' ORDER BY date ASC", engine)
                                # Convert dates back to string format 'YYYY-MM-DD' if they were stored as strings
                                df_cache['date'] = pd.to_datetime(df_cache['date']).dt.strftime('%Y-%m-%d')
                                return df_cache
                except Exception as e:
                    logger.warning(f"[Router Cache] DB read failed: {e}")
                return None
            
            cached_df = await asyncio.to_thread(_check_db)
            if cached_df is not None and not cached_df.empty:
                return cached_df
            
            # If cache miss, always fetch a large period ('10y' or 'max') so our cache is comprehensive
            # Even if the user requested "3mo", we fetch more to populate the cache.
            period_to_fetch = "10y"
        else:
            period_to_fetch = period

        # --- API Concurrent Fetch Layer ---
        def validate_kline(df):
            if df is None or df.empty: return False
            if 'close' not in df.columns or 'date' not in df.columns: return False
            return True

        df = await self._fetch_concurrently(
            symbol,
            lambda p: p.get_history(symbol, period=period_to_fetch, interval=interval),
            pd.DataFrame(),
            validate_kline
        )
        
        # --- Cache Write Layer ---
        if interval == "1d" and not df.empty:
            def _write_db(data_df):
                try:
                    # Clean existing records for this symbol
                    with engine.begin() as conn:
                        conn.execute(text(f"DELETE FROM daily_klines WHERE symbol = '{symbol}'"))
                    
                    # Prepare dataframe for insert
                    insert_df = data_df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
                    insert_df['symbol'] = symbol
                    # Write to database (pandas to_sql handles the bulk insert)
                    insert_df.to_sql("daily_klines", con=engine, if_exists="append", index=False)
                    logger.info(f"[Router Cache] WRITTEN for {symbol}: {len(insert_df)} rows cached.")
                except Exception as e:
                    logger.warning(f"[Router Cache] DB write failed: {e}")
            
            # Run write in background thread so it doesn't block returning the result
            asyncio.create_task(asyncio.to_thread(_write_db, df))
            
        # If user originally asked for a smaller period, just return the fetched (we don't strictly slice yet, downstream handles it)
        # But we could slice if we want. Downstream usually handles it.
        return df

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        """
        Fetch real-time quote concurrently.
        """
        async def fetch(p):
            return await p.get_quote(symbol)
            
        def is_valid(q):
            return q is not None and q.price > 0
            
        return await self._fetch_concurrently(symbol, fetch, None, is_valid)

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch comprehensive financial metrics concurrently.
        """
        market = detect_market(symbol)
        
        async def fetch(p):
            res = await p.get_financial_summary(symbol)
            if res and "error" not in res:
                res["_routed_via"] = p.name
                res["_market"] = market.value
                return res
            return None
            
        def is_valid(r):
            return r is not None
            
        default_err = {"error": "All providers failed", "symbol": symbol}
        result = await self._fetch_concurrently(symbol, fetch, default_err, is_valid)

        # A-share ownership backfill: the concurrent race may be won by a provider
        # (e.g. yfinance) that lacks A-share holder data, leaving ownership N/A.
        # Enrich from EastMoney F10 regardless of which provider produced financials.
        if (
            isinstance(result, dict)
            and market == MarketType.A_SHARE
            and (result.get("heldPercentInsiders") is None or result.get("heldPercentInstitutions") is None)
        ):
            try:
                from .a_stock_direct import fetch_a_share_ownership
                code = "".join(ch for ch in symbol if ch.isdigit())[:6]
                if code:
                    ownership = await fetch_a_share_ownership(code)
                    for key, val in ownership.items():
                        if result.get(key) is None:
                            result[key] = val
            except Exception as e:
                logger.warning(f"[Router] A-share ownership enrichment failed for {symbol}: {e}")

        return result

    async def get_quotes_batch(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Batch fetch quotes for multiple symbols.
        Routes each symbol independently.
        """
        import asyncio
        tasks = [self.get_quote(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for sym, result in zip(symbols, results):
            if isinstance(result, Exception):
                output.append({"symbol": sym, "error": str(result)})
            elif result is None:
                output.append({"symbol": sym, "error": "No data"})
            else:
                output.append(result.to_dict())
        return output


# Singleton instance
data_router = DataRouter()
