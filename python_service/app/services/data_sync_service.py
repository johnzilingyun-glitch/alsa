import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

try:
    from vnpy.trader.database import get_database, BaseDatabase
    from vnpy.trader.object import BarData
    from vnpy.trader.constant import Exchange, Interval
except ImportError:
    class BaseDatabase: pass
    def get_database(): return None
    class BarData: pass
    class Exchange: 
        SSE = "SSE"
        SZSE = "SZSE"
        HKFE = "HKFE"
        SEHK = "SEHK"
        SMART = "SMART"
        value = "unknown"
    class Interval: 
        DAILY = "d"

logger = logging.getLogger(__name__)

class DataSyncService:
    def __init__(self):
        self.database: BaseDatabase = get_database()
        
    def _normalize_yf_symbol(self, symbol: str, exchange: Exchange) -> str:
        if exchange == Exchange.SSE:
            return f"{symbol}.SS"
        elif exchange == Exchange.SZSE:
            return f"{symbol}.SZ"
        elif exchange == Exchange.HKFE or exchange == Exchange.SEHK:
            return f"{symbol.zfill(4)}.HK"
        return symbol # SMART / US default

    async def ensure_local_data(
        self, 
        symbol: str, 
        exchange: Exchange, 
        start_date: datetime, 
        end_date: datetime
    ) -> bool:
        """
        Ensure the local database has the requested daily bar data.
        Downloads from yfinance if missing.
        """
        vt_symbol = f"{symbol}.{exchange.value}"
        
        # 1. Check local database
        overviews = self.database.get_bar_overview()
        overview = next(
            (o for o in overviews if o.symbol == symbol and o.exchange == exchange and o.interval == Interval.DAILY),
            None
        )
        
        needs_download = False
        
        if not overview:
            logger.info(f"[{vt_symbol}] No local data found. Starting full sync.")
            needs_download = True
        else:
            # Check if requested range is within local range
            db_start = overview.start.replace(tzinfo=timezone.utc)
            db_end = overview.end.replace(tzinfo=timezone.utc)
            
            # Allow some margin (e.g., weekend shifts)
            if start_date < db_start or end_date > db_end:
                logger.info(f"[{vt_symbol}] Local data range ({db_start.date()} to {db_end.date()}) does not cover requested range ({start_date.date()} to {end_date.date()}). Starting sync.")
                needs_download = True
            else:
                logger.info(f"[{vt_symbol}] Local data covers requested range. Using cached data.")

        # 2. Download and save if needed
        if needs_download:
            try:
                # We download a slightly wider range to be safe
                fetch_start = min(start_date, overview.start.replace(tzinfo=timezone.utc)) if overview else start_date
                fetch_end = max(end_date, overview.end.replace(tzinfo=timezone.utc)) if overview else end_date
                
                # yfinance end date is exclusive
                fetch_end_str = (fetch_end + timedelta(days=1)).strftime("%Y-%m-%d")
                fetch_start_str = fetch_start.strftime("%Y-%m-%d")
                
                yf_symbol = self._normalize_yf_symbol(symbol, exchange)
                
                logger.info(f"[{vt_symbol}] Downloading from yfinance ({fetch_start_str} to {fetch_end_str})...")
                
                loop = asyncio.get_event_loop()
                df = await loop.run_in_executor(None, lambda: yf.download(yf_symbol, start=fetch_start_str, end=fetch_end_str, progress=False))
                
                if df.empty:
                    logger.warning(f"[{vt_symbol}] Downloaded data is empty.")
                    return False
                    
                # yfinance > 0.2.x returns MultiIndex by default for single symbols
                if isinstance(df.columns, pd.MultiIndex):
                    # We just flatten it by picking the first level of the ticker (or just ignore the ticker level)
                    # Because df[('Close', 'AAPL')] works. 
                    # If it's single ticker, df['Close'] actually works in newer yfinance, but let's be robust
                    pass
                else:
                    # Older yfinance, convert to single ticker multiindex manually
                    df.columns = pd.MultiIndex.from_product([df.columns, [yf_symbol]])

                bars = []
                utc_tz = timezone.utc
                
                for dt, row in df.iterrows():
                    dt_native = dt.to_pydatetime()
                    
                    if isinstance(df.columns, pd.MultiIndex):
                        close_raw = row.get(('Close', yf_symbol))
                        if pd.isna(close_raw) or close_raw <= 0:
                            continue
                            
                        adj_close = row.get(('Adj Close', yf_symbol), close_raw)
                        if pd.isna(adj_close):
                            adj_close = close_raw
                            
                        adj_factor = float(adj_close / close_raw)
                        
                        open_price = float(row.get(('Open', yf_symbol), close_raw) * adj_factor)
                        high_price = float(row.get(('High', yf_symbol), close_raw) * adj_factor)
                        low_price = float(row.get(('Low', yf_symbol), close_raw) * adj_factor)
                        volume = row.get(('Volume', yf_symbol), 0)
                    else:
                        close_raw = row.get('Close')
                        if pd.isna(close_raw) or close_raw <= 0:
                            continue
                            
                        adj_close = row.get('Adj Close', close_raw)
                        if pd.isna(adj_close):
                            adj_close = close_raw
                            
                        adj_factor = float(adj_close / close_raw)
                        
                        open_price = float(row.get('Open', close_raw) * adj_factor)
                        high_price = float(row.get('High', close_raw) * adj_factor)
                        low_price = float(row.get('Low', close_raw) * adj_factor)
                        volume = row.get('Volume', 0)
                        
                    bar = BarData(
                        symbol=symbol,
                        exchange=exchange,
                        datetime=dt_native.replace(tzinfo=utc_tz),
                        interval=Interval.DAILY,
                        volume=float(volume),
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        close_price=float(adj_close),
                        gateway_name="YF"
                    )
                    bars.append(bar)
                    
                if bars:
                    self.database.save_bar_data(bars)
                    logger.info(f"[{vt_symbol}] Successfully saved {len(bars)} bars to local database.")
                    return True
                else:
                    logger.warning(f"[{vt_symbol}] No valid bars parsed.")
                    return False

            except Exception as e:
                logger.error(f"[{vt_symbol}] Failed to sync data: {e}")
                return False
                
        return True

data_sync_service = DataSyncService()
