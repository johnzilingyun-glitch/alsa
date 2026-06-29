import asyncio
import logging
import pandas as pd
from typing import Optional, Dict, Any

from .base import DataProvider, QuoteData, normalize_ohlcv
from .ths_provider import ths_provider

logger = logging.getLogger(__name__)

class THSDataProvider(DataProvider):
    @property
    def name(self) -> str:
        return "thsdk"

    async def get_history(self, symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
        try:
            # Map interval
            ths_interval = "1d" if interval in ("1d", "1wk", "1mo") else interval
            # Map period to count
            count = 100
            if period == "1mo": count = 22
            elif period == "3mo": count = 66
            elif period == "6mo": count = 130
            elif period == "1y": count = 250
            
            res = await ths_provider.get_klines(ths_code=symbol, interval=ths_interval, count=count, adjust="qfq")
            if res and "data" in res and res["data"]:
                df = pd.DataFrame(res["data"])
                return normalize_ohlcv(df)
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"[THSDataProvider] K-line failed for {symbol}: {e}")
            return pd.DataFrame()

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        return None

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        return {"error": "Not implemented", "source": self.name}


class SinaDataProvider(DataProvider):
    @property
    def name(self) -> str:
        return "sina"

    async def get_history(self, symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
        import akshare as ak
        loop = asyncio.get_event_loop()
        try:
            clean_sym = ''.join(filter(str.isdigit, symbol))
            if not clean_sym:
                return pd.DataFrame()
            prefix = "sh" if clean_sym.startswith(("6", "9")) else "sz"
            sina_sym = f"{prefix}{clean_sym}"
            
            def fetch():
                if interval == "1d":
                    return ak.stock_zh_a_daily(symbol=sina_sym, adjust="qfq")
                else:
                    period_map = {"5m": "5", "15m": "15", "30m": "30", "60m": "60"}
                    return ak.stock_zh_a_minute(symbol=sina_sym, period=period_map.get(interval, "5"), adjust="qfq")

            df = await loop.run_in_executor(None, fetch)
            if df is not None and not df.empty:
                return normalize_ohlcv(df)
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"[SinaDataProvider] K-line failed for {symbol}: {e}")
            return pd.DataFrame()

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        return None

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        return {"error": "Not implemented", "source": self.name}


class IwencaiDataProvider(DataProvider):
    @property
    def name(self) -> str:
        return "iwencai"

    async def get_history(self, symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
        try:
            # Fallback wrapper for iwencai logic via ths_provider.wencai_nlp
            query = f"{symbol}近3个月K线"
            res = await ths_provider.wencai_nlp(query)
            if res and "data" in res and res["data"]:
                df = pd.DataFrame(res["data"])
                return normalize_ohlcv(df)
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"[IwencaiDataProvider] K-line failed for {symbol}: {e}")
            return pd.DataFrame()

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        return None

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        return {"error": "Not implemented", "source": self.name}
