"""
AkShare Fallback Provider — Secondary A-Share data source.

Used as fallback when the primary direct HTTP provider fails.
Wraps existing akshare calls with the unified DataProvider interface.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

import pandas as pd

from .base import DataProvider, QuoteData, normalize_ohlcv

logger = logging.getLogger(__name__)


def _clean_symbol(symbol: str) -> str:
    """Normalize to pure 6-digit code."""
    s = symbol.strip().upper()
    for suffix in (".SH", ".SS", ".SZ", ".BJ"):
        s = s.replace(suffix, "")
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix) and len(s) > 2:
            s = s[2:]
    return s[:6]


class AkShareFallbackProvider(DataProvider):
    """
    Fallback A-Share provider using akshare.
    Only activated when AStockDirectProvider fails.
    """

    @property
    def name(self) -> str:
        return "akshare-fallback"

    async def get_history(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """Fetch history via akshare stock_zh_a_hist."""
        import akshare as ak
        from ...utils.network import safe_ak_call

        code = _clean_symbol(symbol)

        # Map period to date range
        from datetime import datetime, timedelta
        period_days = {
            "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "max": 7300,
        }
        days = period_days.get(period, 90)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        # Map interval
        interval_map = {"1d": "daily", "1wk": "weekly", "1mo": "monthly"}
        ak_period = interval_map.get(interval, "daily")

        try:
            df = await safe_ak_call(
                ak.stock_zh_a_hist,
                symbol=code,
                period=ak_period,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            if df is not None and not df.empty:
                logger.info(f"[{self.name}] Fetched {len(df)} bars for {code}")
                return normalize_ohlcv(df)
        except Exception as e:
            logger.error(f"[{self.name}] get_history failed for {code}: {e}")

        return pd.DataFrame()

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        """Fetch quote via akshare stock_zh_a_spot_em."""
        import akshare as ak
        from ...utils.network import safe_ak_call

        code = _clean_symbol(symbol)
        try:
            df = await safe_ak_call(ak.stock_zh_a_spot_em)
            if df is not None and not df.empty:
                row = df[df["代码"] == code]
                if not row.empty:
                    r = row.iloc[0]
                    return QuoteData(
                        symbol=code,
                        name=r.get("名称", ""),
                        price=float(r.get("最新价", 0) or 0),
                        open=float(r.get("今开", 0) or 0),
                        high=float(r.get("最高", 0) or 0),
                        low=float(r.get("最低", 0) or 0),
                        last_close=float(r.get("昨收", 0) or 0),
                        change=float(r.get("涨跌额", 0) or 0),
                        change_pct=float(r.get("涨跌幅", 0) or 0),
                        volume=float(r.get("成交量", 0) or 0),
                        amount=float(r.get("成交额", 0) or 0),
                        market_cap=float(r.get("总市值", 0) or 0) / 1e8 if r.get("总市值") else None,
                        pe_ttm=float(r.get("市盈率-动态", 0) or 0) or None,
                        pb=float(r.get("市净率", 0) or 0) or None,
                        turnover_pct=float(r.get("换手率", 0) or 0) or None,
                        source=self.name,
                    )
        except Exception as e:
            logger.error(f"[{self.name}] get_quote failed for {code}: {e}")
        return None

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        """Fetch financial summary via akshare financial indicators."""
        import akshare as ak
        from ...utils.network import safe_ak_call
        from ...utils.data_validation import validate_ak_data

        code = _clean_symbol(symbol)
        result: Dict[str, Any] = {"source": self.name, "symbol": code}

        # Financial indicators
        try:
            df = await safe_ak_call(ak.stock_financial_analysis_indicator_em, symbol=code)
            if validate_ak_data(df, min_rows=1):
                latest = df.iloc[0]
                result.update({
                    "netProfit": latest.get("净利润"),
                    "netProfitDeduct": latest.get("扣除非经常性损益后的净利润"),
                    "netProfitYoY": latest.get("净利润同比增长率"),
                    "revenue": latest.get("营业收入"),
                    "roe": latest.get("净资产收益率"),
                    "grossMargin": latest.get("销售毛利率"),
                    "debtRatio": latest.get("资产负债率"),
                })
        except Exception as e:
            logger.warning(f"[{self.name}] Financial indicators failed for {code}: {e}")

        # Stock info
        try:
            info_df = await safe_ak_call(ak.stock_individual_info_em, symbol=code)
            if validate_ak_data(info_df, min_rows=1):
                info_dict = dict(zip(info_df['item'], info_df['value']))
                result.update({
                    "marketCap": info_dict.get("总市值"),
                    "pe": info_dict.get("市盈率-动态"),
                    "pb": info_dict.get("市净率"),
                    "industry": info_dict.get("行业"),
                    "longName": info_dict.get("股票简称"),
                })
        except Exception as e:
            logger.warning(f"[{self.name}] Stock info failed for {code}: {e}")

        result["currency"] = "CNY"
        result["financialCurrency"] = "CNY"
        return result
