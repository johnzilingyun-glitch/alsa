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
        # Not implemented — Sina direct HTTP not implemented
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
