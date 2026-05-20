"""
A-Share Direct Provider — Primary data source for China A-Shares.

Directly connects to HTTP APIs (Tencent, EastMoney, Baidu, Sina)
without intermediate wrappers like akshare. Based on the architecture
from github.com/simonlin1212/a-stock-data (V3.0).

Data sources:
  - Tencent Finance: PE/PB/market cap/turnover/real-time quotes
  - EastMoney datacenter: financial indicators, dividends, fundamentals
  - EastMoney push2: K-line history, industry info
  - Sina Finance: financial statements (balance sheet/income/cashflow)
"""

import asyncio
import logging
import urllib.request
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

import requests
import pandas as pd

from .base import DataProvider, QuoteData, normalize_ohlcv

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _get_prefix(code: str) -> str:
    """6-digit code → market prefix (sh/sz/bj)."""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    else:
        return "sz"


def _clean_symbol(symbol: str) -> str:
    """Normalize various symbol formats to pure 6-digit code."""
    s = symbol.strip().upper()
    for suffix in (".SH", ".SS", ".SZ", ".BJ"):
        s = s.replace(suffix, "")
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix) and len(s) > 2:
            s = s[2:]
    return s[:6]


def _eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> List[Dict]:
    """EastMoney datacenter unified query helper."""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    try:
        r = requests.get(
            DATACENTER_URL, params=params,
            headers={"User-Agent": UA}, timeout=15
        )
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception as e:
        logger.warning(f"EastMoney datacenter error ({report_name}): {e}")
    return []


class AStockDirectProvider(DataProvider):
    """
    Primary A-Share data provider using direct HTTP APIs.
    No akshare dependency — connects directly to Tencent, EastMoney, Sina.
    """

    @property
    def name(self) -> str:
        return "a-stock-direct"

    async def get_history(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Fetch K-line history. Tries EastMoney push2his first,
        falls back to Tencent ifeng/web API on failure.
        """
        code = _clean_symbol(symbol)
        market_code = 1 if code.startswith(("6", "9")) else 0

        # Map period string to number of bars
        period_bars = {
            "1mo": 22, "3mo": 66, "6mo": 132,
            "1y": 252, "2y": 504, "5y": 1260, "max": 5000,
        }
        limit = period_bars.get(period, 66)

        # Map interval to klt parameter
        interval_map = {
            "1d": "101", "1wk": "102", "1mo": "103",
            "5m": "5", "15m": "15", "30m": "30", "60m": "60",
        }
        klt = interval_map.get(interval, "101")

        # Try EastMoney first
        df = await self._fetch_eastmoney_kline(code, market_code, klt, limit, period)
        if not df.empty:
            return df

        # Fallback: Tencent web K-line API
        df = await self._fetch_tencent_kline(code, period, interval)
        if not df.empty:
            return df

        logger.warning(f"[{self.name}] All kline sources failed for {code}")
        return pd.DataFrame()

    async def _fetch_eastmoney_kline(
        self, code: str, market_code: int, klt: str, limit: int, period: str
    ) -> pd.DataFrame:
        """Fetch K-line from EastMoney push2his (blocked from non-China IPs)."""
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": f"{market_code}.{code}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": klt,
            "fqt": "1",
            "end": "20500101",
            "lmt": str(limit),
        }

        loop = asyncio.get_event_loop()
        try:
            def _fetch():
                r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=8)
                return r.json()

            d = await loop.run_in_executor(None, _fetch)
            klines = d.get("data", {}).get("klines", [])
            if not klines:
                return pd.DataFrame()

            rows = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 7:
                    rows.append({
                        "date": parts[0],
                        "open": float(parts[1]),
                        "close": float(parts[2]),
                        "high": float(parts[3]),
                        "low": float(parts[4]),
                        "volume": float(parts[5]),
                        "amount": float(parts[6]),
                    })

            df = pd.DataFrame(rows)
            logger.info(f"[{self.name}] EastMoney kline: {len(df)} bars for {code} (period={period})")
            return normalize_ohlcv(df)

        except Exception as e:
            logger.debug(f"[{self.name}] EastMoney kline unavailable for {code}: {type(e).__name__}")
            return pd.DataFrame()

    async def _fetch_tencent_kline(
        self, code: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """Fetch K-line from Tencent web.ifzq API (accessible from overseas)."""
        prefix = _get_prefix(code)
        qt_symbol = f"{prefix}{code}"

        # Map period to day count for Tencent API
        period_days = {
            "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "max": 3650,
        }
        days = period_days.get(period, 90)

        # Tencent kline type: day/week/month
        kline_type = "day"
        if interval == "1wk":
            kline_type = "week"
        elif interval == "1mo":
            kline_type = "month"

        from datetime import datetime, timedelta
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "_var": "kline_dayqfq",
            "param": f"{qt_symbol},{kline_type},{start_date},{end_date},640,qfq",
        }

        loop = asyncio.get_event_loop()
        try:
            def _fetch():
                r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=10)
                text = r.text
                # Response is JS variable assignment: kline_dayqfq={...}
                json_str = text.split("=", 1)[1] if "=" in text else text
                return json.loads(json_str)

            d = await loop.run_in_executor(None, _fetch)
            stock_data = d.get("data", {}).get(qt_symbol, {})

            # Try qfq (前复权) key first, then day/week/month
            klines = stock_data.get(f"qfq{kline_type}", stock_data.get(kline_type, []))
            if not klines:
                return pd.DataFrame()

            rows = []
            for k in klines:
                if len(k) >= 6:
                    rows.append({
                        "date": k[0],
                        "open": float(k[1]),
                        "close": float(k[2]),
                        "high": float(k[3]),
                        "low": float(k[4]),
                        "volume": float(k[5]),
                    })

            df = pd.DataFrame(rows)
            logger.info(f"[{self.name}] Tencent kline: {len(df)} bars for {code} (period={period})")
            return normalize_ohlcv(df)

        except Exception as e:
            logger.warning(f"[{self.name}] Tencent kline failed for {code}: {type(e).__name__}: {e}")
            return pd.DataFrame()

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        """
        Real-time quote from Tencent Finance API.
        Returns PE/PB/market cap/turnover along with price data.
        """
        code = _clean_symbol(symbol)
        prefix = _get_prefix(code)
        qt_symbol = f"{prefix}{code}"

        loop = asyncio.get_event_loop()
        try:
            def _fetch():
                url = f"https://qt.gtimg.cn/q={qt_symbol}"
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "Mozilla/5.0")
                resp = urllib.request.urlopen(req, timeout=10)
                return resp.read().decode("gbk")

            data = await loop.run_in_executor(None, _fetch)
            vals = data.split('"')[1].split("~")
            if len(vals) < 53:
                return None

            quote = QuoteData(
                symbol=code,
                name=vals[1],
                price=float(vals[3]) if vals[3] else 0,
                open=float(vals[5]) if vals[5] else 0,
                high=float(vals[33]) if vals[33] else 0,
                low=float(vals[34]) if vals[34] else 0,
                last_close=float(vals[4]) if vals[4] else 0,
                change=float(vals[31]) if vals[31] else 0,
                change_pct=float(vals[32]) if vals[32] else 0,
                volume=float(vals[36]) if vals[36] else 0,
                amount=float(vals[37]) * 10000 if vals[37] else 0,  # 万→元
                market_cap=float(vals[44]) if vals[44] else None,  # 亿
                pe_ttm=float(vals[39]) if vals[39] else None,
                pb=float(vals[46]) if vals[46] else None,
                turnover_pct=float(vals[38]) if vals[38] else None,
                source=self.name,
            )
            logger.info(f"[{self.name}] Quote for {code}: {quote.price} PE={quote.pe_ttm}")
            return quote

        except Exception as e:
            logger.error(f"[{self.name}] get_quote failed for {code}: {e}")
            return None

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Comprehensive financial summary from multiple direct APIs:
          - Tencent: PE/PB/market cap
          - EastMoney: financial indicators, dividends, stock info
          - Sina: financial statements
        """
        code = _clean_symbol(symbol)
        loop = asyncio.get_event_loop()

        result: Dict[str, Any] = {"source": self.name, "symbol": code}

        # 1. Real-time valuation from Tencent
        quote = await self.get_quote(code)
        if quote:
            result.update({
                "price": quote.price,
                "name": quote.name,
                "marketCap": quote.market_cap,  # 亿元
                "pe": quote.pe_ttm,
                "pb": quote.pb,
                "turnoverPct": quote.turnover_pct,
            })

        # 2. EastMoney stock info (industry, total shares, etc.)
        # NOTE: EastMoney push2 is blocked from non-China IPs, use short timeout
        try:
            def _fetch_info():
                market_code = 1 if code.startswith("6") else 0
                url = "https://push2.eastmoney.com/api/qt/stock/get"
                params = {
                    "fltt": "2", "invt": "2",
                    "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
                    "secid": f"{market_code}.{code}",
                }
                r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=5)
                return r.json().get("data", {})

            info = await loop.run_in_executor(None, _fetch_info)
            if info:
                result.update({
                    "longName": info.get("f58", ""),
                    "industry": info.get("f127", ""),
                    "totalShares": info.get("f84", 0),
                    "floatShares": info.get("f85", 0),
                    "listingDate": str(info.get("f189", "")),
                })
        except Exception as e:
            logger.debug(f"[{self.name}] EastMoney push2 unavailable for {code} (expected from overseas): {type(e).__name__}")

        # 3. Financial indicators from EastMoney datacenter
        try:
            def _fetch_indicators():
                return _eastmoney_datacenter(
                    "RPT_LICO_FN_CPD",
                    filter_str=f'(SECURITY_CODE="{code}")',
                    page_size=5,
                    sort_columns="REPORTDATE",
                    sort_types="-1",
                )

            indicators = await loop.run_in_executor(None, _fetch_indicators)
            if indicators:
                latest = indicators[0]
                result.update({
                    "roe": latest.get("WEIGHTAVG_ROE"),
                    "grossMargin": latest.get("XSMLL"),
                    "eps": latest.get("BASIC_EPS"),
                    "bvps": latest.get("BPS"),
                    "operatingCashflowPerShare": latest.get("MGJYXJJE"),
                    "revenueGrowthYoY": latest.get("YSTZ"),
                    "netProfitGrowthYoY": latest.get("SJLTZ"),
                })
                # Net profit for growth calculation
                if len(indicators) >= 5:
                    np0 = indicators[0].get("PARENT_NETPROFIT")
                    np4 = indicators[4].get("PARENT_NETPROFIT")
                    if np0 and np4 and np4 != 0:
                        result["netProfitYoY"] = (np0 - np4) / abs(np4)
        except Exception as e:
            logger.warning(f"[{self.name}] Financial indicators failed for {code}: {e}")

        # 4. Dividend history
        try:
            def _fetch_dividends():
                return _eastmoney_datacenter(
                    "RPT_SHAREBONUS_DET",
                    filter_str=f'(SECURITY_CODE="{code}")',
                    page_size=5,
                    sort_columns="EX_DIVIDEND_DATE",
                    sort_types="-1",
                )

            dividends = await loop.run_in_executor(None, _fetch_dividends)
            if dividends:
                latest_div = dividends[0]
                result["dividendPerShare"] = latest_div.get("PRETAX_BONUS_RMB", 0)
                result["dividendDate"] = str(latest_div.get("EX_DIVIDEND_DATE", ""))[:10]
        except Exception as e:
            logger.warning(f"[{self.name}] Dividend fetch failed for {code}: {e}")

        # 5. Sina financial statements (income statement for revenue/profit)
        try:
            def _fetch_sina_lrb():
                prefix = "sh" if code.startswith("6") else "sz"
                paper_code = f"{prefix}{code}"
                url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
                params = {
                    "paperCode": paper_code,
                    "source": "lrb",
                    "type": "0",
                    "page": "1",
                    "num": "5",
                }
                r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
                d = r.json()
                # API returns: result.data.report_list = {date: {data: [{item_title, item_value}, ...]}}
                report_list = d.get("result", {}).get("data", {}).get("report_list", {})
                if not report_list:
                    return []
                # Convert to list of dicts with item_title as key
                parsed_reports = []
                for date_key in sorted(report_list.keys(), reverse=True):
                    report = report_list[date_key]
                    items = report.get("data", [])
                    if not items:
                        continue
                    row = {"报告日": date_key}
                    for item in items:
                        title = item.get("item_title", "")
                        value = item.get("item_value")
                        if title and value is not None:
                            row[title] = value
                    parsed_reports.append(row)
                return parsed_reports

            lrb = await loop.run_in_executor(None, _fetch_sina_lrb)
            if lrb:
                latest_fin = lrb[0]
                result["revenue"] = latest_fin.get("营业收入")
                result["netProfit"] = latest_fin.get("净利润")
                result["operatingProfit"] = latest_fin.get("营业利润")
                result["reportDate"] = latest_fin.get("报告日")
                # Revenue growth
                if len(lrb) >= 5:
                    rev0 = latest_fin.get("营业收入")
                    rev4 = lrb[4].get("营业收入")
                    if rev0 and rev4:
                        try:
                            result["revenueYoY"] = (float(rev0) - float(rev4)) / abs(float(rev4))
                        except (ValueError, ZeroDivisionError):
                            pass
        except Exception as e:
            logger.warning(f"[{self.name}] Sina financial data failed for {code}: {e}")

        result["currency"] = "CNY"
        result["financialCurrency"] = "CNY"
        return result
