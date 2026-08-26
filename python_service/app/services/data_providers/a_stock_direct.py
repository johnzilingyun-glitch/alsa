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
import re
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


def _to_float_safe(x) -> Optional[float]:
    """Convert int/float/str to float, handling Chinese magnitude suffixes and sentinels.

    Returns None for unparseable values (e.g. '--', '-', '', 'False', 'None').
    Does NOT modify the section-6 inline _to_float — this is a separate module-level helper.
    """
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", "").replace("，", "")
        if s in ("--", "-", "", "False", "None"):
            return None
        mult = 1.0
        for suffix, factor in (("万亿", 1e12), ("亿", 1e8), ("万", 1e4)):
            if suffix in s:
                s = s.replace(suffix, "")
                mult = factor
                break
        return float(s) * mult
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


async def fetch_a_share_ownership(code: str) -> Dict[str, Any]:
    """Best-effort A-share ownership from EastMoney F10. Returns a dict that may
    contain:
      - heldPercentInsiders:     float  (decimal fraction of shares held by top-10 holders)
      - heldPercentInstitutions: float  (decimal fraction held by institutions, EastMoney 机构持股)
      - topCirculatingHolders:   List[Dict]  (前十大流通股东: rank/name/type/shares/pct/change/endDate)

    Kept module-level so the router can backfill ownership regardless of which
    provider won the concurrent financials race (e.g. yfinance, which lacks
    A-share holder data).

    UNIT NOTE (fixes the 100x distortion): EastMoney `TOTAL_SHARES_RATIO` and
    `HOLD_NUM_RATIO` are already decimal fractions (0.0085 == 0.85%). The old code
    did `inst_ratio / 100`, understating institutional holdings by 100x — this is
    the "筹码结构严重失真" bug for non-dual-listed A-shares. Do NOT divide by 100.
    """
    out: Dict[str, Any] = {}
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
        # 前十大流通股东 — the REAL A-share chip structure. Prefer `sdltgd`
        # (carries HOLDER_TYPE + FREE_HOLDNUM_RATIO for circulating shares) over
        # `sdgd`.
        sdltgd = holders.get("sdltgd") or holders.get("sdgd") or []
        if isinstance(sdltgd, list) and sdltgd:
            top_sum = sum((h.get("HOLD_NUM_RATIO") or 0) for h in sdltgd)
            if top_sum > 0:
                # HOLD_NUM_RATIO is a percent (54.4) -> divide by 100 for decimal.
                out["heldPercentInsiders"] = top_sum / 100
            top_holders = []
            for h in sdltgd[:10]:
                top_holders.append({
                    "rank": h.get("HOLDER_RANK"),
                    "name": h.get("HOLDER_NAME"),
                    "type": h.get("HOLDER_TYPE"),
                    "shares": h.get("HOLD_NUM"),
                    "pct": h.get("FREE_HOLDNUM_RATIO") or h.get("HOLD_NUM_RATIO"),
                    "change": h.get("HOLD_NUM_CHANGE"),
                    "endDate": str(h.get("END_DATE"))[:10] if h.get("END_DATE") else None,
                })
            if top_holders:
                out["topCirculatingHolders"] = top_holders
        # 机构持股 (institutions) — EastMoney jgcc TOTAL_SHARES_RATIO is a percentage (e.g., 12.5117 = 12.5117%)
        jgcc = holders.get("jgcc") or []
        if isinstance(jgcc, list) and jgcc:
            inst_ratio = jgcc[0].get("TOTAL_SHARES_RATIO") or jgcc[0].get("ALL_SHARES_RATIO")
            if inst_ratio:
                out["heldPercentInstitutions"] = float(inst_ratio) / 100.0

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


async def fetch_industry_valuation(industry_name: str) -> Dict[str, Any]:
    """Fetch industry valuation benchmarks from EastMoney datacenter.

    Queries RPT_VALUEANALYSIS_DET by BOARD_NAME to get peer-company
    valuation metrics (PE, PB, PS) and computes industry medians/means.
    Also samples up to 40 largest constituents to compute net margin and
    revenue growth from income statements.

    Returns {} on any failure (graceful degradation).
    The returned dict may contain any of:
      pe_avg, pe_med, pb_avg, pb_med, ps_avg, ps_med,
      net_margin_avg, net_margin_med, revenue_growth_avg, revenue_growth_med.
    """
    def _fetch_page(page_number: int) -> List[Dict]:
        url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        params = {
            "reportName": "RPT_VALUEANALYSIS_DET",
            "columns": "ALL",
            "filter": f'(BOARD_NAME="{industry_name}")',
            "pageNumber": str(page_number),
            "pageSize": "500",
            "sortColumns": "",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "PC",
        }
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=30)
            d = r.json()
            if d.get("result") and d["result"].get("data"):
                return d["result"]["data"]
        except Exception as e:
            logger.warning(f"[IndustryValuation] Page {page_number} error: {type(e).__name__}: {e}")
        return []

    try:
        rows = await asyncio.to_thread(_fetch_page, 1)
        if not rows:
            return {}
        all_rows = list(rows)
        while len(rows) == 500 and len(all_rows) < 1000:
            next_page = len(all_rows) // 500 + 1
            rows = await asyncio.to_thread(_fetch_page, next_page)
            if rows:
                all_rows.extend(rows)
            else:
                break
    except Exception as e:
        logger.warning(f"[IndustryValuation] Failed to fetch for {industry_name}: {type(e).__name__}: {e}")
        return {}

    pe_vals: List[float] = []
    pb_vals: List[float] = []
    ps_vals: List[float] = []

    for row in all_rows:
        try:
            pe = row.get("PE_TTM")
            if pe is not None and float(pe) > 0:
                pe_vals.append(float(pe))
        except (TypeError, ValueError):
            pass
        try:
            pb = row.get("PB_MRQ")
            if pb is not None and float(pb) > 0:
                pb_vals.append(float(pb))
        except (TypeError, ValueError):
            pass
        try:
            ps = row.get("PS_TTM")
            if ps is not None and float(ps) > 0:
                ps_vals.append(float(ps))
        except (TypeError, ValueError):
            pass

    def _stats(vals: List[float]):
        if not vals:
            return None, None
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        mean = sum(sorted_vals) / n
        if n % 2 == 0:
            med = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        else:
            med = sorted_vals[n // 2]
        return mean, med

    out: Dict[str, Any] = {}

    pe_mean, pe_med = _stats(pe_vals)
    if pe_mean is not None:
        out["pe_avg"] = round(pe_mean, 2)
        out["pe_med"] = round(pe_med, 2)

    pb_mean, pb_med = _stats(pb_vals)
    if pb_mean is not None:
        out["pb_avg"] = round(pb_mean, 2)
        out["pb_med"] = round(pb_med, 2)

    ps_mean, ps_med = _stats(ps_vals)
    if ps_mean is not None:
        out["ps_avg"] = round(ps_mean, 2)
        out["ps_med"] = round(ps_med, 2)

    # --- Net margin & revenue growth from income statements ---
    # Pick up to 40 largest constituents (by TOTAL_MARKET_CAP)
    constituents = sorted(
        all_rows,
        key=lambda r: float(r.get("TOTAL_MARKET_CAP") or 0),
        reverse=True,
    )[:40]

    income_codes: List[str] = []
    for c in constituents:
        secucode = c.get("SECURITY_CODE") or c.get("SECUCODE") or ""
        code = secucode.split(".")[0] if secucode else ""
        # Must be a 6-digit A-share code
        code = code.strip()
        if len(code) == 6 and code.isdigit():
            income_codes.append(code)

    if income_codes:
        # Bound concurrency: 40 simultaneous requests fail in this sandbox
        # (rate-limit / connection-pool exhaustion); a semaphore keeps it reliable.
        sem = asyncio.Semaphore(8)

        async def _fetch_inc(code: str):
            async with sem:
                return await fetch_a_share_income_items(code, periods=5)

        income_results = await asyncio.gather(
            *[_fetch_inc(c) for c in income_codes], return_exceptions=True
        )

        net_margins: List[float] = []
        revenue_growths: List[float] = []

        for inc in income_results:
            if isinstance(inc, Exception) or not inc:
                continue
            r0 = inc[0]
            rev0 = r0.get("revenue")
            np0 = r0.get("netProfit")
            if rev0 is not None and np0 is not None:
                try:
                    rev0_f = float(rev0)
                    np0_f = float(np0)
                    if rev0_f > 0:
                        net_margins.append(np0_f / rev0_f)
                except (TypeError, ValueError):
                    pass
            # Revenue growth: year-over-year (latest quarter vs same quarter 1y earlier).
            # Income data is quarterly sorted desc; index 4 = 4 quarters prior = YoY.
            if len(inc) >= 5:
                rev0 = inc[0].get("revenue")
                rev4 = inc[4].get("revenue")
                if rev0 is not None and rev4 is not None:
                    try:
                        rev0_f = float(rev0)
                        rev4_f = float(rev4)
                        if rev4_f > 0:
                            revenue_growths.append((rev0_f - rev4_f) / abs(rev4_f))
                    except (TypeError, ValueError):
                        pass

        nm_mean, nm_med = _stats(net_margins)
        if nm_mean is not None:
            out["net_margin_avg"] = round(nm_mean * 100, 2)
            out["net_margin_med"] = round(nm_med * 100, 2)

        rg_mean, rg_med = _stats(revenue_growths)
        if rg_mean is not None:
            out["revenue_growth_avg"] = round(rg_mean * 100, 2)
            out["revenue_growth_med"] = round(rg_med * 100, 2)

    logger.info(
        "[IndustryValuation] %s: %d constituents, PE=%d PB=%d PS=%d codes=%d nm=%s rg=%s",
        industry_name, len(all_rows), len(pe_vals), len(pb_vals), len(ps_vals),
        len(income_codes),
        "yes" if "net_margin_avg" in out else "no",
        "yes" if "revenue_growth_avg" in out else "no",
    )
    return out


async def fetch_industry_peers(
    industry_name: str,
    top_n: int = 10,
    exclude_symbol: str = "",
) -> List[Dict[str, Any]]:
    """Fetch top-N industry peer companies with valuation data.

    Uses EastMoney RPT_VALUEANALYSIS_DET for per-company PE / PB / market cap
    (single bulk call), then best-effort fetches ROE and computes net margin
    from RPT_LICO_FN_CPD for each peer.

    Returns a list of dicts shaped for the report comps table::

        [{name, symbol, pe, pb, roe, margin, marketCap, vs_target}, ...]

    Returns empty list on any failure (graceful degradation).
    The ``top_n`` peers are selected by total market cap (descending).
    ``exclude_symbol`` (e.g. the target stock itself) is stripped from results.
    ``roe`` and ``margin`` may be None when the API is unreachable.
    """
    # ── Phase 1: constituent list with PE/PB/MCap ──────────────────────
    try:
        def _fetch_page(page_number: int) -> List[Dict]:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "reportName": "RPT_VALUEANALYSIS_DET",
                "columns": (
                    "SECURITY_CODE,SECURITY_NAME_ABBR,PE_TTM,PB_MRQ,"
                    "TOTAL_MARKET_CAP,TRADE_DATE"
                ),
                "filter": f'(BOARD_NAME="{industry_name}")',
                "pageNumber": str(page_number),
                "pageSize": "500",
                "sortColumns": "TRADE_DATE,SECURITY_CODE",
                "sortTypes": "-1,1",
                "source": "WEB",
                "client": "PC",
            }
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=30)
            d = r.json()
            if d.get("result") and d["result"].get("data"):
                return d["result"]["data"]
            return []

        rows = await asyncio.to_thread(_fetch_page, 1)
        if not rows:
            return []
        all_rows = list(rows)
        # Paginate if page was full (up to safety cap of 2000)
        while len(rows) == 500 and len(all_rows) < 2000:
            next_page = len(all_rows) // 500 + 1
            rows = await asyncio.to_thread(_fetch_page, next_page)
            if rows:
                all_rows.extend(rows)
            else:
                break
    except Exception as e:
        logger.warning(
            "[IndustryPeers] RPT_VALUEANALYSIS_DET failed for %s: %s",
            industry_name, e,
        )
        return []

    # Deduplicate: latest TRADE_DATE row per SECURITY_CODE
    seen: Dict[str, Dict[str, Any]] = {}
    for row in all_rows:
        code = str(row.get("SECURITY_CODE", "")).strip()
        if not code or len(code) != 6 or not code.isdigit():
            continue
        if code == exclude_symbol:
            continue
        if code not in seen:
            seen[code] = row
        # (first occurrence is the latest because sort is TRADE_DATE desc)

    # Sort by market cap, take top N
    def _mcap(r: Dict[str, Any]) -> float:
        try:
            return float(r.get("TOTAL_MARKET_CAP") or 0)
        except (TypeError, ValueError):
            return 0.0

    top = sorted(seen.values(), key=_mcap, reverse=True)[:top_n]
    if not top:
        return []

    # ── Phase 2: ROE & net margin (best-effort, concurrent) ────────────
    sem = asyncio.Semaphore(8)

    async def _fetch_financials(code: str) -> Dict[str, Any]:
        """Single-company financial indicators → {roe, margin} or {}."""
        async with sem:
            try:
                def _req():
                    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
                    params = {
                        "reportName": "RPT_LICO_FN_CPD",
                        "columns": (
                            "REPORTDATE,WEIGHTAVG_ROE,TOTAL_OPERATE_INCOME,"
                            "PARENT_NETPROFIT"
                        ),
                        "filter": f'(SECURITY_CODE="{code}")',
                        "pageNumber": "1",
                        "pageSize": "5",
                        "sortColumns": "REPORTDATE",
                        "sortTypes": "-1",
                        "source": "WEB",
                        "client": "PC",
                    }
                    r = requests.get(
                        url, params=params,
                        headers={"User-Agent": UA}, timeout=12,
                    )
                    return r.json()

                data = await asyncio.to_thread(_req)
                rows = (data or {}).get("result", {}).get("data") or []
                if not rows:
                    return {}

                # Pick the latest annual (12-31) report; fall back to latest
                latest_annual = None
                for r in rows:
                    rd = str(r.get("REPORTDATE", ""))
                    if rd.endswith("-12-31"):
                        latest_annual = r
                        break
                best = latest_annual or rows[0]

                result: Dict[str, Any] = {}
                roe = best.get("WEIGHTAVG_ROE")
                if roe is not None:
                    try:
                        result["roe"] = round(float(roe), 2)
                    except (TypeError, ValueError):
                        pass

                rev = best.get("TOTAL_OPERATE_INCOME")
                np_ = best.get("PARENT_NETPROFIT")
                if rev is not None and np_ is not None:
                    try:
                        rev_f, np_f = float(rev), float(np_)
                        if rev_f > 0:
                            result["margin"] = round(np_f / rev_f * 100, 2)
                    except (TypeError, ValueError):
                        pass
                return result
            except Exception as e:
                logger.debug(
                    "[IndustryPeers] Financials fetch failed for %s: %s",
                    code, e,
                )
                return {}

    fin_results = await asyncio.gather(
        *[_fetch_financials(r["SECURITY_CODE"]) for r in top],
        return_exceptions=True,
    )

    # ── Phase 3: assemble peer dicts ────────────────────────────────────
    peers: List[Dict[str, Any]] = []
    for row, fin in zip(top, fin_results):
        if isinstance(fin, Exception):
            fin = {}
        if not isinstance(fin, dict):
            fin = {}

        try:
            mcap_raw = float(row.get("TOTAL_MARKET_CAP") or 0)
            mcap_yi = round(mcap_raw / 1e8, 1)  # 元 → 亿元
        except (TypeError, ValueError):
            mcap_yi = None

        peer: Dict[str, Any] = {
            "name": row.get("SECURITY_NAME_ABBR", ""),
            "symbol": row.get("SECURITY_CODE", ""),
            "pe": _safe_float(row.get("PE_TTM")),
            "pb": _safe_float(row.get("PB_MRQ")),
            "roe": fin.get("roe"),
            "margin": fin.get("margin"),
            "marketCap": mcap_yi,               # 亿元
            "market_cap_cny_bn": mcap_yi,       # alias for renderer _alt()
            "vs_target": None,
        }
        peers.append(peer)

    logger.info(
        "[IndustryPeers] %s: %d peers (top %d by mcap)",
        industry_name, len(peers), top_n,
    )
    return peers


def _safe_float(val: Any) -> Optional[float]:
    """Convert to float or return None (never raise)."""
    if val is None:
        return None
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


# ── Extended-metrics helpers (Part B: β / ROIC / WACC / buyback / coal) ──
def _compute_beta(stock_df, bench_df):
    """Beta of a stock vs benchmark, from aligned daily close returns."""
    if stock_df is None or bench_df is None:
        return None
    if getattr(stock_df, "empty", True) or getattr(bench_df, "empty", True):
        return None
    try:
        s = stock_df[["date", "close"]].copy()
        b = bench_df[["date", "close"]].copy()
        s["date"] = s["date"].astype(str).str[:10]
        b["date"] = b["date"].astype(str).str[:10]
        s["ret"] = s["close"].pct_change()
        b["ret"] = b["close"].pct_change()
        m = s.merge(b, on="date", suffixes=("_s", "_b")).dropna(subset=["ret_s", "ret_b"])
        if len(m) < 30:
            return None
        cov = m["ret_s"].cov(m["ret_b"])
        var = m["ret_b"].var()
        if not var:
            return None
        return float(cov / var)
    except Exception:
        return None


def _get_cn_risk_free_rate() -> float:
    """China 10Y treasury yield (decimal) as risk-free rate. Best-effort;
    falls back to 2.0% if no stable free endpoint. WACC is labeled 估算."""
    try:
        rows = _eastmoney_datacenter("RPT_BOND_CHINA_GOV10Y", columns="ALL", page_size=1)
        if rows and rows[0].get("YIELD") is not None:
            return float(rows[0]["YIELD"]) / 100.0
    except Exception:
        pass
    return 0.02


async def _fetch_buyback(code: str) -> Optional[Dict[str, Any]]:
    """Best-effort A-share share-repurchase (回购) from EastMoney F10 events.
    Degrades to None if the endpoint is unavailable (honest 数据缺失)."""
    try:
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, lambda: _eastmoney_datacenter(
            "RPT_F10_EVENT", filter_str=f'(SECURITY_CODE="{code}")',
            page_size=20, sort_columns="NOTICE_DATE", sort_types="-1"))
        if not rows:
            return None
        bbs = [r for r in rows if "回购" in str(r.get("EVENT_TITLE", ""))]
        if not bbs:
            return None
        latest = bbs[0]
        return {
            "date": str(latest.get("NOTICE_DATE", ""))[:10],
            "title": latest.get("EVENT_TITLE"),
            "amount": latest.get("REPURCHASE_AMOUNT") or latest.get("PLAN_AMOUNT"),
        }
    except Exception:
        return None


async def _fetch_coal_price() -> Optional[Dict[str, Any]]:
    """Best-effort thermal-coal spot (动力煤, 秦皇岛港 Q5500) for coal-chemical
    names. Degrades to None if no stable free endpoint (honest 数据缺失)."""
    try:
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, lambda: _eastmoney_datacenter(
            "RPT_CFL_SPOT", columns="ALL", page_size=20))
        if not rows:
            return None
        for r in rows:
            name = str(r.get("NAME", "") + str(r.get("PRODUCT_NAME", "")))
            if "动力煤" in name or "秦皇岛" in name or "Q5500" in name:
                return {"name": name, "price": r.get("PRICE"),
                        "date": str(r.get("DATE", ""))[:10], "unit": r.get("UNIT")}
        return None
    except Exception:
        return None


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
        """Fetch K-line from EastMoney push2delay (accessible from non-China IPs)."""
        url = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"
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
        self, code: str, period: str = "3mo", interval: str = "1d",
        prefix_override: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch K-line from Tencent web.ifzq API (accessible from overseas)."""
        prefix = prefix_override or _get_prefix(code)
        qt_symbol = f"{prefix}{code}"

        # Map period to day count for Tencent API
        period_days = {
            "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 3650,
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

        NOTE: Tencent API field layout differs between A-shares (sh/sz) and
        HK shares (hk). For HK stocks, vals[46] is the stock pinyin abbreviation
        (e.g. 'TENCENT'), NOT PB. PB is not directly available in the HK quote
        format, so we set it to None.
        """
        code = _clean_symbol(symbol)
        prefix = _get_prefix(code)
        qt_symbol = f"{prefix}{code}"
        is_hk = (prefix == "hk")

        def _safe_float(v: str) -> Optional[float]:
            """Safely parse a string to float, returning None on failure."""
            if not v or not v.strip():
                return None
            # Skip non-numeric values (e.g. pinyin abbreviations like 'CCTC')
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

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
                name=vals[1] if len(vals) > 1 else code,
                price=_safe_float(vals[3]) or 0,
                open=_safe_float(vals[5]) or 0,
                high=_safe_float(vals[33]) or 0,
                low=_safe_float(vals[34]) or 0,
                last_close=_safe_float(vals[4]) or 0,
                change=_safe_float(vals[31]) or 0,
                change_pct=_safe_float(vals[32]) or 0,
                volume=_safe_float(vals[36]) or 0,
                amount=(_safe_float(vals[37]) or 0) * 10000,  # 万→元
                market_cap=(_safe_float(vals[44]) or 0) * 1e8 if _safe_float(vals[44]) else None,  # 亿→元
                pe_ttm=_safe_float(vals[39]),
                # PB index differs: A-share PB at vals[46]; HK puts pinyin there instead.
                # For HK stocks, PB is not directly available in the quote format.
                pb=_safe_float(vals[46]) if not is_hk else None,
                turnover_pct=_safe_float(vals[38]),
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

        HK/US fast path: yfinance (the usual HK/US source) is rate-limited from
        datacenter IPs (2026-08 incident), so HK (5-digit) and US (alpha)
        symbols are served keylessly from Tencent quotes + EastMoney HK F10.
        """
        code = _clean_symbol(symbol)
        loop = asyncio.get_event_loop()

        result: Dict[str, Any] = {"source": self.name, "symbol": code}

        # ── HK/US fast path (Tencent + EastMoney HK; yfinance-free) ──────
        if code and (not code.isdigit() or len(code) == 5):
            try:
                tq = await fetch_tencent_quote([symbol])
                if tq:
                    q = tq[0]
                    result.update({
                        "price": q.get("price"),
                        "name": q.get("name"),
                        "marketCap": q.get("market_cap"),
                        "pe": q.get("pe"),
                        "pb": q.get("pb"),
                        "turnoverPct": q.get("change_pct"),
                    })
                    if len(code) == 5:  # HK — add financials from EastMoney
                        hk = await fetch_hk_financials(symbol, periods=16)
                        if hk:
                            r = hk[0]
                            result.update({
                                "revenue": r.get("OPERATE_INCOME"),
                                "netProfit": r.get("HOLDER_PROFIT"),
                                "netProfitGrowthYoY": r.get("HOLDER_PROFIT_YOY"),
                                "revenueGrowthYoY": r.get("OPERATE_INCOME_YOY"),
                                "roe": r.get("ROE_AVG"),
                                "grossMargin": r.get("GROSS_PROFIT_RATIO"),
                                "eps": r.get("BASIC_EPS"),
                                "industry": "HK-Share",
                            })
                            # ── Comprehensive HK F10 → report-compiler mapping ──
                            # EastMoney HK F10 (RPT_HKF10_FN_MAININDICATOR) exposes
                            # ~25 indicators; previously only 7 were mapped, so the
                            # deep-fundamentals table showed N/A for most rows on HK
                            # shares. Map everything the report compiler consumes.
                            # (Tencent's HK quote has no PB — field 46 is the pinyin
                            # abbreviation — so PB must come from PB_TTM here.)
                            if r.get("PB_TTM") is not None:
                                result["pb"] = r.get("PB_TTM")
                                result["priceToBook"] = r.get("PB_TTM")
                            if r.get("PE_TTM") is not None and result.get("pe") is None:
                                result["pe"] = r.get("PE_TTM")
                            # Margins: store as decimal fraction (matches yfinance/THS convention)
                            if r.get("NET_PROFIT_RATIO") is not None:
                                result["profitMargin"] = r.get("NET_PROFIT_RATIO") / 100.0
                            if r.get("ROA") is not None:
                                result["roa"] = r.get("ROA")
                            if r.get("DEBT_ASSET_RATIO") is not None:
                                result["debtRatio"] = r.get("DEBT_ASSET_RATIO")
                            if r.get("TOTAL_ASSETS") is not None:
                                result["totalAssets"] = r.get("TOTAL_ASSETS")
                            if r.get("TOTAL_LIABILITIES") is not None:
                                result["totalLiabilities"] = r.get("TOTAL_LIABILITIES")
                            if r.get("NETCASH_OPERATE") is not None:
                                result["operatingCashflow"] = r.get("NETCASH_OPERATE")
                            if r.get("END_CASH") is not None:
                                result["totalCash"] = r.get("END_CASH")
                            if r.get("DIVIDEND_RATE") is not None:
                                result["dividendYield"] = r.get("DIVIDEND_RATE")
                            if r.get("DPS_HKD") is not None:
                                result["dividendPerShare"] = r.get("DPS_HKD")
                            if r.get("BPS") is not None:
                                result["bvps"] = r.get("BPS")
                            # Growth aliases the report compiler understands
                            if r.get("OPERATE_INCOME_YOY") is not None:
                                result["revenueYoY"] = r.get("OPERATE_INCOME_YOY")
                                result["revenueGrowth"] = r.get("OPERATE_INCOME_YOY")
                            if r.get("HOLDER_PROFIT_YOY") is not None:
                                result["netProfitYoY"] = r.get("HOLDER_PROFIT_YOY")
                                result["netProfitGrowth"] = r.get("HOLDER_PROFIT_YOY")
                            # Market cap: F10 total market cap is raw (yuan) —
                            # overrides Tencent's 亿-unit value for consistency
                            # with the A-share path (raw yuan everywhere).
                            if r.get("TOTAL_MARKET_CAP") is not None:
                                result["marketCap"] = r.get("TOTAL_MARKET_CAP")
                            # Enterprise value ≈ market cap + total liabilities − cash
                            if (r.get("TOTAL_MARKET_CAP") is not None
                                    and r.get("TOTAL_LIABILITIES") is not None
                                    and r.get("END_CASH") is not None):
                                result["enterpriseValue"] = (
                                    r.get("TOTAL_MARKET_CAP") + r.get("TOTAL_LIABILITIES") - r.get("END_CASH")
                                )
                            # QoQ (环比) / 3-year CAGR from the F10 period series —
                            # only compare reports of the SAME frequency (e.g. two
                            # 一季报); mixing 一季报 vs 年报 would be misleading.
                            def _report_freq(typ):
                                m = re.search(r'(一季报|中报|三季报|年报)', str(typ or ""))
                                return m.group(1) if m else None
                            def _pct_change(cur, prev):
                                if cur is None or prev in (None, 0):
                                    return None
                                return round((cur - prev) / abs(prev) * 100.0, 2)
                            freq0 = _report_freq(r.get("report_type"))
                            if freq0:
                                # Same-frequency previous period → QoQ
                                prev_same = next((x for x in hk[1:] if _report_freq(x.get("report_type")) == freq0), None)
                                if prev_same is not None:
                                    if r.get("OPERATE_INCOME") is not None and prev_same.get("OPERATE_INCOME") is not None:
                                        result["revenueQoQ"] = _pct_change(r.get("OPERATE_INCOME"), prev_same.get("OPERATE_INCOME"))
                                    if r.get("HOLDER_PROFIT") is not None and prev_same.get("HOLDER_PROFIT") is not None:
                                        result["netProfitQoQ"] = _pct_change(r.get("HOLDER_PROFIT"), prev_same.get("HOLDER_PROFIT"))
                                # Same-frequency report ~3 years earlier → CAGR
                                base_date = r.get("report_date") or ""
                                for old in hk:
                                    od = old.get("report_date") or ""
                                    if od >= base_date or _report_freq(old.get("report_type")) != freq0:
                                        continue
                                    try:
                                        d0 = datetime.strptime(base_date, "%Y-%m-%d")
                                        d1 = datetime.strptime(od, "%Y-%m-%d")
                                        years = (d0 - d1).days / 365.25
                                    except (ValueError, TypeError):
                                        continue
                                    if 2.5 <= years <= 3.5:
                                        def _cagr(cur, prev):
                                            if cur is None or prev in (None, 0) or prev < 0 or cur < 0:
                                                return None
                                            return round((abs(cur / prev) ** (1.0 / years) - 1.0) * 100.0, 2)
                                        if r.get("OPERATE_INCOME") is not None and old.get("OPERATE_INCOME") is not None:
                                            result["revenueCagr3y"] = _cagr(r.get("OPERATE_INCOME"), old.get("OPERATE_INCOME"))
                                        if r.get("HOLDER_PROFIT") is not None and old.get("HOLDER_PROFIT") is not None:
                                            result["incomeCagr3y"] = _cagr(r.get("HOLDER_PROFIT"), old.get("HOLDER_PROFIT"))
                                        break

                            # ── Derived metrics (computable from F10 + quote) ──
                            # These were previously N/A; derive them so both the
                            # expert prompts and the deep-fundamentals table get values.
                            mcap = result.get("marketCap")
                            price = result.get("price")
                            rev = r.get("OPERATE_INCOME")
                            npv = r.get("HOLDER_PROFIT")
                            ta = r.get("TOTAL_ASSETS")
                            # Price-to-Sales: use TTM revenue assembled from the period
                            # series (latest quarter + last FY − same quarter last year)
                            ttm_rev = None
                            if rev is not None and freq0 and freq0 != "年报":
                                fy = next((x for x in hk if _report_freq(x.get("report_type")) == "年报"), None)
                                yoy = next((x for x in hk if _report_freq(x.get("report_type")) == freq0 and (x.get("report_date") or "") < (r.get("report_date") or "")), None)
                                if fy and yoy and fy.get("OPERATE_INCOME") is not None and yoy.get("OPERATE_INCOME") is not None:
                                    ttm_rev = rev + fy["OPERATE_INCOME"] - yoy["OPERATE_INCOME"]
                            ps_base = ttm_rev if ttm_rev else rev
                            if mcap and ps_base:
                                result["priceToSales"] = round(mcap / ps_base, 2)
                            # Payout ratio: DPS × shares / net profit (decimal, yfinance convention)
                            if mcap and price and npv and r.get("DPS_HKD") is not None and npv > 0:
                                shares = mcap / price if price else None
                                if shares:
                                    result["payoutRatio"] = round(r["DPS_HKD"] * shares / npv, 3)
                            # Asset turnover: revenue / total assets
                            if rev and ta:
                                result["assetTurnover"] = round(rev / ta, 4)
                            # ROIC ≈ NOPAT / invested capital = pre-tax×(1−25%) / (assets − cash)
                            if r.get("PRETAX_PROFIT") is not None and ta and r.get("END_CASH") is not None:
                                ic = ta - r["END_CASH"]
                                if ic > 0:
                                    result["roic"] = round(r["PRETAX_PROFIT"] * 0.75 / ic * 100.0, 2)
                            # 52-week high/low (for 股价百分位) + beta (vs HSI)
                            # from the 1y Tencent K-line — one fetch, two metrics.
                            try:
                                kdf = await self._fetch_tencent_kline(code, period="1y", interval="1d")
                                if kdf is not None and len(kdf) > 20:
                                    result["fiftyTwoWeekHigh"] = float(kdf["high"].max())
                                    result["fiftyTwoWeekLow"] = float(kdf["low"].min())
                                if kdf is not None and len(kdf) > 60 and result.get("beta") is None:
                                    bench = await self._fetch_tencent_kline("HSI", period="1y", interval="1d", prefix_override="hk")
                                    if bench is not None and len(bench) > 60:
                                        try:
                                            beta = _compute_beta(kdf, bench)
                                            if beta is not None:
                                                result["beta"] = round(float(beta), 3)
                                        except Exception:
                                            pass
                            except Exception as e2:
                                logger.debug(f"[a-stock-direct] 52w/beta failed for {code}: {e2}")
                    return result
            except Exception as e:
                logger.warning(f"[a-stock-direct] HK/US summary failed for {symbol}: {e}")
            return {**result, "error": "no tencent quote"}

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
        try:
            def _fetch_info():
                market_code = 1 if code.startswith("6") else 0
                url = "https://push2delay.eastmoney.com/api/qt/stock/get"
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

        # 4b. Dividend history (3y) — reuse confirmed EastMoney RPT_SHAREBONUS_DET
        try:
            div_hist = await fetch_a_share_dividends(code, periods=10)
            if div_hist:
                _hist, _seen = [], set()
                for d in div_hist:
                    _yr = (d.get("ex_dividend_date") or d.get("report_date") or "")[:4]
                    if _yr and _yr not in _seen:
                        _seen.add(_yr)
                        _hist.append({"year": _yr, "exDate": d.get("ex_dividend_date"),
                                      "pretaxBonusPer10": d.get("pretaxBonusPer10")})
                    if len(_hist) >= 3:
                        break
                if _hist:
                    result["dividendHistory"] = _hist
        except Exception as e:
            logger.warning(f"[{self.name}] Dividend history failed for {code}: {e}")

        # 6. Extended metrics (β / ROIC / WACC / buyback / coal) — Part B
        # 6a. Beta vs CSI300 (computed from daily returns; Tencent kline, overseas-accessible)
        try:
            _sk = await self._fetch_tencent_kline(code, period="1y", interval="1d")
            _bk = await self._fetch_tencent_kline("000300", period="1y", interval="1d", prefix_override="sh")
            _beta = _compute_beta(_sk, _bk)
            if _beta is not None:
                result["beta"] = round(_beta, 2)
        except Exception as e:
            logger.debug(f"[{self.name}] Beta failed for {code}: {type(e).__name__}")

        # 6b. ROIC & WACC (derived; report labels WACC as 估算)
        try:
            _inc = await fetch_a_share_income_items(code, periods=2)
            _bal = await fetch_a_share_balance_items(code, periods=2)
            if _inc and _bal:
                _op = _inc[0].get("operatingProfit")
                _ta = _bal[0].get("totalAssets")
                _tl = _bal[0].get("totalLiabilities")
                _cash = _bal[0].get("monetaryFunds")
                if _op is not None and _ta is not None:
                    _tax = 0.25  # 中国法定企业所得税率(近似)
                    _nopat = _op * (1 - _tax)
                    _ic = (_ta or 0) - (_cash or 0)
                    if _ic:
                        result["roic"] = round(_nopat / _ic * 100, 2)  # percent
                    _rf = await loop.run_in_executor(None, _get_cn_risk_free_rate)
                    _beta_v = result.get("beta") or 1.0
                    _re = _rf + _beta_v * 0.055  # 股权风险溢价假设 5.5%
                    _rd = 0.04
                    _eq = (_ta or 0) - (_tl or 0)
                    _v = _eq + (_tl or 0)
                    if _v:
                        result["wacc"] = round(
                            ((_eq / _v) * _re + (_tl or 0) / _v * _rd * (1 - _tax)) * 100, 2)
                        result["waccEstimated"] = True
        except Exception as e:
            logger.warning(f"[{self.name}] ROIC/WACC failed for {code}: {e}")

        # 6c. Buyback & coal price (best-effort; degrade to None → 数据缺失)
        try:
            _bb = await _fetch_buyback(code)
            if _bb:
                result["buyback"] = _bb
        except Exception:
            pass
        try:
            _coal = await _fetch_coal_price()
            if _coal:
                result["coalPrice"] = _coal
        except Exception:
            pass

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
                # Annual figures (for TTM-style ratios) — capture 2 most recent annuals
                _annual_count = 0
                for row in lrb:
                    if str(row.get("报告日", "")).endswith("1231"):
                        if _annual_count == 0:
                            result["_annualRevenue"] = row.get("营业收入")
                            result["_annualCostOfRevenue"] = row.get("营业成本")
                            _annual_count += 1
                        else:
                            result["_priorAnnualRevenue"] = row.get("营业收入")
                            break
                # Annual revenue YoY
                try:
                    _ann_rev = _to_float_safe(result.get("_annualRevenue"))
                    _prior_ann_rev = _to_float_safe(result.get("_priorAnnualRevenue"))
                    if (_ann_rev is not None and _prior_ann_rev is not None
                            and _prior_ann_rev != 0):
                        result["revenueYoY_annual"] = (_ann_rev - _prior_ann_rev) / abs(_prior_ann_rev)
                except Exception as exc_ann:
                    logger.debug(f"[{self.name}] revenueYoY_annual derivation failed for {code}: {exc_ann}")

                # --- Derived financial metrics from Sina income statement ---
                try:
                    # Interest expense (multiple possible titles)
                    interest_raw = (latest_fin.get("利息费用") or
                                    latest_fin.get("利息支出") or
                                    latest_fin.get("财务费用"))
                    interest_expense = _to_float_safe(interest_raw)

                    # Depreciation
                    depr_raw = (latest_fin.get("折旧费用") or
                                latest_fin.get("累计折旧") or
                                latest_fin.get("固定资产折旧"))
                    depreciation = _to_float_safe(depr_raw)

                    # Amortization
                    amort_raw = (latest_fin.get("摊销费用") or
                                 latest_fin.get("无形资产摊销"))
                    amortization = _to_float_safe(amort_raw)

                    # Income tax
                    tax_raw = (latest_fin.get("所得税费用") or
                               latest_fin.get("所得税"))
                    income_tax = _to_float_safe(tax_raw)

                    # Core inputs for all derivations
                    op_profit_s5 = _to_float_safe(latest_fin.get("营业利润"))
                    np_s5 = _to_float_safe(latest_fin.get("净利润"))

                    # interestCoverage = 营业利润 / 利息支出
                    if (op_profit_s5 is not None and interest_expense is not None
                            and abs(interest_expense) > 0):
                        result["interestCoverage"] = op_profit_s5 / interest_expense

                    # EBITDA
                    ebitda = 0.0
                    ebitda_count = 0
                    for comp, val in (("netProfit", np_s5), ("interest", interest_expense),
                                      ("tax", income_tax), ("depreciation", depreciation),
                                      ("amortization", amortization)):
                        if val is not None:
                            ebitda += abs(val)  # interest_expense & tax are positive expense
                            ebitda_count += 1
                    if np_s5 is not None and interest_expense is not None and income_tax is not None:
                        result["ebitda"] = ebitda

                except Exception as exc_derived:
                    logger.warning(
                        f"[{self.name}] Derived financial metrics failed for {code}: {exc_derived}"
                    )

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
                if total_assets is not None:
                    result["totalAssets"] = total_assets
                if equity is not None:
                    result["equity"] = equity
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
                # netCash (净现金) = 现金及等价物 - 有息负债. 即使公司近乎无息负债
                # (如茅台), 也应计入为一笔正的净现金, 而非因 total_debt==0 而漏算.
                if total_cash > 0:
                    result["totalCash"] = total_cash
                    result["netCash"] = total_cash - total_debt
                if total_debt > 0:
                    result["totalDebt"] = total_debt
                # Enterprise value = market cap + total debt - cash
                if market_cap and total_cash > 0:
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
            # 毛利率趋势: 用季度 grossMargin 计算 环比(QoQ) 与 同比(YoY)
            gm_rows = [q for q in qh_list if q.get("grossMargin") is not None]
            if len(gm_rows) >= 2:
                try:
                    g0, g1 = float(gm_rows[0]["grossMargin"]), float(gm_rows[1]["grossMargin"])
                    if g1 != 0:
                        result["grossMarginQoQ"] = round((g0 - g1) / abs(g1) * 100, 2)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
            if len(gm_rows) >= 5:
                try:
                    g0, g4 = float(gm_rows[0]["grossMargin"]), float(gm_rows[4]["grossMargin"])
                    if g4 != 0:
                        result["grossMarginYoY"] = round((g0 - g4) / abs(g4) * 100, 2)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to build quarterlyHistory for {code}: {e}")
            result["quarterlyHistory"] = []

        # 9. Per-share & valuation ratio derivations (no new API calls)
        #    All inputs already fetched in sections 1-8 above.
        try:
            # sharesOutstanding & netCashPerShare
            shares = _to_float_safe(result.get("sharesOutstanding") or result.get("totalShares"))
            if shares is None:
                # Fallback when EastMoney push2 (totalShares source) is geo-blocked:
                # derive total shares from market cap / price (both in CNY).
                _mc = _to_float_safe(result.get("marketCap"))
                _px = _to_float_safe(result.get("price"))
                if _mc is not None and _px is not None and _px > 0:
                    _derived = _mc / _px
                    if 1e6 < _derived < 1e13:  # sane listed-company share count
                        shares = _derived
            if shares is not None and shares > 0:
                if result.get("sharesOutstanding") is None:
                    result["sharesOutstanding"] = shares
                net_cash = _to_float_safe(result.get("netCash"))
                if net_cash is not None:
                    try:
                        result["netCashPerShare"] = net_cash / shares
                    except ZeroDivisionError:
                        pass

            # pegRatio
            pe = _to_float_safe(result.get("pe"))
            growth = _to_float_safe(result.get("netProfitGrowthYoY"))
            if pe is not None and growth is not None and growth > 0:
                result["pegRatio"] = pe / growth

            # revenueYoY_annual fallback (prefer annual-report derivation from section 5)
            if result.get("revenueYoY_annual") is None:
                rev_yoy = _to_float_safe(result.get("revenueGrowthYoY"))
                if rev_yoy is not None:
                    result["revenueYoY_annual"] = rev_yoy

            # enterpriseToEbitda (must run here because enterpriseValue is set in section 6,
            # after section 5 where ebitda is computed)
            _ev = _to_float_safe(result.get("enterpriseValue"))
            _ebitda = _to_float_safe(result.get("ebitda"))
            if _ev is not None and _ebitda is not None and _ebitda != 0:
                result["enterpriseToEbitda"] = _ev / _ebitda
        except Exception as exc_s9:
            logger.warning(
                f"[{self.name}] Section 9 derivations failed for {code}: {exc_s9}"
            )

        result["currency"] = "CNY"
        result["financialCurrency"] = "CNY"
        return result


# ---------------------------------------------------------------------------
# Intraday volume enrichment via the a-stock-analysis skill
#
# The pipeline LLM (often a weak model that cannot call tools itself) needs the
# 分时量能 (intraday volume distribution + main-force signals) that the
# a-stock-analysis skill produces. We proactively run the skill's `analyze.py`
# for A-Shares and fold the result into the analysis snapshot, where it is
# rendered into the expert prompt.
#
# The skill script is an agent artifact (not part of this repo); its path is
# configurable via A_STOCK_SKILL_SCRIPT and the enrichment degrades gracefully
# if the script is missing, times out, or returns an error. A failure here must
# never break the snapshot or the analysis job.
# ---------------------------------------------------------------------------

import os as _os
import sys as _sys
import subprocess as _subprocess
import json as _json

A_STOCK_SKILL_SCRIPT = _os.getenv(
    "A_STOCK_SKILL_SCRIPT",
    "/home/ubuntu/.agents/skills/a-stock-analysis/scripts/analyze.py",
)
# Hard cap so a hung Sina fetch can never stall the analysis job.
A_STOCK_SKILL_TIMEOUT = float(_os.getenv("A_STOCK_SKILL_TIMEOUT", "20"))


async def fetch_intraday_volume(symbol: str) -> Optional[dict]:
    """Run the a-stock-analysis skill's analyze.py to collect intraday volume
    distribution + main-force signals for an A-share `symbol` (6-digit code).

    Returns the parsed `minute_analysis` dict, or None on any failure (missing
    script, network error, parse error, non-zero exit). Best-effort only.
    """
    script = A_STOCK_SKILL_SCRIPT
    if not _os.path.isfile(script):
        logger.warning(
            "[intraday] a-stock-analysis skill script not found at %s; skipping intraday enrichment",
            script,
        )
        return None
    try:
        proc = await asyncio.to_thread(
            _subprocess.run,
            [_sys.executable, script, symbol, "--minute", "--json"],
            capture_output=True,
            text=True,
            timeout=A_STOCK_SKILL_TIMEOUT,
        )
    except Exception as exc:
        logger.warning(
            "[intraday] a-stock-analysis skill execution failed for %s: %s",
            symbol,
            exc,
        )
        return None

    if proc.returncode != 0:
        logger.warning(
            "[intraday] a-stock-analysis skill exited %d for %s: %s",
            proc.returncode,
            symbol,
            (proc.stderr or "").strip()[:300],
        )
        return None

    try:
        results = _json.loads(proc.stdout)
    except Exception as exc:
        logger.warning(
            "[intraday] failed to parse a-stock-analysis skill output for %s: %s",
            symbol,
            exc,
        )
        return None

    if not isinstance(results, list) or not results:
        return None
    first = results[0] or {}
    if first.get("error"):
        logger.warning(
            "[intraday] a-stock-analysis skill returned error for %s: %s",
            symbol,
            first.get("error"),
        )
        return None
    return first.get("minute_analysis")


# ────────────────────────────────────────────────────────────────────────────
# HK financials + Tencent quote — fallbacks for yfinance rate-limit / thsdk
# guest-account gaps (2026-08 data-source incident). See
# docs/DATA_SOURCE_AND_TOOLS_OPTIMIZATION_2026-07-08.md for the failure matrix.
# ────────────────────────────────────────────────────────────────────────────

# EastMoney HK F10 main-indicator report (annual/semi-annual HK financials).
HK_MAIN_INDICATOR_REPORT = "RPT_HKF10_FN_MAININDICATOR"

# Field map: EastMoney HK indicator → human label. Values are in the report
# currency (HKD for HK-listed issuers, unless IS_CNY_CODE=1).
HK_INDICATOR_FIELDS = [
    ("OPERATE_INCOME", "营收"),
    ("OPERATE_INCOME_YOY", "营收同比%"),
    ("HOLDER_PROFIT", "归母净利润"),
    ("HOLDER_PROFIT_YOY", "归母净利同比%"),
    ("PRETAX_PROFIT", "税前利润"),
    ("GROSS_PROFIT", "毛利润"),
    ("GROSS_PROFIT_RATIO", "毛利率%"),
    ("NET_PROFIT_RATIO", "净利率%"),
    ("BASIC_EPS", "基本每股收益"),
    ("DILUTED_EPS", "稀释每股收益"),
    ("EPS_TTM", "EPS(TTM)"),
    ("BPS", "每股净资产"),
    ("ROE_AVG", "ROE(加权)%"),
    ("ROA", "ROA%"),
    ("DEBT_ASSET_RATIO", "资产负债率%"),
    ("TOTAL_ASSETS", "总资产"),
    ("TOTAL_LIABILITIES", "总负债"),
    ("TOTAL_PARENT_EQUITY", "归母净资产"),
    ("NETCASH_OPERATE", "经营现金流净额"),
    ("END_CASH", "期末现金"),
    ("DPS_HKD", "每股派息(HKD)"),
    ("DIVIDEND_RATE", "股息率%"),
    ("PE_TTM", "PE(TTM)"),
    ("PB_TTM", "PB"),
    ("TOTAL_MARKET_CAP", "总市值"),
]


def _normalize_hk_symbol(symbol: str) -> str:
    """Normalize HK symbol → 5-digit zero-padded EastMoney code (e.g. 01888).

    Accepts: '1888', '1888.HK', 'HK1888', '01888', 'hk01888'.
    Returns '' if the symbol does not look like an HK code.
    """
    s = symbol.strip().upper()
    if s.startswith("HK"):
        s = s[2:]
    s = s.replace(".HK", "")
    s = s.replace("UHKG", "")
    if s.isdigit() and len(s) <= 5:
        return s.zfill(5)
    return ""


async def fetch_hk_financials(symbol: str, periods: int = 4) -> List[Dict[str, Any]]:
    """Fetch HK-share core financial indicators from EastMoney datacenter.

    Source: RPT_HKF10_FN_MAININDICATOR — annual/semi-annual reports (REPORT_DATE
    descending). Works from datacenter IPs where yfinance is rate-limited.

    Returns rows like:
      {"report_date": "2025-12-31", "report_type": "2025年年报",
       "OPERATE_INCOME": 18425859611.8, "HOLDER_PROFIT": 2205820400.28, ...}
    """
    code = _normalize_hk_symbol(symbol)
    if not code:
        return []
    try:
        rows = await asyncio.to_thread(
            _eastmoney_datacenter,
            HK_MAIN_INDICATOR_REPORT,
            "ALL",
            f'(SECUCODE="{code}.HK")',
            page_size=periods,
            sort_columns="REPORT_DATE",
            sort_types="-1",
        )
    except Exception as e:
        logger.warning(f"[a-stock-direct] HK financials failed for {symbol}: {e}")
        return []

    out = []
    for r in rows:
        item = {"report_date": str(r.get("REPORT_DATE", ""))[:10],
                "report_type": r.get("REPORT_TYPE", "")}
        for fkey, label in HK_INDICATOR_FIELDS:
            if r.get(fkey) is not None:
                item[fkey] = r[fkey]
        if item.get("OPERATE_INCOME") is not None or item.get("HOLDER_PROFIT") is not None:
            out.append(item)
    return out


async def fetch_tencent_quote(symbols) -> List[Dict[str, Any]]:
    """Fetch real-time quotes from Tencent Finance (qt.gtimg.cn).

    Supports A-share (sh600519/sz000858/bj), HK (hk01888) and US (usAAPL)
    symbols. Used as fallback when thsdk guest account has no HK/US data or
    yfinance is rate-limited.

    Accepts a single symbol or list; each may be '600519', '01888.HK', 'AAPL',
    'USHA600519', 'UHKG01888', 'UNQNAAPL' … Returns rows with keys:
      code, name, price, prev_close, open, high, low, volume, amount,
      change_pct, change_amt, turnover, pe, pb, market_cap, time
    """
    if isinstance(symbols, str):
        symbols = [symbols]

    qt_symbols = []
    for s in symbols:
        s = s.strip()
        up = s.upper()
        if up.startswith("USHA"):
            qt_symbols.append("sh" + up[4:])
        elif up.startswith("USZA"):
            qt_symbols.append("sz" + up[4:])
        elif up.startswith("UNQQ"):
            qt_symbols.append("us" + up[4:])
        elif up.startswith("UNYS"):
            qt_symbols.append("us" + up[4:])
        elif up.startswith("UHKG"):
            qt_symbols.append("hk" + up[4:])
        elif up.endswith(".HK") or up.startswith("HK") or (up.isdigit() and len(up) <= 5):
            qt_symbols.append("hk" + up.replace(".HK", "").replace("HK", "").zfill(5))
        elif up.isdigit() and len(up) == 6:
            prefix = "sh" if up.startswith(("6", "9")) else ("bj" if up.startswith("8") else "sz")
            qt_symbols.append(prefix + up)
        elif up.isalpha() and len(up) <= 5:
            # US ticker: Tencent uses bare 'usTICKER' (no exchange suffix —
            # 'usAAPL.OQ' returns v_pv_none_match).
            qt_symbols.append("us" + up)

    if not qt_symbols:
        return []

    url = "https://qt.gtimg.cn/q=" + ",".join(qt_symbols)
    try:
        loop = asyncio.get_event_loop()
        def _fetch():
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://gu.qq.com/",
            })
            return urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="replace")
        text = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=12)
    except Exception as e:
        logger.warning(f"[a-stock-direct] Tencent quote failed: {e}")
        return []

    out = []
    for line in text.strip().split(";"):
        line = line.strip()
        if "=" not in line:
            continue
        raw = line.split("=", 1)[1].strip().strip('"')
        if not raw:
            continue
        p = raw.split("~")
        if len(p) < 40:
            continue
        def _f(idx, scale=1.0):
            try:
                v = float(p[idx])
                return v / scale if scale != 1.0 else v
            except (ValueError, IndexError):
                return None
        out.append({
            "code": p[2],
            "name": p[1],
            "price": _f(3),
            "prev_close": _f(4),
            "open": _f(5),
            "volume": _f(6),
            "amount": _f(37),
            "high": _f(33),
            "low": _f(34),
            "change_pct": _f(32),
            "change_amt": _f(31),
            "time": p[30] if len(p) > 30 else "",
            "market_cap": _f(45),
            "pe": _f(39),
            "pb": _f(46),
        })
    return out
