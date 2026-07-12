"""
A-Share Direct Provider — Primary data source for China A-Shares.

Directly connects to HTTP APIs (Tencent, EastMoney, Baidu, Sina)
without intermediate wrappers like API. Based on the architecture
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
# 同花顺 (Tonghuashun/THS) financial summary — domestic source, used as
# primary to reduce reliance on EastMoney (rate-limit / block risk).
THS_MAIN_URL = "https://basic.10jqka.com.cn/api/stock/finance/{code}_main.json"
THS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _parse_ths_num(val) -> Optional[float]:
    """Parse a THS pre-formatted number string like '36.61亿' / '-1.2万' / '0.50' → float (yuan).

    Returns None for missing/False/'--' values.
    """
    if val is None or val is False or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "")
    if s in ("--", "-", "False", "None"):
        return None
    s = s.rstrip("%")  # tolerate stray percent (caller uses _parse_ths_pct for pct)
    mult = 1.0
    for suffix, factor in (("万亿", 1e12), ("亿", 1e8), ("万", 1e4)):
        if suffix in s:
            s = s.replace(suffix, "")
            mult = factor
            break
    try:
        return float(s) * mult
    except (ValueError, TypeError):
        return None


def _parse_ths_pct(val) -> Optional[float]:
    """Parse a THS percent string like '50.23%' → 50.23 (numeric percent)."""
    if val is None or val is False or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").rstrip("%")
    if s in ("--", "-", "False", "None", ""):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _get_prefix(code: str) -> str:
    """Code → market prefix (sh/sz/bj/hk)."""
    if len(code) == 5:
        return "hk"
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    else:
        return "sz"


def _clean_symbol(symbol: str) -> str:
    """Normalize various symbol formats to pure code."""
    s = symbol.strip().upper()
    if s.endswith(".HK") or s.startswith("HK"):
        s = s.replace(".HK", "").replace("HK", "")
        # Remove any leading zeros then zero-pad to 5 for Tencent
        s = s.lstrip("0") or "0"
        return s.zfill(5)
        
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


async def fetch_a_share_ownership(code: str) -> Dict[str, float]:
    """Best-effort A-share ownership ratios from EastMoney F10 (with datacenter
    fallback for top holders). Returns a dict with any of
    {heldPercentInsiders, heldPercentInstitutions} that could be resolved, else {}.

    Kept module-level so the router can backfill ownership regardless of which
    provider won the concurrent financials race (e.g. yfinance, which lacks
    A-share holder data).
    """
    out: Dict[str, float] = {}
    prefix = "SH" if code.startswith("6") else "SZ"

    def _fetch_holders():
        url = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax"
        r = requests.get(url, params={"code": f"{prefix}{code}"},
                         headers={"User-Agent": UA}, timeout=8)
        return r.json()

    try:
        holders = await asyncio.to_thread(_fetch_holders)
    except Exception as e:
        logger.warning(f"[Ownership] F10 fetch failed for {code}: {type(e).__name__}")
        holders = None

    if holders:
        sdgd = holders.get("sdgd") or holders.get("sdltgd") or []
        if isinstance(sdgd, list) and sdgd:
            top_sum = sum((h.get("HOLD_NUM_RATIO") or 0) for h in sdgd)
            if top_sum > 0:
                out["heldPercentInsiders"] = top_sum / 100  # decimal
        jgcc = holders.get("jgcc") or []
        if isinstance(jgcc, list) and jgcc:
            inst_ratio = jgcc[0].get("TOTAL_SHARES_RATIO") or jgcc[0].get("ALL_SHARES_RATIO")
            if inst_ratio:
                out["heldPercentInstitutions"] = inst_ratio / 100  # decimal

    # Fallback: F10 PageAjax can return empty for some boards (ChiNext/STAR).
    # Use the datacenter top-10 circulating holders if insiders still missing.
    if "heldPercentInsiders" not in out:
        try:
            top = await asyncio.to_thread(
                lambda: _eastmoney_datacenter(
                    "RPT_F10_EH_FREEHOLDERS",
                    filter_str=f'(SECURITY_CODE="{code}")',
                    page_size=10, sort_columns="END_DATE",
                )
            )
            if top:
                latest = top[0].get("END_DATE")
                top_sum = sum((h.get("HOLD_RATIO") or h.get("FREE_HOLDNUM_RATIO") or 0)
                              for h in top if h.get("END_DATE") == latest)
                if top_sum > 0:
                    out["heldPercentInsiders"] = top_sum / 100  # decimal
        except Exception:
            pass

    return out


async def fetch_a_share_balance_items(code: str, periods: int = 4) -> List[Dict[str, Any]]:
    """Fetch A-share balance-sheet line items from EastMoney datacenter (no API).

    Returns detailed line items that yfinance does not break out for A-shares —
    e.g. 应收账款 (accounts receivable), 应收票据及账款, 存货 (inventory),
    货币资金 (monetary funds), 应付账款 (accounts payable). This is the reliable
    replacement for the API balance-sheet path which frequently fails with
    RemoteDisconnected.

    Returns a list (latest first) of dicts:
      {report_date, monetaryFunds, notesAndAccountsRece, accountsRece,
       inventory, accountsPayable, totalAssets, totalLiabilities}
    Empty list on failure (graceful degradation).
    """
    suffix = "SH" if code.startswith("6") else ("BJ" if code.startswith(("4", "8", "9")) else "SZ")
    secucode = f"{code}.{suffix}"

    def _fetch():
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "reportName": "RPT_F10_FINANCE_GBALANCE",
            "columns": (
                "SECUCODE,REPORT_DATE,MONETARYFUNDS,NOTE_ACCOUNTS_RECE,"
                "ACCOUNTS_RECE,INVENTORY,ACCOUNTS_PAYABLE,TOTAL_ASSETS,TOTAL_LIABILITIES"
            ),
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": "1",
            "pageSize": str(max(periods, 1)),
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "HSF10",
            "client": "PC",
        }
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=12)
        return r.json()

    try:
        data = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning(f"[BalanceItems] EastMoney fetch failed for {code}: {type(e).__name__}")
        return []

    rows = (data or {}).get("result", {}).get("data") or []
    out: List[Dict[str, Any]] = []
    for row in rows[:periods]:
        out.append({
            "report_date": str(row.get("REPORT_DATE", ""))[:10],
            "monetaryFunds": row.get("MONETARYFUNDS"),
            "notesAndAccountsRece": row.get("NOTE_ACCOUNTS_RECE"),
            "accountsRece": row.get("ACCOUNTS_RECE"),
            "inventory": row.get("INVENTORY"),
            "accountsPayable": row.get("ACCOUNTS_PAYABLE"),
            "totalAssets": row.get("TOTAL_ASSETS"),
            "totalLiabilities": row.get("TOTAL_LIABILITIES"),
        })
    return out


async def fetch_a_share_income_items(code: str, periods: int = 4) -> List[Dict[str, Any]]:
    """Fetch A-share income-statement periods from EastMoney datacenter (no API).

    Reliable replacement for API's quarterly financial abstract which fails
    frequently with RemoteDisconnected. Returns per-period revenue / net profit /
    deducted (扣非) net profit.

    Returns a list (latest first) of dicts:
      {report_date, revenue, operatingProfit, netProfit, parentNetProfit, deductNetProfit}
    Empty list on failure (graceful degradation).
    """
    suffix = "SH" if code.startswith("6") else ("BJ" if code.startswith(("4", "8", "9")) else "SZ")
    secucode = f"{code}.{suffix}"

    def _fetch():
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "reportName": "RPT_F10_FINANCE_GINCOME",
            "columns": (
                "SECUCODE,REPORT_DATE,TOTAL_OPERATE_INCOME,OPERATE_PROFIT,"
                "NETPROFIT,PARENT_NETPROFIT,DEDUCT_PARENT_NETPROFIT"
            ),
            "filter": f'(SECUCODE="{secucode}")',
            "pageNumber": "1",
            "pageSize": str(max(periods, 1)),
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "HSF10",
            "client": "PC",
        }
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=12)
        return r.json()

    try:
        data = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning(f"[IncomeItems] EastMoney fetch failed for {code}: {type(e).__name__}")
        return []

    rows = (data or {}).get("result", {}).get("data") or []
    out: List[Dict[str, Any]] = []
    for row in rows[:periods]:
        out.append({
            "report_date": str(row.get("REPORT_DATE", ""))[:10],
            "revenue": row.get("TOTAL_OPERATE_INCOME"),
            "operatingProfit": row.get("OPERATE_PROFIT"),
            "netProfit": row.get("NETPROFIT"),
            "parentNetProfit": row.get("PARENT_NETPROFIT"),
            "deductNetProfit": row.get("DEDUCT_PARENT_NETPROFIT"),
        })
    return out


async def fetch_a_share_dividends(code: str, periods: int = 5) -> List[Dict[str, Any]]:
    """Fetch A-share dividend history from EastMoney datacenter (no API).

    Reliable replacement for API's dividend detail. Returns per-period
    pre-tax cash dividend (per 10 shares) with ex-dividend date.

    Returns a list (latest first) of dicts:
      {report_date, ex_dividend_date, pretaxBonusPer10}
    Empty list on failure (graceful degradation).
    """
    def _fetch():
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "reportName": "RPT_SHAREBONUS_DET",
            "columns": "SECUCODE,REPORT_DATE,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,PLAN_NOTICE_DATE",
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": "1",
            "pageSize": str(max(periods, 1)),
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=12)
        return r.json()

    try:
        data = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning(f"[Dividends] EastMoney fetch failed for {code}: {type(e).__name__}")
        return []

    rows = (data or {}).get("result", {}).get("data") or []
    out: List[Dict[str, Any]] = []
    for row in rows[:periods]:
        out.append({
            "report_date": str(row.get("REPORT_DATE", ""))[:10],
            "ex_dividend_date": str(row.get("EX_DIVIDEND_DATE", ""))[:10],
            "pretaxBonusPer10": row.get("PRETAX_BONUS_RMB"),
        })
    return out


class AStockDirectProvider(DataProvider):
    """
    Primary A-Share data provider using direct HTTP APIs.
    No API dependency — connects directly to Tencent, EastMoney, Sina.
    """

    @property
    def name(self) -> str:
        return "a-stock-direct"

    async def get_history(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Fetch K-line history. Tries Tencent web API first (accessible),
        falls back to EastMoney push2his (geo-blocked overseas) on failure.
        """
        code = _clean_symbol(symbol)
        market_code = 116 if len(code) == 5 else (1 if code.startswith(("6", "9")) else 0)

        # Map period string to number of bars
        period_bars = {
            "1mo": 22, "3mo": 66, "6mo": 132,
            "1y": 252, "2y": 504, "5y": 1260, "10y": 2520, "max": 6000,
        }
        limit = period_bars.get(period, 2520)

        # Map interval to klt parameter
        interval_map = {
            "1d": "101", "1wk": "102", "1mo": "103", "1y": "106",
            "5m": "5", "15m": "15", "30m": "30", "60m": "60", "1h": "60"
        }
        klt = interval_map.get(interval, "101")

        # Domestic-source priority: Tencent first (accessible & reliable),
        # EastMoney as fallback (push2his is geo-blocked from non-China IPs).
        df = await self._fetch_tencent_kline(code, period, interval)
        if not df.empty:
            return df

        # Fallback: EastMoney push2his K-line
        df = await self._fetch_eastmoney_kline(code, market_code, klt, limit, period)
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

        # Tencent kline type: day/week/month/m15/m60
        kline_type = "day"
        if interval == "1wk":
            kline_type = "week"
        elif interval == "1mo":
            kline_type = "month"
        elif interval == "1y":
            kline_type = "year"
        elif interval == "15m":
            kline_type = "m15"
        elif interval == "1h" or interval == "60m":
            kline_type = "m60"

        from datetime import timedelta
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        is_min = interval in ("15m", "1h", "60m")
        if is_min:
            url = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
            params = {
                "param": f"{qt_symbol},{kline_type},,640",
            }
        else:
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
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

            if is_min:
                klines = stock_data.get(kline_type, [])
            else:
                # Try qfq (前复权) key first, then day/week/month
                klines = stock_data.get(f"qfq{kline_type}", stock_data.get(kline_type, []))
            
            if not klines:
                return pd.DataFrame()

            rows = []
            for k in klines:
                if len(k) >= 6:
                    # Minute dates are "YYYYMMDDHHMM"
                    date_val = k[0]
                    if is_min and len(date_val) == 12:
                        date_val = f"{date_val[:4]}-{date_val[4:6]}-{date_val[6:8]} {date_val[8:10]}:{date_val[10:12]}:00"
                    
                    rows.append({
                        "date": date_val,
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
                market_cap=float(vals[44]) * 1e8 if vals[44] else None,  # 亿→元
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

    def _fetch_sina_statement(self, code: str, source: str, num: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch a Sina financial statement.
          source: lrb=利润表(income), fzb=资产负债表(balance), llb=现金流量表(cashflow)
        Returns list of period dicts (latest first), keyed by Chinese item_title.
        """
        prefix = "sh" if code.startswith("6") else "sz"
        paper_code = f"{prefix}{code}"
        url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
        params = {"paperCode": paper_code, "source": source, "type": "0", "page": "1", "num": str(num)}
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
        d = r.json()
        report_list = d.get("result", {}).get("data", {}).get("report_list") or {}
        parsed = []
        for date_key in sorted(report_list.keys(), reverse=True):
            items = report_list[date_key].get("data", [])
            if not items:
                continue
            row = {"报告日": date_key}
            for item in items:
                title = item.get("item_title", "")
                value = item.get("item_value")
                if title and value is not None:
                    row[title] = value
            parsed.append(row)
        return parsed

    def _fetch_ths_main(self, code: str) -> Dict[str, Any]:
        """
        Fetch 同花顺 (THS) main financial summary.

        THS exposes 24 financial metrics × dozens of reporting periods at
        basic.10jqka.com.cn. This is a *domestic* source and is used as the
        primary financial-indicator provider so we don't depend on EastMoney
        (which may be rate-limited / blocked).

        Returns a dict::

            {
              "indicators": [ {REPORTDATE, PARENT_NETPROFIT, TOTAL_OPERATE_INCOME,
                               DEDUCT_PARENT_NETPROFIT, WEIGHTAVG_ROE, XSMLL,
                               BASIC_EPS, BPS, MGJYXJJE, YSTZ, SJLTZ,
                               YSHZ, SJLHZ}, ... ],   # newest-first, numeric
              "direct": { roe, grossMargin, profitMargin, currentRatio,
                          quickRatio, debtRatio, inventoryTurnover,
                          netProfitDeductYoY },
            }

        The ``indicators`` list mirrors EastMoney ``RPT_LICO_FN_CPD`` so the
        existing downstream TTM / CAGR / QoQ logic works unchanged. Returns
        ``{}`` on any failure (caller falls back to EastMoney).
        """
        url = THS_MAIN_URL.format(code=code)
        r = requests.get(url, headers={"User-Agent": THS_UA,
                                       "Referer": "https://basic.10jqka.com.cn/"}, timeout=10)
        d = r.json()
        fd = d.get("flashData")
        if isinstance(fd, str):
            fd = json.loads(fd)
        if not isinstance(fd, dict):
            return {}
        report = fd.get("report") or []
        if not report or not report[0]:
            return {}
        # Title index → metric position. report[i] is the value array for titles[i].
        # Positions are fixed by THS schema (validated against live data).
        IDX = {
            "netProfit": 1, "netProfitYoY": 2, "deduct": 3, "deductYoY": 4,
            "revenue": 5, "revenueYoY": 6, "eps": 7, "bvps": 8,
            "ocfps": 11, "profitMargin": 12, "grossMargin": 13, "roe": 14,
            "inventoryTurnover": 17, "currentRatio": 20, "quickRatio": 21,
            "debtRatio": 24,
        }

        # ---- Prefer header-name based mapping when THS titles array is available ----
        TITLE_TO_KEY = {
            "净利润": "netProfit", "净利润(元)": "netProfit",
            "净利润同比增长率": "netProfitYoY",
            "扣非净利润": "deduct", "扣非净利润(元)": "deduct",
            "扣非净利润同比增长率": "deductYoY",
            "营业总收入": "revenue", "营业收入": "revenue",
            "营业总收入(元)": "revenue", "营业收入(元)": "revenue",
            "营业总收入同比增长率": "revenueYoY", "营业收入同比增长率": "revenueYoY",
            "基本每股收益": "eps", "每股收益": "eps",
            "每股净资产": "bvps", "每股净资产(元)": "bvps",
            "每股经营现金流": "ocfps",
            "销售毛利率": "grossMargin", "毛利率": "grossMargin",
            "销售净利率": "profitMargin", "净利率": "profitMargin",
            "加权净资产收益率": "roe", "净资产收益率": "roe",
            "存货周转率": "inventoryTurnover",
            "流动比率": "currentRatio",
            "速动比率": "quickRatio",
            "资产负债率": "debtRatio",
        }
        titles = fd.get("titles", [])
        if titles:
            named_idx = {}
            for pos, title_name in enumerate(titles):
                key = TITLE_TO_KEY.get(str(title_name).strip())
                if key:
                    named_idx[key] = pos
            if named_idx:
                IDX = dict(IDX)
                IDX.update(named_idx)
                logger.info(f"[THS] Title-column mapping for {code}: {len(named_idx)} columns resolved")

        def col(i):
            if 0 <= i < len(report):
                return report[i]
            logger.warning(f"[THS] Column index {i} >= report columns {len(report)} for {code}")
            return []

        dates = col(IDX["revenue"]) and report[0] or report[0]
        periods = report[0]

        # QoQ (环比) series — simple_mom rows align to titles like report
        mom = fd.get("simple_mom")
        if isinstance(mom, str):
            try:
                mom = json.loads(mom)
            except Exception:
                mom = None

        def mom_col(i):
            if isinstance(mom, list) and 0 <= i < len(mom):
                return mom[i]
            return []

        indicators: List[Dict[str, Any]] = []
        n = len(periods)
        for p in range(n):
            def num(idx):
                c = col(idx)
                return _parse_ths_num(c[p]) if p < len(c) else None

            def pct(idx):
                c = col(idx)
                return _parse_ths_pct(c[p]) if p < len(c) else None

            def mompct(idx):
                c = mom_col(idx)
                return _parse_ths_pct(c[p]) if p < len(c) else None

            row = {
                "REPORTDATE": periods[p],
                "PARENT_NETPROFIT": num(IDX["netProfit"]),
                "TOTAL_OPERATE_INCOME": num(IDX["revenue"]),
                "DEDUCT_PARENT_NETPROFIT": num(IDX["deduct"]),
                "WEIGHTAVG_ROE": pct(IDX["roe"]),
                "XSMLL": pct(IDX["grossMargin"]),
                "BASIC_EPS": num(IDX["eps"]),
                "BPS": num(IDX["bvps"]),
                "MGJYXJJE": num(IDX["ocfps"]),
                "YSTZ": pct(IDX["revenueYoY"]),
                "SJLTZ": pct(IDX["netProfitYoY"]),
                "YSHZ": mompct(IDX["revenue"]),
                "SJLHZ": mompct(IDX["netProfit"]),
            }
            indicators.append(row)

        # Direct ratios/margins (latest period) THS provides ready-made
        direct: Dict[str, Any] = {}
        roe0 = _parse_ths_pct(col(IDX["roe"])[0]) if col(IDX["roe"]) else None
        if roe0 is not None:
            direct["roe"] = roe0  # percent
        gm0 = _parse_ths_pct(col(IDX["grossMargin"])[0]) if col(IDX["grossMargin"]) else None
        if gm0 is not None:
            direct["grossMargin"] = gm0  # percent
        pm0 = _parse_ths_pct(col(IDX["profitMargin"])[0]) if col(IDX["profitMargin"]) else None
        if pm0 is not None:
            direct["profitMargin"] = pm0 / 100.0  # decimal (compiler expects fraction)
        cr0 = _parse_ths_num(col(IDX["currentRatio"])[0]) if col(IDX["currentRatio"]) else None
        if cr0 is not None:
            direct["currentRatio"] = cr0
        qr0 = _parse_ths_num(col(IDX["quickRatio"])[0]) if col(IDX["quickRatio"]) else None
        if qr0 is not None:
            direct["quickRatio"] = qr0
        dr0 = _parse_ths_pct(col(IDX["debtRatio"])[0]) if col(IDX["debtRatio"]) else None
        if dr0 is not None:
            direct["debtRatio"] = dr0 / 100.0  # decimal
        it0 = _parse_ths_num(col(IDX["inventoryTurnover"])[0]) if col(IDX["inventoryTurnover"]) else None
        if it0 is not None:
            direct["inventoryTurnover"] = it0
        dyoy0 = _parse_ths_pct(col(IDX["deductYoY"])[0]) if col(IDX["deductYoY"]) else None
        if dyoy0 is not None:
            direct["netProfitDeductYoY"] = dyoy0  # percent

        return {"indicators": indicators, "direct": direct}

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

        # 3. Financial indicators — 同花顺 (THS) PRIMARY, EastMoney FALLBACK.
        #    THS is a domestic source; preferring it (with Sina/Tencent) avoids
        #    EastMoney rate-limiting / blocking. The THS indicator list mirrors
        #    EastMoney RPT_LICO_FN_CPD so all downstream TTM/CAGR logic is shared.
        indicators = []
        ths_direct: Dict[str, Any] = {}
        try:
            ths = await loop.run_in_executor(None, self._fetch_ths_main, code)
            if ths and ths.get("indicators"):
                indicators = ths["indicators"]
                ths_direct = ths.get("direct") or {}
                logger.info(f"[{self.name}] THS financial indicators OK for {code} "
                            f"({len(indicators)} periods)")
        except Exception as e:
            logger.debug(f"[{self.name}] THS financial fetch failed for {code}: {type(e).__name__}: {e}")

        try:
            if not indicators:
                def _fetch_indicators():
                    return _eastmoney_datacenter(
                        "RPT_LICO_FN_CPD",
                        filter_str=f'(SECURITY_CODE="{code}")',
                        page_size=24,
                        sort_columns="REPORTDATE",
                        sort_types="-1",
                    )

                indicators = await loop.run_in_executor(None, _fetch_indicators)
                if indicators:
                    logger.info(f"[{self.name}] EastMoney financial indicators (fallback) for {code}")
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
                    # Alias for PEG computation in report compiler
                    "netProfitGrowth": latest.get("SJLTZ"),
                })
                # Net profit / revenue as numbers (avoid Sina string-typing issues)
                if latest.get("PARENT_NETPROFIT") is not None:
                    result["netProfit"] = latest.get("PARENT_NETPROFIT")
                if latest.get("TOTAL_OPERATE_INCOME") is not None:
                    result["revenue"] = latest.get("TOTAL_OPERATE_INCOME")
                # Sequential (QoQ) growth — EastMoney provides directly (percent)
                if latest.get("YSHZ") is not None:
                    result["revenueQoQ"] = latest.get("YSHZ")
                if latest.get("SJLHZ") is not None:
                    result["netProfitQoQ"] = latest.get("SJLHZ")
                # Net profit YoY (same period prior year)
                if len(indicators) >= 5:
                    np0 = indicators[0].get("PARENT_NETPROFIT")
                    np4 = indicators[4].get("PARENT_NETPROFIT")
                    if np0 and np4 and np4 != 0:
                        result["netProfitYoY"] = (np0 - np4) / abs(np4)
                # 3-year CAGR from annual (12-31) reports
                annuals = [r for r in indicators if str(r.get("REPORTDATE", ""))[:10].endswith("-12-31")]
                if len(annuals) >= 4:
                    def _cagr(key):
                        v0 = annuals[0].get(key)
                        v3 = annuals[3].get(key)
                        if v0 and v3 and v3 > 0:
                            return ((v0 / v3) ** (1 / 3) - 1) * 100  # percent
                        return None
                    rc = _cagr("TOTAL_OPERATE_INCOME")
                    ic = _cagr("PARENT_NETPROFIT")
                    if rc is not None:
                        result["revenueCagr3y"] = rc
                    if ic is not None:
                        result["incomeCagr3y"] = ic
        except Exception as e:
            logger.warning(f"[{self.name}] Financial indicators failed for {code}: {e}")

        # 3a. Apply THS-provided ready-made ratios/margins (already correct units).
        #     These take precedence as they come straight from THS's computed values.
        for k, v in ths_direct.items():
            if v is not None:
                result[k] = v
        # Deduct net profit (扣非净利润) + YoY/QoQ derived from THS indicator history
        # (THS already carries DEDUCT_PARENT_NETPROFIT per period → no EastMoney call).
        if indicators and indicators[0].get("DEDUCT_PARENT_NETPROFIT") is not None:
            result["netProfitDeduct"] = indicators[0].get("DEDUCT_PARENT_NETPROFIT")
            if "netProfitDeductYoY" not in result and len(indicators) >= 5:
                dd0 = indicators[0].get("DEDUCT_PARENT_NETPROFIT")
                dd4 = indicators[4].get("DEDUCT_PARENT_NETPROFIT")
                if dd0 and dd4 and dd4 != 0:
                    result["netProfitDeductYoY"] = (dd0 - dd4) / abs(dd4) * 100  # percent
            try:
                def _single_q_d(rows, i):
                    rd = str(rows[i].get("REPORTDATE", ""))[:10]
                    cum = rows[i].get("DEDUCT_PARENT_NETPROFIT")
                    if cum is None:
                        return None
                    if rd.endswith("-03-31"):
                        return cum
                    if i + 1 < len(rows) and rows[i + 1].get("DEDUCT_PARENT_NETPROFIT") is not None:
                        return cum - rows[i + 1].get("DEDUCT_PARENT_NETPROFIT")
                    return None
                cq = _single_q_d(indicators, 0)
                pq = _single_q_d(indicators, 1)
                if cq is not None and pq not in (None, 0):
                    result["netProfitDeductQoQ"] = (cq - pq) / abs(pq) * 100
            except Exception:
                pass

        # 3b. Deduct net profit (扣非净利润) — EastMoney FALLBACK only if THS missed it.
        if result.get("netProfitDeduct") is None:
          try:
            def _fetch_deduct():
                return _eastmoney_datacenter(
                    "RPT_DMSK_FN_INCOME",
                    filter_str=f'(SECURITY_CODE="{code}")',
                    page_size=8,
                    sort_columns="REPORT_DATE",
                    sort_types="-1",
                )

            deducts = await loop.run_in_executor(None, _fetch_deduct)
            if deducts:
                d0 = deducts[0].get("DEDUCT_PARENT_NETPROFIT")
                if d0 is not None:
                    result["netProfitDeduct"] = d0
                if len(deducts) >= 5:
                    d4 = deducts[4].get("DEDUCT_PARENT_NETPROFIT")
                    if d0 and d4 and d4 != 0:
                        result["netProfitDeductYoY"] = (d0 - d4) / abs(d4) * 100  # percent
                    # QoQ from single-quarter values (cumulative reports → diff)
                    try:
                        def _single_q(rows, i):
                            rd = str(rows[i].get("REPORT_DATE", ""))[:10]
                            cum = rows[i].get("DEDUCT_PARENT_NETPROFIT")
                            if cum is None:
                                return None
                            if rd.endswith("-03-31"):
                                return cum  # Q1 cumulative == single quarter
                            if i + 1 < len(rows) and rows[i + 1].get("DEDUCT_PARENT_NETPROFIT") is not None:
                                return cum - rows[i + 1].get("DEDUCT_PARENT_NETPROFIT")
                            return None
                        cur_q = _single_q(deducts, 0)
                        prev_q = _single_q(deducts, 1)
                        if cur_q is not None and prev_q not in (None, 0):
                            result["netProfitDeductQoQ"] = (cur_q - prev_q) / abs(prev_q) * 100
                    except Exception:
                        pass
          except Exception as e:
            logger.warning(f"[{self.name}] Deduct profit fetch failed for {code}: {e}")

        # 3c. Shareholder & institutional ownership — EastMoney F10 (+ datacenter fallback)
        try:
            own = await fetch_a_share_ownership(code)
            result.update(own)
        except Exception as e:
            logger.warning(f"[{self.name}] Shareholder fetch unavailable for {code}: {type(e).__name__}: {e}")

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
                # Only set if EastMoney didn't already provide numeric values
                if result.get("revenue") is None:
                    result["revenue"] = latest_fin.get("营业收入")
                if result.get("netProfit") is None:
                    result["netProfit"] = latest_fin.get("净利润")
                result["operatingProfit"] = latest_fin.get("营业利润")
                result["_costOfRevenue"] = latest_fin.get("营业成本")
                result["reportDate"] = latest_fin.get("报告日")
                # Annual figures (for TTM-style ratios) — lrb[1] is usually prior annual
                for row in lrb:
                    if str(row.get("报告日", "")).endswith("1231"):
                        result["_annualRevenue"] = row.get("营业收入")
                        result["_annualCostOfRevenue"] = row.get("营业成本")
                        break
                # Revenue growth
                if result.get("revenueYoY") is None and len(lrb) >= 5:
                    rev0 = latest_fin.get("营业收入")
                    rev4 = lrb[4].get("营业收入")
                    if rev0 and rev4:
                        try:
                            result["revenueYoY"] = (float(rev0) - float(rev4)) / abs(float(rev4))
                        except (ValueError, ZeroDivisionError):
                            pass
        except Exception as e:
            logger.warning(f"[{self.name}] Sina financial data failed for {code}: {e}")

        # 6. Sina balance sheet (fzb) + cash flow (llb) → derive missing metrics
        #    Margins, leverage/liquidity ratios, ROA, cash flow, FCF.
        try:
            def _to_float(x):
                try:
                    if x is None:
                        return None
                    if isinstance(x, (int, float)):
                        return float(x)
                    s = str(x).strip().replace(",", "").replace("，", "")
                    if s in ("--", "-", "", "False", "None"):
                        return None
                    # Chinese magnitude suffixes in Sina statement values
                    mult = 1.0
                    for suffix, factor in (("万亿", 1e12), ("亿", 1e8), ("万", 1e4)):
                        if suffix in s:
                            s = s.replace(suffix, "")
                            mult = factor
                            break
                    return float(s) * mult
                except (ValueError, TypeError):
                    return None

            revenue = _to_float(result.get("revenue"))
            net_profit = _to_float(result.get("netProfit"))
            op_profit = _to_float(result.get("operatingProfit"))

            # TTM revenue / net profit from indicator history (single-quarter sum of last 4)
            ttm_revenue = ttm_net_profit = None
            try:
                def _single_q_series(rows, key):
                    out = []
                    for i, row in enumerate(rows):
                        rd = str(row.get("REPORTDATE", ""))[:10]
                        cum = row.get(key)
                        if cum is None:
                            out.append(None)
                            continue
                        if rd.endswith("-03-31"):
                            out.append(cum)
                        elif i + 1 < len(rows) and rows[i + 1].get(key) is not None:
                            out.append(cum - rows[i + 1].get(key))
                        else:
                            out.append(None)
                    return out
                if indicators and len(indicators) >= 4:
                    rev_q = _single_q_series(indicators, "TOTAL_OPERATE_INCOME")[:4]
                    np_q = _single_q_series(indicators, "PARENT_NETPROFIT")[:4]
                    if all(x is not None for x in rev_q):
                        ttm_revenue = sum(rev_q)
                    if all(x is not None for x in np_q):
                        ttm_net_profit = sum(np_q)
            except Exception:
                pass
            # Fallback to latest annual revenue if TTM unavailable
            if ttm_revenue is None:
                ttm_revenue = _to_float(result.get("_annualRevenue"))

            # Margins (same-period ratio — no annualization needed)
            if revenue and net_profit is not None and "profitMargin" not in result:
                result["profitMargin"] = net_profit / revenue
            if revenue and op_profit is not None:
                result["operatingMargin"] = op_profit / revenue
            # Gross margin fallback (EastMoney may be geo-blocked)
            cost_rev = _to_float(result.pop("_costOfRevenue", None))
            annual_cost = _to_float(result.pop("_annualCostOfRevenue", None))
            if revenue and cost_rev is not None and not result.get("grossMargin"):
                result["grossMargin"] = (revenue - cost_rev) / revenue * 100  # percent

            market_cap = _to_float(result.get("marketCap"))
            # Price-to-Sales (market cap / TTM revenue)
            if market_cap and ttm_revenue and ttm_revenue > 0 and "priceToSales" not in result:
                result["priceToSales"] = market_cap / ttm_revenue

            # Balance sheet
            fzb = await loop.run_in_executor(None, self._fetch_sina_statement, code, "fzb", 1)
            if fzb:
                b = fzb[0]
                total_assets = _to_float(b.get("资产总计"))
                total_liab = _to_float(b.get("负债合计"))
                cur_assets = _to_float(b.get("流动资产合计"))
                cur_liab = _to_float(b.get("流动负债合计"))
                inventory = _to_float(b.get("存货"))
                equity = _to_float(b.get("所有者权益(或股东权益)合计"))
                if total_assets and total_liab is not None and "debtRatio" not in result:
                    result["debtRatio"] = total_liab / total_assets
                if cur_assets is not None and cur_liab:
                    if "currentRatio" not in result:
                        result["currentRatio"] = cur_assets / cur_liab
                    if inventory is not None and "quickRatio" not in result:
                        result["quickRatio"] = (cur_assets - inventory) / cur_liab
                # ROA — period net profit / total assets (matches A-share YTD convention)
                if total_assets and net_profit is not None and "roa" not in result:
                    result["roa"] = net_profit / total_assets
                # ROE fallback (EastMoney may be geo-blocked) — period-based, percent
                if equity and net_profit is not None and not result.get("roe"):
                    result["roe"] = net_profit / equity * 100

                # Cash & interest-bearing debt
                cash = _to_float(b.get("货币资金")) or 0
                trading_assets = _to_float(b.get("交易性金融资产")) or 0
                total_cash = cash + trading_assets
                short_debt = _to_float(b.get("短期借款")) or 0
                long_debt = _to_float(b.get("长期借款")) or 0
                bonds = _to_float(b.get("应付债券")) or 0
                short_bonds = _to_float(b.get("应付短期债券")) or 0
                total_debt = short_debt + long_debt + bonds + short_bonds
                if total_cash > 0:
                    result["totalCash"] = total_cash
                if total_debt > 0:
                    result["totalDebt"] = total_debt
                    result["netCash"] = total_cash - total_debt
                # Enterprise value = market cap + total debt - cash
                if market_cap and total_debt > 0:
                    result["enterpriseValue"] = market_cap + total_debt - total_cash
                # Asset / inventory turnover (use TTM flows)
                if total_assets and ttm_revenue and "assetTurnover" not in result:
                    result["assetTurnover"] = ttm_revenue / total_assets
                ttm_cost = annual_cost or (cost_rev * 4 if cost_rev else None)
                if inventory and ttm_cost and "inventoryTurnover" not in result:
                    result["inventoryTurnover"] = ttm_cost / inventory

            # Cash flow statement
            llb = await loop.run_in_executor(None, self._fetch_sina_statement, code, "llb", 1)
            if llb:
                cf = llb[0]
                op_cf = _to_float(cf.get("经营活动产生的现金流量净额"))
                capex = _to_float(cf.get("购建固定资产、无形资产和其他长期资产所支付的现金"))
                if op_cf is not None:
                    result["operatingCashflow"] = op_cf
                if capex is not None:
                    result["capitalExpenditure"] = capex
                    if op_cf is not None:
                        result["freeCashflow"] = op_cf - capex

            # Dividend yield & payout (dividendPerShare is per-10-shares, pretax CNY)
            dps10 = _to_float(result.get("dividendPerShare"))
            price = _to_float(result.get("price"))
            if dps10 and price and price > 0:
                dps = dps10 / 10.0  # per single share
                result["dividendRate"] = dps
                result["dividendYield"] = dps / price * 100  # percent
                # Payout ratio vs latest annual EPS
                annual_eps = None
                if indicators:
                    for row in indicators:
                        if str(row.get("REPORTDATE", ""))[:10].endswith("-12-31"):
                            annual_eps = _to_float(row.get("BASIC_EPS"))
                            break
                if annual_eps and annual_eps > 0:
                    result["payoutRatio"] = dps / annual_eps  # decimal
        except Exception as e:
            logger.warning(f"[{self.name}] Sina balance/cashflow derivation failed for {code}: {e}")

        # 7. 52-week high/low (for price percentile) from 1-year K-line
        try:
            hist = await self._fetch_tencent_kline(code, period="1y", interval="1d")
            if hist is not None and not hist.empty and "high" in hist and "low" in hist:
                hi = float(hist["high"].max())
                lo = float(hist["low"].min())
                if hi > 0 and lo > 0:
                    result["fiftyTwoWeekHigh"] = hi
                    result["fiftyTwoWeekLow"] = lo
        except Exception as e:
            logger.debug(f"[{self.name}] 52-week range unavailable for {code}: {type(e).__name__}")

        # 8. Quarterly history (for valuation guidance in discussion prompt)
        #    Populated from the existing indicator rows, mapped to QuarterlyHistory schema.
        try:
            qh_list: List[Dict[str, Any]] = []
            if indicators:
                for row in indicators:
                    q = {
                        "period": str(row.get("REPORTDATE", ""))[:10] if row.get("REPORTDATE") else "",
                        "revenue": row.get("TOTAL_OPERATE_INCOME"),
                        "revenueYoY": row.get("YSTZ"),
                        "netProfit": row.get("PARENT_NETPROFIT"),
                        "netProfitYoY": row.get("SJLTZ"),
                        "netProfitDeduct": row.get("DEDUCT_PARENT_NETPROFIT"),
                        "grossMargin": row.get("XSMLL"),
                        "roe": row.get("WEIGHTAVG_ROE"),
                        "eps": row.get("BASIC_EPS"),
                        "bvps": row.get("BPS"),
                        "ocfPerShare": row.get("MGJYXJJE"),
                    }
                    # Compute net profit margin from available data
                    rev = q["revenue"]
                    np_ = q["netProfit"]
                    if rev is not None and np_ is not None and float(rev) != 0:
                        q["netMargin"] = float(np_) / float(rev)
                    # YoY for deducted net profit across same-quarter-last-year
                    qh_list.append(q)
                for i, q in enumerate(qh_list):
                    if i + 4 < len(qh_list):
                        cur = q.get("netProfitDeduct")
                        prv = qh_list[i + 4].get("netProfitDeduct")
                        if cur is not None and prv is not None and prv != 0:
                            q["netProfitDeductYoY"] = (cur - prv) / abs(prv) * 100
            result["quarterlyHistory"] = qh_list
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to build quarterlyHistory for {code}: {e}")
            result["quarterlyHistory"] = []

        result["currency"] = "CNY"
        result["financialCurrency"] = "CNY"
        return result
