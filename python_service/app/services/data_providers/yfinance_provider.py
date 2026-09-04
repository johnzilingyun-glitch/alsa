"""
YFinance Provider — Data source for US and HK stocks.

Uses yfinance as the primary provider for US/HK market data.
Provides history, quotes, and financial summaries.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

import pandas as pd
import yfinance as yf

from .base import DataProvider, QuoteData, normalize_ohlcv

logger = logging.getLogger(__name__)


def _normalize_yf_symbol(symbol: str) -> str:
    """Convert to yfinance-compatible ticker format."""
    s = symbol.strip().upper()

    # Strip frontend composite market suffixes: "KLAC.US-SHARE" → "KLAC",
    # "01888.HK-SHARE" → "01888.HK", "600519.A-SHARE" → "600519".
    if s.endswith(".HK-SHARE"):
        s = s[: -len(".HK-SHARE")] + ".HK"
    elif s.endswith(".A-SHARE"):
        s = s[: -len(".A-SHARE")]
    elif s.endswith(".US-SHARE"):
        s = s[: -len(".US-SHARE")]

    # Already in yfinance format
    if "." in s or s.startswith("^") or "=" in s:
        # Handle A-share if accidentally routed here
        if s.endswith((".SH", ".SS")):
            return s.replace(".SH", ".SS")  # yfinance uses .SS for Shanghai
        return s

    # Pure numeric → likely HK stock
    if s.isdigit():
        if len(s) <= 5:
            # Yahoo Finance uses exactly 4-digit codes for HK stocks (e.g., 0700.HK, 2888.HK).
            # Strip all leading zeros, then zero-pad back to 4.
            #  00700→0700  00001→0001  02888→2888  06951→6951
            clean_s = s.lstrip("0") or "0"
            return f"{clean_s.zfill(4)}.HK"
        elif len(s) == 6:
            # A-share (shouldn't normally reach here via router)
            return f"{s}.SS" if s.startswith("6") else f"{s}.SZ"

    # Alpha → US stock
    return s


class YFinanceProvider(DataProvider):
    """
    Yahoo Finance provider for US and HK stocks.
    """

    @property
    def name(self) -> str:
        return "yfinance"

    async def get_history(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """Fetch historical OHLCV from Yahoo Finance."""
        yf_symbol = _normalize_yf_symbol(symbol)
        loop = asyncio.get_event_loop()

        try:
            def _fetch():
                ticker = yf.Ticker(yf_symbol)
                return ticker.history(period=period, interval=interval)

            df = await loop.run_in_executor(None, _fetch)

            if df is None or df.empty:
                logger.warning(f"[{self.name}] No history for {yf_symbol}")
                return pd.DataFrame()

            # yfinance returns DatetimeIndex; reset to column
            df = df.reset_index()
            if "Date" in df.columns:
                df = df.rename(columns={"Date": "date"})
            elif "Datetime" in df.columns:
                df = df.rename(columns={"Datetime": "date"})

            # Rename yfinance columns
            col_map = {
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            }
            df = df.rename(columns=col_map)

            logger.info(f"[{self.name}] Fetched {len(df)} bars for {yf_symbol} (period={period})")
            return normalize_ohlcv(df)

        except Exception as e:
            logger.error(f"[{self.name}] get_history failed for {yf_symbol}: {e}")
            return pd.DataFrame()

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        """Fetch real-time quote from Yahoo Finance."""
        yf_symbol = _normalize_yf_symbol(symbol)
        loop = asyncio.get_event_loop()

        try:
            def _fetch():
                ticker = yf.Ticker(yf_symbol)
                return ticker.info

            info = await loop.run_in_executor(None, _fetch)
            if not info:
                return None

            price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            prev_close = info.get("regularMarketPreviousClose") or 0
            change = price - prev_close if price and prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            return QuoteData(
                symbol=symbol,
                name=info.get("shortName") or info.get("longName") or symbol,
                price=price,
                open=info.get("regularMarketOpen") or 0,
                high=info.get("regularMarketDayHigh") or 0,
                low=info.get("regularMarketDayLow") or 0,
                last_close=prev_close,
                change=round(change, 4),
                change_pct=round(change_pct, 2),
                volume=info.get("regularMarketVolume") or 0,
                amount=0,
                market_cap=info.get("marketCap"),
                pe_ttm=info.get("trailingPE"),
                pb=info.get("priceToBook"),
                source=self.name,
            )
        except Exception as e:
            logger.error(f"[{self.name}] get_quote failed for {yf_symbol}: {e}")
            return None

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        """Comprehensive financial summary from Yahoo Finance."""
        yf_symbol = _normalize_yf_symbol(symbol)
        loop = asyncio.get_event_loop()

        try:
            ticker = yf.Ticker(yf_symbol)
            info = await loop.run_in_executor(None, lambda: ticker.info)
            if not info:
                return {"error": "No data available", "source": self.name}

            # Fetch additional data
            financials = await loop.run_in_executor(None, lambda: ticker.financials)
            quarterly = await loop.run_in_executor(None, lambda: ticker.quarterly_financials)

            # Calculate CAGR
            revenue_cagr = None
            income_cagr = None
            if financials is not None and not financials.empty:
                if "Total Revenue" in financials.index:
                    rev_series = financials.loc["Total Revenue"].dropna()
                    revenue_cagr = self._calculate_cagr(rev_series)
                if "Net Income" in financials.index:
                    ni_series = financials.loc["Net Income"].dropna()
                    income_cagr = self._calculate_cagr(ni_series)

            # QoQ/YoY from quarterly
            revenue_qoq = revenue_yoy = net_profit_qoq = net_profit_yoy = None
            if quarterly is not None and not quarterly.empty:
                if "Total Revenue" in quarterly.index:
                    q_rev = quarterly.loc["Total Revenue"].dropna()
                    if len(q_rev) >= 2 and q_rev.iloc[1] != 0:
                        revenue_qoq = (q_rev.iloc[0] - q_rev.iloc[1]) / abs(q_rev.iloc[1])
                    if len(q_rev) >= 5 and q_rev.iloc[4] != 0:
                        revenue_yoy = (q_rev.iloc[0] - q_rev.iloc[4]) / abs(q_rev.iloc[4])
                if "Net Income" in quarterly.index:
                    q_ni = quarterly.loc["Net Income"].dropna()
                    if len(q_ni) >= 2 and q_ni.iloc[1] != 0:
                        net_profit_qoq = (q_ni.iloc[0] - q_ni.iloc[1]) / abs(q_ni.iloc[1])
                    if len(q_ni) >= 5 and q_ni.iloc[4] != 0:
                        net_profit_yoy = (q_ni.iloc[0] - q_ni.iloc[4]) / abs(q_ni.iloc[4])

            result = {
                "source": self.name,
                "symbol": symbol,
                "marketCap": info.get("marketCap"),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "pe": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "pb": info.get("priceToBook"),
                "pegRatio": info.get("pegRatio"),
                "priceToSales": info.get("priceToSalesTrailing12Months"),
                "enterpriseToEbitda": info.get("enterpriseToEbitda"),
                "enterpriseValue": info.get("enterpriseValue"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "grossMargin": info.get("grossMargins"),
                "operatingMargin": info.get("operatingMargins"),
                "profitMargin": info.get("profitMargins"),
                "revenue": info.get("totalRevenue"),
                "revenueGrowth": info.get("revenueGrowth"),
                "earningsGrowth": info.get("earningsGrowth"),
                "revenueYoY": revenue_yoy or info.get("revenueGrowth"),
                "netProfitYoY": net_profit_yoy or info.get("earningsGrowth"),
                "revenueQoQ": revenue_qoq,
                "netProfitQoQ": net_profit_qoq,
                "revenueCagr3y": revenue_cagr,
                "incomeCagr3y": income_cagr,
                "eps": info.get("trailingEps"),
                "totalCash": info.get("totalCash"),
                "totalDebt": info.get("totalDebt"),
                "freeCashflow": info.get("freeCashflow"),
                "operatingCashflow": info.get("operatingCashflow"),
                "debtToEquity": info.get("debtToEquity"),
                "currentRatio": info.get("currentRatio"),
                "quickRatio": info.get("quickRatio"),
                "dividendYield": info.get("dividendYield"),
                "payoutRatio": info.get("payoutRatio"),
                "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
                "currency": info.get("currency", "USD"),
                "financialCurrency": info.get("financialCurrency", "USD"),
                "longName": info.get("longName"),
                "industry": info.get("industry"),
                "sector": info.get("sector"),
                "exchange": info.get("exchange"),
                "country": info.get("country"),
            }
            logger.info(f"[{self.name}] Financial summary for {yf_symbol}: PE={result.get('pe')}")
            return result

        except Exception as e:
            logger.error(f"[{self.name}] get_financial_summary failed for {yf_symbol}: {e}")
            return {"error": str(e), "source": self.name}

    @staticmethod
    def _calculate_cagr(series: pd.Series) -> Optional[float]:
        """Calculate 3-year CAGR from a pandas Series (newest first)."""
        values = series.dropna()
        if len(values) < 3:
            return None
        newest = values.iloc[0]
        oldest = values.iloc[min(3, len(values) - 1)]
        if oldest <= 0 or newest <= 0:
            return None
        years = min(3, len(values) - 1)
        try:
            return (newest / oldest) ** (1 / years) - 1
        except (ZeroDivisionError, ValueError):
            return None
