import asyncio
import json
import os
import re
import time
import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from ..utils.data_validation import validate_data
from .search_service import search_service
from .data_providers import data_router
from ..logging import get_logger

logger = get_logger(__name__)

class _CircuitBreaker:
    """Simple circuit breaker: after N failures, skip source for cooldown_seconds."""
    def __init__(self, max_failures: int = 2, cooldown_seconds: int = 300):
        self._failures: Dict[str, int] = {}
        self._open_until: Dict[str, float] = {}
        self._max_failures = max_failures
        self._cooldown = cooldown_seconds

    def record_failure(self, source: str):
        self._failures[source] = self._failures.get(source, 0) + 1
        if self._failures[source] >= self._max_failures:
            self._open_until[source] = time.time() + self._cooldown
            logger.warning("[CircuitBreaker] %s OPEN for %ss after %s failures", source, self._cooldown, self._failures[source])

    def record_success(self, source: str):
        self._failures[source] = 0
        self._open_until.pop(source, None)

    def is_open(self, source: str) -> bool:
        until = self._open_until.get(source, 0)
        if until and time.time() < until:
            return True
        return False


class MarketDataService:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300 # 5 minutes
        self._breaker = _CircuitBreaker(max_failures=2, cooldown_seconds=300)
        self.GLOBAL_INDEX_NAMES = {
            "^HSI": "恒生指数",
            "^HSTECH": "恒生科技指数",
            "^HSCE": "恒生国企指数",
            "^HSCCI": "红筹指数",
            "^GSPC": "标普500",
            "^IXIC": "纳斯达克",
            "^DJI": "道琼斯",
            "^RUT": "罗素2000",
            "^SOX": "费城半导体",
            "000001.SS": "上证指数",
            "399001.SZ": "深证成指",
            "399006.SZ": "创业板指",
            "000300.SS": "沪深300",
            "000905.SS": "中证500",
            "000016.SS": "上证50",
        }
        # yfinance 限流兑底：大宗商品新浪/腾讯直连行情映射。
        # （yfinance 对本服务器 IP 限流为常态；新浪 hf_* 外盘期货、fx_* 汇率
        #   与腾讯 us* 国际指数直连稳定，与 _fetch_indices_tencent 同源模式）
        self.COMMODITY_FALLBACK_SINA = {
            "GC=F": ("hf_GC", "future"),       # COMEX 黄金: 0=现价 7=昨结 13=名称
            "CL=F": ("hf_CL", "future"),       # WTI 原油
            "USDCNY=X": ("fx_susdcny", "fx"),  # 在岸美元/人民币: 7=现价 3=昨收 9=名称
        }
        self.COMMODITY_FALLBACK_TENCENT = {
            "^VIX": "usVIX",  # 标普500波动率指数: 1=名称 3=现价 4=昨收
        }
        # yfinance 限流兑底：大宗商品新浪/腾讯直连行情映射。
        # （yfinance 对本服务器 IP 限流为常态；新浪 hf_* 外盘期货、fx_* 汇率
        #   与腾讯 us* 国际指数直连稳定，与 _fetch_indices_tencent 同源模式）
        self.COMMODITY_FALLBACK_SINA = {
            "GC=F": ("hf_GC", "future"),       # COMEX 黄金: 0=现价 7=昨结 13=名称
            "CL=F": ("hf_CL", "future"),       # WTI 原油
            "USDCNY=X": ("fx_susdcny", "fx"),  # 在岸美元/人民币: 7=现价 3=昨收 9=名称
        }
        self.COMMODITY_FALLBACK_TENCENT = {
            "^VIX": "usVIX",  # 标普500波动率指数: 1=名称 3=现价 4=昨收
        }

    async def resolve_symbol(self, query: str, market: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Smart Recognition: Resolve a query (name or code) to a list of matching assets.
        """
        results = []

        # Resolve a stock name/code via Sina's suggest API (no akshare dependency —
        # akshare was removed; Sina covers both A-shares (type=11) and HK-shares (type=21)).
        async def _sina_suggest(q: str, type_code: str) -> List[Dict[str, Any]]:
            try:
                import urllib.request
                from urllib.parse import quote
                encoded_key = quote(q)
                url = f"https://suggest3.sinajs.cn/suggest/type={type_code}&key={encoded_key}"
                req = urllib.request.Request(url, headers={
                    "Referer": "https://finance.sina.com.cn",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                })
                resp = urllib.request.urlopen(req, timeout=10)
                text = resp.read().decode("gbk")
                # Format: var suggestvalue="name,11,code,shcode,...;name2,11,code2,...;"
                m = re.search(r'"([^"]*)"', text)
                if not m:
                    return []
                out = []
                for item in m.group(1).split(";"):
                    parts = item.split(",")
                    if len(parts) < 4 or parts[1] != type_code:
                        continue
                    name, code = parts[0], parts[2]
                    if type_code == "11":  # A-share
                        # Only Shanghai(6) and Shenzhen(0/3) are A-Share.
                        # Beijing Exchange (8xxxxx) and NEEQ (4xxxxx) are separate markets.
                        if not (len(code) == 6 and code.startswith(("6", "0", "3"))):
                            continue
                        market_label = "A-Share"
                    else:  # HK-share (type=21)
                        if not (len(code) == 5 and code.isdigit()):
                            continue
                        market_label = "HK-Share"
                    # Fuzzy match on name (contains) or exact code
                    if q in name or q == code:
                        out.append({"symbol": code, "name": name, "market": market_label})
                return out[:5]
            except Exception as e:
                logger.error("Sina suggest (%s) resolution error: %s", type_code, e)
                return []

        # 1. Check if it's already a code
        if query.isdigit():
            if len(query) == 6:
                return [{"symbol": query, "name": "A-Share Code", "market": "A-Share"}]
            if len(query) <= 5:
                return [{"symbol": query, "name": "HK-Share Code", "market": "HK-Share"}]

        # 2. A-Share name resolution (Sina type=11)
        if market is None or market == "A-Share":
            results.extend(await _sina_suggest(query, "11"))

        # 3. HK-Share name resolution (Sina type=21) — only if no A-share hit
        if not results and (market is None or market == "HK-Share"):
            results.extend(await _sina_suggest(query, "21"))

        # 4. US-Share fallback (heuristic + web search) — only if no A/HK results
        if not results and (market is None or market == "US-Share"):
            try:
                await search_service.search(f"{query} stock symbol yahoo finance", max_results=5)
            except Exception as e:
                logger.error("US-Share resolution error: %s", e)
            if query.isascii() and query.isalpha() and len(query) <= 5:
                results.append({"symbol": query.upper(), "name": query.upper(), "market": "US-Share"})

        return results

    async def get_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch real-time quotes for multiple symbols.
        For A-Shares: primary Tencent Finance path (fast, no rate limit) returns
        marketCap/trailingPE/priceToBook/turnoverRate fields that match the
        QuoteData schema from AStockDirectProvider (used by DataRouter.get_quote).
        For US/HK: uses yfinance.
        Note: This path diverges from DataRouter.get_quote which uses
        AStockDirectProvider for A-Shares; the fields returned here match
        intentionally but the provider differs.
        Handles A-Share symbol normalization (.SS/.SZ/.BJ).
        """
        processed_symbols = []
        symbol_map = {}
        for s in symbols:
            if s.isdigit() and len(s) == 6:
                # Shanghai(6xx) → .SS, Beijing(8xx) → .BJ, Shenzhen(0/3xx) → .SZ
                if s.startswith(('6', '9')):
                    suffixed = f"{s}.SS"
                elif s.startswith('8'):
                    suffixed = f"{s}.BJ"
                else:
                    suffixed = f"{s}.SZ"
                processed_symbols.append(suffixed)
                symbol_map[suffixed] = s
            elif s.isdigit() and len(s) <= 5:
                clean_s = s.lstrip('0') or '0'
                suffixed = f"{clean_s.zfill(4)}.HK"
                processed_symbols.append(suffixed)
                symbol_map[suffixed] = s
            elif s.upper().endswith('.SH') and len(s) == 9 and s[:6].isdigit():
                suffixed = f"{s[:6]}.SS"
                processed_symbols.append(suffixed)
                symbol_map[suffixed] = s
            elif s.upper().endswith('.SZ') and len(s) == 9 and s[:6].isdigit():
                suffixed = f"{s[:6]}.SZ"
                processed_symbols.append(suffixed)
                symbol_map[suffixed] = s
            elif s.upper().endswith('.SS') and len(s) == 9 and s[:6].isdigit():
                processed_symbols.append(s.upper())
                symbol_map[s.upper()] = s
            elif s.upper().endswith('.HK') and s[:-3].isdigit():
                clean_s = s[:-3].lstrip('0') or '0'
                suffixed = f"{clean_s.zfill(4)}.HK"
                processed_symbols.append(suffixed)
                symbol_map[suffixed] = s
            elif s == "^HSTECH":
                processed_symbols.append("HSTECH.HK")
                symbol_map["HSTECH.HK"] = s
            elif s == "^HSCCI":
                processed_symbols.append("^HSCC")
                symbol_map["^HSCC"] = s
            else:
                processed_symbols.append(s)
                symbol_map[s] = s

        # Pre-fetch A-share names if needed
        a_share_names = getattr(self, '_a_share_names_cache', {})

        results = []
        try:
            loop = asyncio.get_event_loop()
            import urllib.request

            def _fetch_tencent_quote(sym: str) -> Optional[Dict]:
                """Fetch a single A-Share quote from Tencent Finance (fast, no rate limit)."""
                prefix = "sh" if sym.startswith(('6', '9')) else "sz"
                url = f"http://qt.gtimg.cn/q={prefix}{sym}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=5)
                text = resp.read().decode("gbk")
                if "~" not in text:
                    return None
                parts = text.split("~")
                if len(parts) < 45:
                    return None
                price = float(parts[3]) if parts[3] else 0
                if price <= 0:
                    return None
                prev_close = float(parts[4]) if parts[4] else 0
                change = float(parts[31]) if parts[31] else 0
                change_pct = float(parts[32]) if parts[32] else 0
                return {
                    "symbol": sym,
                    "name": parts[1] or a_share_names.get(sym) or self.GLOBAL_INDEX_NAMES.get(sym, sym),
                    "price": price,
                    "change": round(change, 4),
                    "changePercent": round(change_pct, 2),
                    "previousClose": prev_close,
                    "open": float(parts[5]) if parts[5] else 0,
                    "dayHigh": float(parts[33]) if parts[33] else 0,
                    "dayLow": float(parts[34]) if parts[34] else 0,
                    "volume": float(parts[36]) if parts[36] else 0,
                    "marketCap": float(parts[44]) * 1e8 if parts[44] else None,
                    "trailingPE": float(parts[39]) if parts[39] else None,
                    "priceToBook": float(parts[46]) if parts[46] else None,
                    "turnoverRate": float(parts[38]) if parts[38] else None,
                    "currency": "CNY",
                    "lastUpdated": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST",
                }

            def fetch_single(ps):
                orig = symbol_map[ps]
                # A-Share: use Tencent (fast, reliable, no rate limit)
                if ps.endswith(".SS") or ps.endswith(".SZ") or ps.endswith(".BJ"):
                    if not self._breaker.is_open("tencent"):
                        try:
                            result = _fetch_tencent_quote(orig)
                            if result:
                                self._breaker.record_success("tencent")
                                return result
                        except Exception as e:
                            self._breaker.record_failure("tencent")
                            logger.warning("Tencent quote failed for %s: %s", orig, e)
                    # Fallback to yfinance if Tencent fails — last resort
                    if not self._breaker.is_open("yfinance"):
                        try:
                            ticker = yf.Ticker(ps)
                            info = ticker.info
                            price = info.get("currentPrice") or info.get("regularMarketPrice")
                            prev_close = info.get("regularMarketPreviousClose")
                            change = price - prev_close if price and prev_close else 0
                            change_pct = (change / prev_close * 100) if prev_close else 0
                            cn_name = a_share_names.get(orig) or self.GLOBAL_INDEX_NAMES.get(orig)
                            self._breaker.record_success("yfinance")
                            return {
                                "symbol": orig,
                                "name": cn_name or info.get("shortName") or orig,
                                "price": price,
                                "change": round(change, 4) if change else 0,
                                "changePercent": round(change_pct, 2) if change_pct else 0,
                                "previousClose": prev_close,
                                "marketCap": info.get("marketCap"),
                                "trailingPE": info.get("trailingPE"),
                                "priceToBook": info.get("priceToBook"),
                                "turnoverRate": info.get("turnoverRate"),
                                "currency": info.get("currency", "CNY"),
                                "lastUpdated": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST",
                            }
                        except Exception as e:
                            self._breaker.record_failure("yfinance")
                            logger.error("Error fetching yfinance quote for %s: %s", ps, e)
                            return {"symbol": orig, "error": str(e)}
                    else:
                        logger.warning("yfinance breaker open for %s, skipping", ps)
                        return {"symbol": orig, "error": "yfinance breaker open"}
                else:
                    # US/HK: use yfinance
                    try:
                        ticker = yf.Ticker(ps)
                        info = ticker.info
                        price = info.get("currentPrice") or info.get("regularMarketPrice")
                        prev_close = info.get("regularMarketPreviousClose")
                        change = price - prev_close if price and prev_close else 0
                        change_pct = (change / prev_close * 100) if prev_close else 0
                        cn_name = a_share_names.get(orig) or self.GLOBAL_INDEX_NAMES.get(orig)
                        return {
                            "symbol": orig,
                            "name": cn_name or info.get("shortName") or info.get("longName") or orig,
                            "price": price,
                            "change": round(change, 4) if change else 0,
                            "changePercent": round(change_pct, 2) if change_pct else 0,
                            "previousClose": prev_close,
                            "marketCap": info.get("marketCap"),
                            "trailingPE": info.get("trailingPE"),
                            "priceToBook": info.get("priceToBook"),
                            "currency": info.get("currency"),
                            "lastUpdated": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST",
                        }
                    except Exception as e:
                        logger.error("Error fetching quote for %s: %s", ps, e)
                        return {"symbol": orig, "error": str(e)}

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=30) as executor:
                blocking_tasks = [loop.run_in_executor(executor, fetch_single, ps) for ps in processed_symbols]
                results = await asyncio.gather(*blocking_tasks)

        except Exception as e:
            logger.error("Batch fetch failed: %s", e)
            
        return results

    def _fetch_commodity_fallbacks(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Sina/Tencent direct quotes for commodity symbols — yfinance 限流兑底."""
        import urllib.request
        out: Dict[str, Dict[str, Any]] = {}

        sina_map = {s: self.COMMODITY_FALLBACK_SINA[s] for s in symbols if s in self.COMMODITY_FALLBACK_SINA}
        if sina_map:
            try:
                codes = ",".join(code for code, _ in sina_map.values())
                req = urllib.request.Request(
                    f"https://hq.sinajs.cn/list={codes}",
                    headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"},
                )
                text = urllib.request.urlopen(req, timeout=6).read().decode("gbk")
                for orig, (code, kind) in sina_map.items():
                    m = re.search(rf'hq_str_{re.escape(code)}="([^"]*)"', text)
                    if not m:
                        continue
                    parts = m.group(1).split(",")
                    try:
                        if kind == "future":
                            price, prev, name = float(parts[0]), float(parts[7]), parts[13]
                        else:
                            price, prev, name = float(parts[7]), float(parts[3]), parts[9]
                    except (ValueError, IndexError):
                        continue
                    if price > 0 and prev > 0:
                        out[orig] = {
                            "symbol": orig,
                            "name": name or orig,
                            "price": price,
                            "change": round(price - prev, 4),
                            "changePercent": round((price / prev - 1) * 100, 2),
                            "previousClose": prev,
                            "currency": "CNY" if kind == "fx" else "USD",
                            "lastUpdated": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST",
                        }
            except Exception as e:
                logger.warning("Sina commodity fallback failed: %s", e)

        qt_map = {s: self.COMMODITY_FALLBACK_TENCENT[s] for s in symbols if s in self.COMMODITY_FALLBACK_TENCENT}
        if qt_map:
            try:
                codes = ",".join(qt_map.values())
                req = urllib.request.Request(
                    f"http://qt.gtimg.cn/q={codes}",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                text = urllib.request.urlopen(req, timeout=6).read().decode("gbk")
                for orig, code in qt_map.items():
                    m = re.search(rf'v_{re.escape(code)}="([^"]*)"', text)
                    if not m:
                        continue
                    parts = m.group(1).split("~")
                    if len(parts) < 5:
                        continue
                    try:
                        price, prev = float(parts[3]), float(parts[4])
                    except ValueError:
                        continue
                    if price > 0 and prev > 0:
                        out[orig] = {
                            "symbol": orig,
                            "name": parts[1] or orig,
                            "price": price,
                            "change": round(price - prev, 4),
                            "changePercent": round((price / prev - 1) * 100, 2),
                            "previousClose": prev,
                            "currency": "USD",
                            "lastUpdated": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST",
                        }
            except Exception as e:
                logger.warning("Tencent commodity fallback failed: %s", e)
        return out

    async def get_commodities(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch real-time commodity quotes and enrich each with a 30-day
        period change (change30d), computed from 1-month daily history.

        The 30-day change drives the report / live-UI "30日趋势" field.
        Previously that field fell back to the daily changePercent, so it
        never reflected an actual 30-day trend. Enrichment is best-effort:
        if history is unavailable the original quote (without change30d) is
        returned and the TypeScript layer falls back to changePercent.
        """
        quotes = await self.get_quotes(symbols)

        # yfinance 限流兑底：失败项尝试新浪/腾讯直连行情替换
        failed_syms = [q.get("symbol") for q in quotes if q.get("error")]
        if failed_syms:
            loop = asyncio.get_event_loop()
            fallbacks = await loop.run_in_executor(None, self._fetch_commodity_fallbacks, failed_syms)
            if fallbacks:
                quotes = [fallbacks.get(q.get("symbol"), q) if q.get("error") else q for q in quotes]
        loop = asyncio.get_event_loop()

        def _fetch_30d(sym: str) -> Optional[float]:
            try:
                hist = yf.Ticker(sym).history(period="1mo")
                if hist is None or len(hist) < 2:
                    return None
                closes = hist["Close"].dropna()
                if len(closes) < 2:
                    return None
                first = float(closes.iloc[0])
                last = float(closes.iloc[-1])
                if first == 0:
                    return None
                return round((last / first - 1) * 100, 2)
            except Exception as e:  # noqa: BLE001 - best-effort enrichment
                logger.warning("Commodity 30d history failed for %s: %s", sym, e)
                return None

        syms = [q.get("symbol") for q in quotes if q.get("symbol") and "error" not in q]
        if syms:
            results_30d = await asyncio.gather(
                *[loop.run_in_executor(None, _fetch_30d, s) for s in syms]
            )
            by_sym = dict(zip(syms, results_30d))
            for q in quotes:
                sym = q.get("symbol")
                chg = by_sym.get(sym) if sym else None
                if chg is not None:
                    q["change30d"] = chg
        return quotes

    async def get_indices(self, market: str = "A-Share") -> List[Dict[str, Any]]:
        """
        Fetch major indices for a given market using Tencent Finance API.
        """
        try:
            if market == "A-Share":
                return await self._fetch_indices_tencent(["000001", "399001", "399006"])
            else:
                symbols = {
                    "HK-Share": ["^HSI", "^HSTECH", "^HSCE", "^HSCCI"],
                    "US-Share": ["^GSPC", "^IXIC", "^DJI"]
                }.get(market, ["^GSPC"])
                return await self._fetch_indices_tencent(symbols)
        except Exception as e:
            logger.error("Indices fetch failed for %s: %s", market, e)
            return []

    async def _fetch_indices_tencent(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch index quotes from Tencent Finance API (fast, no rate limit)."""
        import urllib.request
        results = []
        for sym in symbols:
            # Determine prefix
            if sym.startswith("^"):
                prefix_map = {
                    "^HSI": "hkHSI", "^HSTECH": "hkHSTECH", "^HSCE": "hkHSCEI", "^HSCCI": "hkHSCCI",
                    "^GSPC": "usGSPC", "^IXIC": "usIXIC", "^DJI": "usDJI",
                }
                qt = prefix_map.get(sym, f"hk{sym[1:]}")
            elif sym.startswith("0") or sym.startswith("3"):
                prefix = "sh" if sym.startswith("0") else "sz"
                qt = f"{prefix}{sym}"
            elif sym.startswith("6"):
                qt = f"sh{sym}"
            else:
                qt = f"hk{sym}"

            try:
                url = f"http://qt.gtimg.cn/q={qt}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=5)
                text = resp.read().decode("gbk")
                if "~" not in text:
                    continue
                parts = text.split("~")
                if len(parts) < 45:
                    continue
                name = parts[1]
                price = float(parts[3]) if parts[3] else 0
                prev_close = float(parts[4]) if parts[4] else 0
                change = float(parts[31]) if parts[31] else 0
                change_pct = float(parts[32]) if parts[32] else 0
                if price > 0:
                    results.append({
                        "symbol": sym,
                        "name": name,
                        "price": price,
                        "change": round(change, 4),
                        "changePercent": round(change_pct, 2),
                        "previousClose": prev_close,
                        "lastUpdated": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST"
                    })
            except Exception as e:
                logger.error("Tencent index fetch failed for %s: %s", sym, e)
        return results

    async def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> List[Dict[str, Any]]:
        """
        Fetch historical data for a symbol via the DataRouter.
        Routes to optimal provider based on market detection.
        """
        try:
            df = await data_router.get_history(symbol, period=period, interval=interval)
            if df is not None and not df.empty:
                return df.to_dict(orient="records")
            return []
        except Exception as e:
            logger.error("History fetch failed for %s: %s", symbol, e)
            return []

    async def get_quotes_with_meta(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch quotes via DataRouter and include per-symbol route metadata.
        """
        async def _fetch_one(sym: str) -> Dict[str, Any]:
            try:
                quote, route_meta = await data_router.get_quote_with_meta(sym)
                if quote is None:
                    return {
                        "symbol": sym,
                        "error": "No data",
                        "_route_meta": route_meta,
                    }
                row = quote.to_dict()
                row["_route_meta"] = route_meta
                return row
            except Exception as e:
                return {
                    "symbol": sym,
                    "error": str(e),
                    "_route_meta": data_router.get_last_route_meta(),
                }

        tasks = [_fetch_one(s) for s in symbols]
        return await asyncio.gather(*tasks)

    async def get_history_with_meta(
        self, symbol: str, period: str = "1mo", interval: str = "1d"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Fetch historical data via DataRouter and include route metadata.
        """
        try:
            df, route_meta = await data_router.get_history_with_meta(symbol, period=period, interval=interval)
            records = df.to_dict(orient="records") if df is not None and not df.empty else []
            return records, route_meta
        except Exception as e:
            logger.error("History fetch (with meta) failed for %s: %s", symbol, e)
            return [], data_router.get_last_route_meta()

    async def get_news(self, market: str) -> List[Dict[str, Any]]:
        """
        Fetch general market news.
        """
        try:
            loop = asyncio.get_event_loop()
            if market in ["A-Share", "HK-Share"]:
                symbol = "深证成指" if market == "A-Share" else "恒生指数"
                # Direct EastMoney API call to bypass regex bug (\u3000)
                import requests as _req
                url = "https://search-api-web.eastmoney.com/search/jsonp"
                inner_param = {
                    "uid": "", "keyword": symbol,
                    "type": ["cmsArticleWebOld"], "client": "web",
                    "clientType": "web", "clientVersion": "curr",
                    "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": 10, "preTag": "", "postTag": ""}}
                }
                params = {"cb": "cb", "param": json.dumps(inner_param, ensure_ascii=False), "_": str(int(time.time()*1000))}
                headers = {"user-agent": "Mozilla/5.0", "referer": "https://so.eastmoney.com/"}
                r = await loop.run_in_executor(None, lambda: _req.get(url, params=params, headers=headers, timeout=8))
                text = r.text.strip("cb(")[:-1]
                data = json.loads(text)
                articles = data.get("result", {}).get("cmsArticleWebOld", [])
                items = []
                for a in articles[:8]:
                    items.append({
                        "title": a.get("title", "").replace("<em>", "").replace("</em>", ""),
                        "url": f"http://finance.eastmoney.com/a/{a.get('code','')}.html",
                        "time": a.get("date", ""),
                        "source": a.get("mediaName", "东方财富")
                    })
                return items
            else:
                from yfinance import Search
                search_obj = await loop.run_in_executor(None, lambda: Search("SPY"))
                search = {"news": search_obj.news or []}
                items = []
                for n in search.get("news", []):
                    items.append({
                        "title": n.get("title"),
                        "url": n.get("link"),
                        "time": datetime.fromtimestamp(n.get("providerPublishTime")).strftime("%Y-%m-%d %H:%M:%S"),
                        "source": n.get("publisher", "Yahoo Finance")
                    })
                return items
        except Exception as e:
            logger.error("News fetch failed for %s: %s", market, e)
            return []

    async def get_financial_summary(self, symbol: str, market: str = "US-Share") -> Dict[str, Any]:
        cache_key = f"{market}:{symbol}"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if isinstance(entry, dict) and "_cached_at" in entry:
                if time.time() - entry["_cached_at"] < self._cache_ttl:
                    return entry["data"]
            else:
                # Legacy cache entry (no TTL), return as-is
                return entry

        result = await self._fetch_financial_summary(symbol, market)
        self._cache[cache_key] = {"data": result, "_cached_at": time.time()}
        return result

    async def precompute_financial_summary(self, symbol: str, market: str = "US-Share") -> Dict[str, Any]:
        """
        Public method to trigger pre-computation and update cache.
        """
        result = await self._fetch_financial_summary(symbol, market)
        self._cache[f"{market}:{symbol}"] = {"data": result, "_cached_at": time.time()}
        return result
    async def _fetch_financial_summary(self, symbol: str, market: str) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            if market in ["US-Share", "HK-Share"] or symbol.startswith("^") or "=" in symbol:
                yf_symbol = symbol
                if market == "HK-Share":
                    clean_symbol = symbol.replace(".HK", "").zfill(4)
                    yf_symbol = f"{clean_symbol}.HK"
                ticker = yf.Ticker(yf_symbol)
                info = ticker.info
                
                # Fetch financials (annual + quarterly + balance sheet) for growth & turnover
                financials = await loop.run_in_executor(None, lambda: ticker.financials)
                quarterly_financials = await loop.run_in_executor(None, lambda: ticker.quarterly_financials)
                balance_sheet = await loop.run_in_executor(None, lambda: ticker.balance_sheet)
                
                net_income = {}
                revenue_cagr_3y = None
                income_cagr_3y = None
                
                if financials is not None and not financials.empty:
                    if 'Net Income' in financials.index:
                        series = financials.loc['Net Income']
                        net_income = {str(k)[:10]: v for k, v in series.items()}
                        income_cagr_3y = self._calculate_cagr(series)
                    
                    if 'Total Revenue' in financials.index:
                        rev_series = financials.loc['Total Revenue']
                        revenue_cagr_3y = self._calculate_cagr(rev_series)
                
                # QoQ / YoY from quarterly data
                revenue_qoq = None
                net_profit_qoq = None
                revenue_yoy_q = None
                net_profit_yoy_q = None
                quarterly_history_us = []
                if quarterly_financials is not None and not quarterly_financials.empty:
                    if 'Total Revenue' in quarterly_financials.index:
                        q_rev = quarterly_financials.loc['Total Revenue'].dropna()
                        if len(q_rev) >= 2 and q_rev.iloc[1] != 0:
                            revenue_qoq = (q_rev.iloc[0] - q_rev.iloc[1]) / abs(q_rev.iloc[1])
                        if len(q_rev) >= 5 and q_rev.iloc[4] != 0:
                            revenue_yoy_q = (q_rev.iloc[0] - q_rev.iloc[4]) / abs(q_rev.iloc[4])
                    if 'Net Income' in quarterly_financials.index:
                        q_ni = quarterly_financials.loc['Net Income'].dropna()
                        if len(q_ni) >= 2 and q_ni.iloc[1] != 0:
                            net_profit_qoq = (q_ni.iloc[0] - q_ni.iloc[1]) / abs(q_ni.iloc[1])
                        if len(q_ni) >= 5 and q_ni.iloc[4] != 0:
                            net_profit_yoy_q = (q_ni.iloc[0] - q_ni.iloc[4]) / abs(q_ni.iloc[4])
                    # Build quarterly history rows for prompt injection
                    all_fields = {}
                    for label in ['Total Revenue', 'Net Income', 'Gross Profit', 'Operating Income', 'EBITDA']:
                        if label in quarterly_financials.index:
                            row_data = quarterly_financials.loc[label].dropna()
                            for date_key, val in row_data.items():
                                period = str(date_key)[:10]
                                if period not in all_fields:
                                    all_fields[period] = {"period": period}
                                all_fields[period][label] = val
                    quarterly_history_us = list(all_fields.values())[:5]
                
                # --- Balance sheet: cash, debt, net cash ---
                total_cash = info.get("totalCash")
                total_debt = info.get("totalDebt")
                net_cash = None
                net_cash_per_share = None
                shares_outstanding = info.get("sharesOutstanding")
                if total_cash is not None and total_debt is not None:
                    net_cash = total_cash - total_debt
                    if shares_outstanding and shares_outstanding > 0:
                        net_cash_per_share = net_cash / shares_outstanding

                # --- Full-year (annual) revenue YoY ---
                revenue_yoy_annual = None
                if financials is not None and not financials.empty:
                    if 'Total Revenue' in financials.index:
                        ann_rev = financials.loc['Total Revenue'].dropna()
                        if len(ann_rev) >= 2 and ann_rev.iloc[1] != 0:
                            revenue_yoy_annual = (ann_rev.iloc[0] - ann_rev.iloc[1]) / abs(ann_rev.iloc[1])

                # Turnover ratios from balance sheet + income statement
                asset_turnover = None
                inventory_turnover = None
                if balance_sheet is not None and not balance_sheet.empty and financials is not None and not financials.empty:
                    try:
                        if 'Total Assets' in balance_sheet.index and 'Total Revenue' in financials.index:
                            total_assets = balance_sheet.loc['Total Assets'].iloc[0]
                            total_revenue_val = financials.loc['Total Revenue'].iloc[0]
                            if total_assets and total_assets != 0:
                                asset_turnover = total_revenue_val / total_assets
                    except Exception:
                        pass
                    try:
                        if 'Inventory' in balance_sheet.index and 'Cost Of Revenue' in financials.index:
                            inventory_val = balance_sheet.loc['Inventory'].iloc[0]
                            cogs = financials.loc['Cost Of Revenue'].iloc[0]
                            if inventory_val and inventory_val != 0:
                                inventory_turnover = cogs / inventory_val
                    except Exception:
                        pass
                
                # Search fallback for missing HK/US financials
                search_context = ""
                if not info.get("marketCap") or not info.get("totalRevenue") or not info.get("netIncomeToCommon"):
                    try:
                        # Improved query for HK/US stocks with specific missing fields
                        company_name = info.get("longName") or info.get("shortName") or symbol
                        query = f"{company_name} ({yf_symbol}) 2024 2025 financials net profit adjusted net profit Non-GAAP 扣非净利润 营收环比 QoQ growth capex"
                        search_context = await search_service.quick_search(query)
                    except Exception:
                        logger.exception("search_service.quick_search failed for %s", symbol)
                        pass
                
                # --- CAPEX from cashflow statement (fallback when info lacks it) ---
                capital_expenditure = info.get("capitalExpenditure")
                if capital_expenditure is None:
                    try:
                        cashflow = await loop.run_in_executor(None, lambda: ticker.cashflow)
                        if cashflow is not None and not cashflow.empty and 'Capital Expenditure' in cashflow.index:
                            capex_val = cashflow.loc['Capital Expenditure'].iloc[0]
                            if capex_val is not None and not (isinstance(capex_val, float) and capex_val != capex_val):
                                capital_expenditure = capex_val
                    except Exception:
                        pass

                # --- PE percentile from 2-year price history ---
                pe_percentile = None
                trailing_pe = info.get("trailingPE")
                trailing_eps = info.get("trailingEps")
                if trailing_pe and trailing_eps and trailing_eps > 0:
                    try:
                        hist = await loop.run_in_executor(None, lambda: ticker.history(period="2y"))
                        if hist is not None and len(hist) > 60:
                            hist_pe = None
                            try:
                                dates = await loop.run_in_executor(None, lambda: ticker.earnings_dates)
                                if dates is not None and not dates.empty and 'Reported EPS' in dates.columns:
                                    eps_series = dates['Reported EPS'].dropna().sort_index()
                                    if len(eps_series) >= 4:
                                        ttm_eps = eps_series.rolling(4).sum().dropna()
                                        if not ttm_eps.empty:
                                            hist_df = pd.DataFrame({'Close': hist['Close']}).sort_index()
                                            ttm_df = pd.DataFrame({'TTM_EPS': ttm_eps}).sort_index()
                                            hist_df.index = hist_df.index.tz_localize(None).astype('datetime64[ns]')
                                            ttm_df.index = ttm_df.index.tz_localize(None).astype('datetime64[ns]')
                                            merged = pd.merge_asof(hist_df, ttm_df, left_index=True, right_index=True, direction='backward')
                                            if not merged['TTM_EPS'].isna().all():
                                                hist_pe = merged['Close'] / merged['TTM_EPS']
                            except Exception as pe_err:
                                logger.debug(f"Failed to calculate rolling PE for {symbol}: {pe_err}")

                            if hist_pe is None:
                                hist_pe = hist['Close'] / trailing_eps

                            # Filter out negative/extreme PEs
                            hist_pe = hist_pe[(hist_pe > 0) & (hist_pe < 1000)]
                            if len(hist_pe) > 30:
                                pe_percentile = float((hist_pe < trailing_pe).sum()) / len(hist_pe)
                    except Exception:
                        pass

                # Detect currency mismatch for ADR/foreign stocks
                listing_currency = info.get("currency") or "USD"
                financial_currency = info.get("financialCurrency") or listing_currency
                
                # If listing and financial currencies differ (e.g. NVO: USD vs DKK),
                # yfinance's pre-computed ratios (PS, EV/EBITDA) may be wrong.
                # Recompute them using consistent units.
                price_to_sales = info.get("priceToSalesTrailing12Months")
                ev_to_ebitda = info.get("enterpriseToEbitda")
                enterprise_value = info.get("enterpriseValue")
                
                if listing_currency != financial_currency:
                    # yfinance returns EV and financial values in financialCurrency,
                    # but marketCap and price in listing currency.
                    # The pre-computed ratios mix currencies and are unreliable.
                    market_cap = info.get("marketCap")
                    total_revenue = info.get("totalRevenue")
                    ebitda = info.get("ebitda")
                    
                    # EV from yfinance may mix USD marketCap with CNY cash/debt → can be negative/wrong
                    # Recompute EV using FX rate: EV = marketCap * FX + totalDebt - totalCash
                    if enterprise_value is not None and enterprise_value < 0:
                        enterprise_value = None  # Mark unreliable — mixed currency calculation
                    
                    # If EV is None (was negative), try computing manually with FX
                    if enterprise_value is None and market_cap:
                        try:
                            fx_pair = f"{listing_currency}{financial_currency}=X"
                            fx_ticker = yf.Ticker(fx_pair)
                            fx_rate = fx_ticker.info.get("regularMarketPrice")
                            if fx_rate and fx_rate > 0:
                                mc_fc = market_cap * fx_rate  # marketCap in financialCurrency
                                td = info.get("totalDebt") or 0
                                tc = info.get("totalCash") or 0
                                ev_computed = mc_fc + td - tc
                                if ev_computed > 0:
                                    enterprise_value = ev_computed
                        except Exception:
                            pass
                    
                    price_to_sales = None  # Mark unreliable
                    ev_to_ebitda = None     # Mark unreliable
                    
                    # Recompute using ebitda (in financial_currency) and EV (in financial_currency)
                    if enterprise_value and ebitda and ebitda != 0:
                        ev_to_ebitda = enterprise_value / ebitda
                    
                    # Recompute PS using totalRevenue and enterpriseValue to infer
                    # market cap in financial_currency
                    if market_cap and total_revenue and total_revenue != 0:
                        # EV is in financial_currency from yfinance for foreign stocks
                        # We need market_cap in financial_currency too
                        # Approximate: use totalDebt and totalCash which are in financial_currency
                        total_debt_val = info.get("totalDebt") or 0
                        total_cash_val = info.get("totalCash") or 0
                        if enterprise_value:
                            # market_cap_fc = EV - debt + cash (all in financial_currency)
                            market_cap_fc = enterprise_value - total_debt_val + total_cash_val
                            if market_cap_fc > 0:
                                price_to_sales = market_cap_fc / total_revenue
                
                return {
                    "marketCap": info.get("marketCap"),
                    "dividendYield": info.get("dividendYield"),
                    "dividendRate": info.get("dividendRate"),
                    "trailingAnnualDividendYield": info.get("trailingAnnualDividendYield"),
                    "trailingPE": info.get("trailingPE"),
                    "forwardPE": info.get("forwardPE"),
                    "priceToBook": info.get("priceToBook"),
                    "pegRatio": info.get("pegRatio"),
                    "priceToSales": price_to_sales,
                    "enterpriseToEbitda": ev_to_ebitda,
                    "enterpriseValue": enterprise_value,
                    "returnOnEquity": info.get("returnOnEquity"),
                    "returnOnAssets": info.get("returnOnAssets"),
                    "grossMargins": info.get("grossMargins"),
                    "operatingMargins": info.get("operatingMargins"),
                    "profitMargins": info.get("profitMargins"),
                    "totalRevenue": info.get("totalRevenue"),
                    "revenueGrowth": info.get("revenueGrowth"),
                    "earningsGrowth": info.get("earningsGrowth"),
                    "revenueYoY": revenue_yoy_q or info.get("revenueGrowth"),
                    "netProfitYoY": net_profit_yoy_q or info.get("earningsGrowth"),
                    "revenueQoQ": revenue_qoq,
                    "netProfitQoQ": net_profit_qoq,
                    "revenueCagr3y": revenue_cagr_3y,
                    "incomeCagr3y": income_cagr_3y,
                    "eps": info.get("trailingEps"),
                    "totalCash": total_cash,
                    "totalDebt": total_debt,
                    "netCash": net_cash,
                    "netCashPerShare": net_cash_per_share,
                    "sharesOutstanding": shares_outstanding,
                    "revenueYoY_annual": revenue_yoy_annual,
                    "freeCashflow": info.get("freeCashflow"),
                    "operatingCashflow": info.get("operatingCashflow"),
                    "capitalExpenditure": capital_expenditure,
                    "debtToEquity": info.get("debtToEquity"),
                    "currentRatio": info.get("currentRatio"),
                    "quickRatio": info.get("quickRatio"),
                    "payoutRatio": info.get("payoutRatio"),
                    "heldPercentInsiders": info.get("heldPercentInsiders"),
                    "heldPercentInstitutions": info.get("heldPercentInstitutions"),
                    "inventoryTurnover": inventory_turnover or info.get("inventoryTurnover"),
                    "assetTurnover": asset_turnover or info.get("assetTurnover"),
                    "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
                    "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
                    "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                    "netIncomeHistory": net_income,
                    "currency": listing_currency,
                    "financialCurrency": financial_currency,
                    "pePercentile": pe_percentile,
                    "financials": {"searchContext": search_context},
                    "quarterlyHistory": quarterly_history_us,
                    # Company identity fields (for factual grounding)
                    "longName": info.get("longName"),
                    "industry": info.get("industry"),
                    "sector": info.get("sector"),
                    "exchange": info.get("exchange"),
                    "country": info.get("country"),
                    "longBusinessSummary": (info.get("longBusinessSummary") or "")[:500],
                }
            elif market == "A-Share":
                clean_symbol = symbol[:6]
                yf_symbol = f"{clean_symbol}.SS" if clean_symbol.startswith('6') else f"{clean_symbol}.SZ"
                
                # Use yfinance as the primary source for ratios and complex metrics for A-Shares
                ticker = yf.Ticker(yf_symbol)
                yf_info = {}
                try:
                    yf_info = ticker.info
                except Exception:
                    logger.exception("Failed to fetch yfinance ticker.info for %s", yf_symbol)
                    pass

                # Fetch financials for history
                financials_history = await loop.run_in_executor(None, lambda: ticker.financials)
                quarterly_financials = await loop.run_in_executor(None, lambda: ticker.quarterly_financials)
                
                net_income_history = {}
                revenue_cagr_3y = None
                income_cagr_3y = None
                revenue_qoq = None
                net_profit_qoq = None
                revenue_yoy = None
                net_profit_yoy = None

                if financials_history is not None and not financials_history.empty:
                    if 'Net Income' in financials_history.index:
                        series = financials_history.loc['Net Income']
                        net_income_history = {str(k)[:10]: v for k, v in series.items()}
                        income_cagr_3y = self._calculate_cagr(series)
                    if 'Total Revenue' in financials_history.index:
                        rev_series = financials_history.loc['Total Revenue']
                        revenue_cagr_3y = self._calculate_cagr(rev_series)

                if quarterly_financials is not None and not quarterly_financials.empty:
                    try:
                        if 'Total Revenue' in quarterly_financials.index:
                            q_rev = quarterly_financials.loc['Total Revenue']
                            if len(q_rev) >= 2:
                                revenue_qoq = (q_rev.iloc[0] - q_rev.iloc[1]) / abs(q_rev.iloc[1]) if q_rev.iloc[1] != 0 else None
                            if len(q_rev) >= 5:
                                revenue_yoy = (q_rev.iloc[0] - q_rev.iloc[4]) / abs(q_rev.iloc[4]) if q_rev.iloc[4] != 0 else None
                        
                        if 'Net Income' in quarterly_financials.index:
                            q_inc = quarterly_financials.loc['Net Income']
                            if len(q_inc) >= 2:
                                net_profit_qoq = (q_inc.iloc[0] - q_inc.iloc[1]) / abs(q_inc.iloc[1]) if q_inc.iloc[1] != 0 else None
                            if len(q_inc) >= 5:
                                net_profit_yoy = (q_inc.iloc[0] - q_inc.iloc[4]) / abs(q_inc.iloc[4]) if q_inc.iloc[4] != 0 else None
                    except Exception:
                        logger.exception("Failed to process quarterly financials for A-Share %s", clean_symbol)
                        pass

                # --- quarterly history rows ---
                quarterly_history_rows = []
                if quarterly_financials is not None and not quarterly_financials.empty:
                    all_fields = {}
                    for label in ['Total Revenue', 'Net Income', 'Gross Profit', 'Operating Income', 'EBITDA']:
                        if label in quarterly_financials.index:
                            row_data = quarterly_financials.loc[label].dropna()
                            for date_key, val in row_data.items():
                                period = str(date_key)[:10]
                                if period not in all_fields:
                                    all_fields[period] = {"period": period}
                                all_fields[period][label] = val
                    quarterly_history_rows = list(all_fields.values())[:5]

                # --- CAPEX from cashflow statement (fallback) ---
                a_capital_expenditure = yf_info.get("capitalExpenditure")
                if a_capital_expenditure is None:
                    try:
                        a_cashflow = await loop.run_in_executor(None, lambda: ticker.cashflow)
                        if a_cashflow is not None and not a_cashflow.empty and 'Capital Expenditure' in a_cashflow.index:
                            capex_v = a_cashflow.loc['Capital Expenditure'].iloc[0]
                            if capex_v is not None and not (isinstance(capex_v, float) and capex_v != capex_v):
                                a_capital_expenditure = capex_v
                    except Exception:
                        pass

                # --- PE percentile from 2-year history ---
                a_pe_percentile = None
                a_trailing_pe = yf_info.get("trailingPE")
                a_trailing_eps = yf_info.get("trailingEps")
                if a_trailing_pe and a_trailing_eps and a_trailing_eps > 0:
                    try:
                        a_hist = await loop.run_in_executor(None, lambda: ticker.history(period="2y"))
                        if a_hist is not None and len(a_hist) > 60:
                            a_hist_pe = None
                            try:
                                dates = await loop.run_in_executor(None, lambda: ticker.earnings_dates)
                                if dates is not None and not dates.empty and 'Reported EPS' in dates.columns:
                                    eps_series = dates['Reported EPS'].dropna().sort_index()
                                    if len(eps_series) >= 4:
                                        ttm_eps = eps_series.rolling(4).sum().dropna()
                                        if not ttm_eps.empty:
                                            hist_df = pd.DataFrame({'Close': a_hist['Close']}).sort_index()
                                            ttm_df = pd.DataFrame({'TTM_EPS': ttm_eps}).sort_index()
                                            hist_df.index = hist_df.index.tz_localize(None).astype('datetime64[ns]')
                                            ttm_df.index = ttm_df.index.tz_localize(None).astype('datetime64[ns]')
                                            merged = pd.merge_asof(hist_df, ttm_df, left_index=True, right_index=True, direction='backward')
                                            if not merged['TTM_EPS'].isna().all():
                                                a_hist_pe = merged['Close'] / merged['TTM_EPS']
                            except Exception as pe_err:
                                logger.debug(f"Failed to calculate rolling PE for {symbol}: {pe_err}")

                            if a_hist_pe is None:
                                a_hist_pe = a_hist['Close'] / a_trailing_eps

                            a_hist_pe = a_hist_pe[(a_hist_pe > 0) & (a_hist_pe < 1000)]
                            if len(a_hist_pe) > 30:
                                a_pe_percentile = float((a_hist_pe < a_trailing_pe).sum()) / len(a_hist_pe)
                    except Exception:
                        pass

                # --- Enhance cash/debt/netCash via AStockDirectProvider (reliable A-Share source) ---
                # yfinance lacks balance-sheet cash/debt for A-Share (.SS/.SZ) → netCash was always
                # None. Reuse the SAME provider the report/snapshot path uses (data_router._a_stock_primary)
                # so comprehensive_financials matches the HTML report. Handles zero-debt names (e.g. 茅台)
                # where netCash should be a positive amount, not skipped.
                _a_cash_debt = {}
                _a_ownership = {}
                try:
                    from .data_providers import data_router
                    a_provider = data_router._a_stock_primary
                    a_summary = await a_provider.get_financial_summary(symbol)
                    if a_summary and "error" not in a_summary:
                        _a_cash_debt = {
                            "totalCash": a_summary.get("totalCash"),
                            "totalDebt": a_summary.get("totalDebt"),
                            "netCash": a_summary.get("netCash"),
                            "netCashPerShare": a_summary.get("netCashPerShare"),
                            "enterpriseValue": a_summary.get("enterpriseValue") or yf_info.get("enterpriseValue"),
                        }
                        # A-share-native ownership (EastMoney F10): correct institutional
                        # %, real top-10 circulating holders. yfinance heldPercent* is
                        # meaningless for A-shares and was the source of the 100x distortion.
                        _a_ownership = {
                            "heldPercentInsiders": a_summary.get("heldPercentInsiders"),
                            "heldPercentInstitutions": a_summary.get("heldPercentInstitutions"),
                            "topCirculatingHolders": a_summary.get("topCirculatingHolders"),
                        }
                    else:
                        logger.warning("AStockDirectProvider returned error/empty for A-Share %s in comprehensive_financials; falling back to yfinance", symbol)
                        _a_ownership = {}
                except Exception as e:
                    logger.warning("AStockDirectProvider financial summary failed for A-Share %s in comprehensive_financials: %s", symbol, e)

                # Combine data
                return {
                    "marketCap": yf_info.get("marketCap"),
                    "circulatingMarketCap": None,
                    "pe": yf_info.get("trailingPE"),
                    "pb": yf_info.get("priceToBook"),
                    "pegRatio": yf_info.get("pegRatio"),
                    "priceToSales": yf_info.get("priceToSalesTrailing12Months"),
                    "enterpriseToEbitda": yf_info.get("enterpriseToEbitda"),
                    "enterpriseValue": _a_cash_debt.get("enterpriseValue", yf_info.get("enterpriseValue")),
                    "roe": yf_info.get("returnOnEquity"),
                    "roa": yf_info.get("returnOnAssets"),
                    "grossMargin": yf_info.get("grossMargins"),
                    "operatingMargin": yf_info.get("operatingMargins"),
                    "profitMargin": yf_info.get("profitMargins"),
                    "revenue": yf_info.get("totalRevenue"),
                    "revenueGrowth": yf_info.get("revenueGrowth") or revenue_yoy,
                    "revenueYoY": revenue_yoy,
                    "revenueQoQ": revenue_qoq,
                    "earningsGrowth": yf_info.get("earningsGrowth") or net_profit_yoy,
                    "netProfit": yf_info.get("netIncomeToCommon"),
                    "netProfitDeduct": None,
                    "netProfitYoY": net_profit_yoy,
                    "netProfitQoQ": net_profit_qoq,
                    "netProfitDeductYoY": None,
                    "netProfitDeductQoQ": None,
                    "netProfitGrowth": net_profit_yoy,
                    "revenueCagr3y": revenue_cagr_3y,
                    "incomeCagr3y": income_cagr_3y,
                    "eps": yf_info.get("trailingEps"),
                    "debtToEquity": yf_info.get("debtToEquity"),
                    "debtRatio": None,
                    "currentRatio": yf_info.get("currentRatio"),
                    "quickRatio": yf_info.get("quickRatio"),
                    "inventoryTurnover": yf_info.get("inventoryTurnover"),
                    "assetTurnover": yf_info.get("assetTurnover"),
                    "freeCashflow": yf_info.get("freeCashflow"),
                    "operatingCashflow": yf_info.get("operatingCashflow"),
                    "capitalExpenditure": a_capital_expenditure,
                    "totalCash": _a_cash_debt.get("totalCash"),
                    "totalDebt": _a_cash_debt.get("totalDebt"),
                    "netCash": _a_cash_debt.get("netCash"),
                    "netCashPerShare": _a_cash_debt.get("netCashPerShare"),
                    "payoutRatio": yf_info.get("payoutRatio"),
                    "dividend": None,
                    "dividendYield": yf_info.get("dividendYield"),
                    "heldPercentInsiders": _a_ownership.get("heldPercentInsiders", yf_info.get("heldPercentInsiders")),
                    "heldPercentInstitutions": _a_ownership.get("heldPercentInstitutions", yf_info.get("heldPercentInstitutions")),
                    "topCirculatingHolders": _a_ownership.get("topCirculatingHolders"),
                    "fiftyTwoWeekHigh": yf_info.get("fiftyTwoWeekHigh"),
                    "fiftyTwoWeekLow": yf_info.get("fiftyTwoWeekLow"),
                    "price": yf_info.get("currentPrice") or yf_info.get("regularMarketPrice"),
                    "currency": "CNY",
                    "financialCurrency": "CNY",
                    "pePercentile": a_pe_percentile,
                    "financials": {},
                    "quarterlyHistory": quarterly_history_rows,
                    # Company identity fields (for factual grounding)
                    "longName": yf_info.get("longName"),
                    "industry": yf_info.get("industry"),
                    "sector": yf_info.get("sector"),
                    "exchange": yf_info.get("exchange"),
                    "listingDate": None,
                    "longBusinessSummary": (yf_info.get("longBusinessSummary") or "")[:500],
                }
        except Exception as e:
            logger.error("Financial summary fetch failed for %s: %s", symbol, e)
            return {"error": str(e)}
        return {}

    @staticmethod
    def _parse_cn_number(s: str) -> float | None:
        """Parse Chinese number strings like '42.76亿', '3200万', '1.2万亿' to float."""
        if not s or s in ("False", "None", "--", ""):
            return None
        s = s.strip().replace(",", "").replace("，", "")
        multiplier = 1
        if "万亿" in s:
            multiplier = 1e12
            s = s.replace("万亿", "")
        elif "亿" in s:
            multiplier = 1e8
            s = s.replace("亿", "")
        elif "万" in s:
            multiplier = 1e4
            s = s.replace("万", "")
        try:
            return float(s) * multiplier
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_cn_percent(s: str) -> float | None:
        """Parse Chinese percent strings like '83.56%' to decimal (0.8356)."""
        if not s or s in ("False", "None", "--", ""):
            return None
        s = s.strip().replace("%", "").replace("％", "")
        try:
            return float(s) / 100.0
        except (ValueError, TypeError):
            return None

    def _compute_ev_with_fx(self, info: dict):
        """Compute Enterprise Value, using FX conversion for cross-currency ADRs."""
        ev = info.get("enterpriseValue")
        listing_currency = info.get("currency") or "USD"
        financial_currency = info.get("financialCurrency") or listing_currency
        
        # Same currency → use raw value
        if listing_currency == financial_currency:
            return ev
        
        # Cross-currency: if EV is positive, use it
        if ev is not None and ev >= 0:
            return ev
        
        # EV is negative or None → recompute via FX
        market_cap = info.get("marketCap")
        if not market_cap:
            return None
        try:
            fx_pair = f"{listing_currency}{financial_currency}=X"
            fx_ticker = yf.Ticker(fx_pair)
            fx_rate = fx_ticker.info.get("regularMarketPrice")
            if fx_rate and fx_rate > 0:
                mc_fc = market_cap * fx_rate
                td = info.get("totalDebt") or 0
                tc = info.get("totalCash") or 0
                ev_computed = mc_fc + td - tc
                return ev_computed if ev_computed > 0 else None
        except Exception:
            pass
        return None

    def _calculate_cagr(self, series) -> float:
        try:
            if series is None or len(series) < 2: return None
            vals = series.tolist()
            if len(vals) >= 4:
                start_val, end_val, years = vals[3], vals[0], 3
            else:
                start_val, end_val, years = vals[-1], vals[0], len(vals) - 1
            
            if start_val > 0 and end_val > 0:
                return (end_val / start_val) ** (1/years) - 1
            # Handle negative→positive (turnaround): use absolute values and flag as positive growth
            if start_val < 0 and end_val > 0:
                return (end_val / abs(start_val)) ** (1/years) - 1
        except Exception:
            logger.exception("Failed to calculate CAGR")
            pass
        return None

# Singleton instance
market_data_service = MarketDataService()
