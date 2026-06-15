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

from .base import DataProvider, QuoteData, MarketType, detect_market, normalize_ohlcv
from .a_stock_direct import AStockDirectProvider
from .akshare_fallback import AkShareFallbackProvider
from .yfinance_provider import YFinanceProvider

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
                return [self._a_stock_primary, self._a_stock_fallback]
            return [self._a_stock_primary]
        elif market == MarketType.HK_SHARE:
            return [self._a_stock_primary, self._yfinance]
        elif market == MarketType.US_SHARE:
            return [self._yfinance]
        else:
            # Unknown market — try yfinance first, then A-share
            return [self._yfinance, self._a_stock_primary]

    async def get_history(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data with automatic routing and fallback.

        Args:
            symbol: Stock ticker (e.g., "600519", "AAPL", "0700.HK")
            period: Data period ("1mo", "3mo", "6mo", "1y", "2y", "5y", "max")
            interval: Bar interval ("1d", "1wk", "1mo", "5m", "15m", "30m", "60m")

        Returns:
            Normalized DataFrame with columns: date, open, high, low, close, volume
        """
        providers = self._get_providers(symbol)
        market = detect_market(symbol)

        for i, provider in enumerate(providers):
            is_fallback = i > 0
            label = "Fallback" if is_fallback else "Primary"
            try:
                logger.info(
                    f"[Router] Routing {symbol} ({market.value}) to {provider.name} ({label})"
                )
                df = await provider.get_history(symbol, period=period, interval=interval)
                if df is not None and not df.empty:
                    return df
                else:
                    logger.warning(
                        f"[Router] {provider.name} returned empty for {symbol}"
                    )
            except Exception as e:
                logger.warning(
                    f"[Router] {label} ({provider.name}) failed for {symbol}: {e}"
                )
                if is_fallback or i == len(providers) - 1:
                    logger.error(f"[Router] All providers exhausted for {symbol}")

        return pd.DataFrame()

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        """
        Fetch real-time quote with automatic routing and fallback.

        Args:
            symbol: Stock ticker

        Returns:
            QuoteData object or None if all providers fail
        """
        providers = self._get_providers(symbol)
        market = detect_market(symbol)

        for i, provider in enumerate(providers):
            is_fallback = i > 0
            label = "Fallback" if is_fallback else "Primary"
            try:
                logger.info(
                    f"[Router] Quote {symbol} ({market.value}) → {provider.name} ({label})"
                )
                quote = await provider.get_quote(symbol)
                if quote and quote.price > 0:
                    return quote
                else:
                    logger.warning(f"[Router] {provider.name} returned no quote for {symbol}")
            except Exception as e:
                logger.warning(
                    f"[Router] {label} ({provider.name}) quote failed for {symbol}: {e}"
                )

        return None

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch comprehensive financial metrics with routing and fallback.

        Args:
            symbol: Stock ticker

        Returns:
            Dict with financial metrics (PE, PB, ROE, growth, etc.)
        """
        providers = self._get_providers(symbol)
        market = detect_market(symbol)

        for i, provider in enumerate(providers):
            is_fallback = i > 0
            label = "Fallback" if is_fallback else "Primary"
            try:
                logger.info(
                    f"[Router] Financial summary {symbol} ({market.value}) → {provider.name} ({label})"
                )
                result = await provider.get_financial_summary(symbol)
                if result and "error" not in result:
                    result["_routed_via"] = provider.name
                    result["_market"] = market.value
                    return result
                elif is_fallback:
                    # Return even error result from last provider
                    return result
                else:
                    logger.warning(
                        f"[Router] {provider.name} returned error for {symbol}, trying fallback"
                    )
            except Exception as e:
                logger.warning(
                    f"[Router] {label} ({provider.name}) financial_summary failed for {symbol}: {e}"
                )

        return {"error": "All providers failed", "symbol": symbol}

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
