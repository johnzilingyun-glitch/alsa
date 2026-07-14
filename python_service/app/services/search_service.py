import os
import logging

logger = logging.getLogger(__name__)
import re
import aiohttp
from typing import List, Dict, Any
import asyncio


# Determine if we're on a China-based server (check network environment)
# China servers typically can't reach Google reliably
_IS_CHINA_SERVER = os.getenv("IS_CHINA_SERVER", "true").lower() in ("true", "1", "yes")

# Common User-Agent for HTTP requests to Chinese financial sites
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class SearchService:
    BLOCKED_SOURCE_DOMAINS = [
        "baidu.com", "baijiahao.baidu.com",
        "zhidao.baidu.com", "tieba.baidu.com", "wenku.baidu.com",
        "sogou.com", "360.cn", "so.com", "toutiao.com", "163.com",
        ]

    # Class-level flag: emit the unreachable warning only ONCE per process,
    # regardless of how many SearchService instances the app creates.
    _searxng_warned = False

    def __init__(self):
        self.max_results = 20
        # SearXNG configuration
        self._searxng_base_url = os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")
        self._searxng_timeout = 15
        self._searxng_enabled = os.getenv("SEARXNG_ENABLED", "true").lower() in ("true", "1", "yes")

    def _is_blocked_source(self, url: str) -> bool:
        return any(d in url for d in self.BLOCKED_SOURCE_DOMAINS)

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize text to defuse potential indirect prompt injection vectors."""
        if not text:
            return ""

        # 1. Defuse instruction overrides: e.g. "ignore previous instructions", "disregard instructions", etc.
        override_pattern = re.compile(
            r"\b(ignore|disregard|bypass|override)\s+(?:all\s+)?(?:previous\s+|system\s+|above\s+)?instructions\b",
            re.IGNORECASE
        )
        
        # 2. Defuse role modifications: e.g. "you are now a...", "act as a...", "acting as...", "your new role is..."
        role_pattern = re.compile(
            r"\b(you\s+are\s+now\s+(?:a|an|the)?|you\s+must\s+now\s+act\s+as\s+(?:a|an|the)?|act\s+as\s+(?:a|an|the)?|acting\s+as\s+(?:a|an|the)?|your\s+new\s+role\s+is\s+(?:a|an|the)?)\b",
            re.IGNORECASE
        )
        
        # 3. Defuse system-like instructions or bracketed developer blocks: e.g. [SYSTEM: ...] or [SYSTEM ...]
        bracket_system_pattern = re.compile(
            r"\[\s*(?:system|developer|instruction|user|assistant|prompt)\s*:.*?\]",
            re.IGNORECASE
        )
        
        # 4. Clean unbracketed "system: " or "system prompt: "
        colon_system_pattern = re.compile(
            r"\b(?:system|developer|instruction|system\s+prompt)\s*:\s*",
            re.IGNORECASE
        )

        sanitized = text
        sanitized = override_pattern.sub("[CLEANED DIRECTIVE]", sanitized)
        sanitized = role_pattern.sub("[CLEANED ROLE DIRECTIVE]", sanitized)
        sanitized = bracket_system_pattern.sub("[CLEANED DIRECTIVE]", sanitized)
        sanitized = colon_system_pattern.sub("[CLEANED DIRECTIVE]: ", sanitized)

        return sanitized

    def _sanitize_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not results:
            return []
        sanitized = []
        for r in results:
            item = dict(r)
            if "title" in item and isinstance(item["title"], str):
                item["title"] = self.sanitize_text(item["title"])
            if "content" in item and isinstance(item["content"], str):
                item["content"] = self.sanitize_text(item["content"])
            sanitized.append(item)
        return sanitized

    def _warn_searxng_unreachable(self, detail: str) -> None:
        """Emit ONE actionable warning when the configured SearXNG backend is
        unreachable, so operators notice the silent fallback (EastMoney/Sina/
        yfinance) instead of it being swallowed by the per-query `return []`."""
        if SearchService._searxng_warned:
            return
        SearchService._searxng_warned = True
        logger.warning(
            "SearXNG backend UNREACHABLE at %s (%s). Web searches will silently "
            "fall back to EastMoney/Sina/yfinance. Start SearXNG or set "
            "SEARXNG_ENABLED=false to suppress this warning.",
            self._searxng_base_url, detail,
        )

    # ────────── SearXNG ──────────
    async def _searxng_search(self, query: str, max_results: int = 10, categories: str = "general") -> List[Dict[str, Any]]:
        """Search via local SearXNG instance. Returns formatted results."""
        if not self._searxng_enabled:
            return []
        # Force engines. Baidu/sogou were previously pinned because the default
        # `general` category excluded them (Chinese queries returned 0). Now:
        #  - google: cleanest Chinese index, reached via the overseas proxy
        #    configured per-engine in settings.yml (google.com is GFW-blocked
        #    from this CN server) — this is the quality ceiling for Chinese.
        #  - sogou: kept DIRECT (no proxy) for its exclusive WeChat indexing;
        #    used as the web-search fallback behind iwencai (financial primary).
        #  - baidu: deliberately DROPPED — SEO/spam-heavy for financial queries.
        # `engines` overrides `categories` in SearXNG, so the category arg above
        # is intentionally ignored for engine selection.
        params = {
            "q": query,
            "format": "json",
            "categories": categories,
            "engines": "google,sogou",
            "language": "auto",
            "pageno": 1,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._searxng_base_url}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self._searxng_timeout)
                ) as resp:
                    if resp.status != 200:
                        self._warn_searxng_unreachable(f"HTTP {resp.status}")
                        return []
                    data = await resp.json()
        except Exception as e:
            self._warn_searxng_unreachable(str(e))
            return []

        formatted = []
        for r in data.get("results", [])[:max_results]:
            url = r.get("url", "")
            if self._is_blocked_source(url):
                continue
            formatted.append({
                "title": r.get("title", ""),
                "url": url,
                "content": r.get("content", ""),
                "source": "SearXNG"
            })
        return formatted

    # ────────── Public API ──────────
    async def quick_search(self, query: str) -> str:
        results = await self.search(query, max_results=3)
        if not results:
            return ""
        summaries = []
        for r in results:
            content = r['content'][:300] if len(r.get('content', '')) > 300 else r.get('content', '')
            summaries.append(f"Source: {r['source']}\nTitle: {r['title']}\nContent: {content}")
        return "\n\n".join(summaries)

    # ────────── Stock code detection ──────────
    _STOCK_CODE_RE = re.compile(r'\b\d{6}\b')
    _CHINESE_STOCK_KEYWORDS = re.compile(r'[沪深股涨停跌停板块煤炭白酒医药新能源]')
    _TICKER_RE = re.compile(r'\b[A-Z]{1,5}\b')  # US/HK ticker symbols

    def _is_chinese_stock_query(self, query: str) -> bool:
        """Detect if the query is about Chinese stocks (by stock code or keywords)."""
        if self._STOCK_CODE_RE.search(query):
            return True
        if self._CHINESE_STOCK_KEYWORDS.search(query):
            return True
        return False

    def _extract_stock_code(self, query: str) -> str | None:
        """Extract a 6-digit Chinese stock code from query text."""
        match = self._STOCK_CODE_RE.search(query)
        return match.group() if match else None

    def _extract_ticker(self, query: str) -> str | None:
        """Extract a potential US/HK ticker symbol from query text."""
        match = self._TICKER_RE.search(query)
        return match.group() if match else None

    # ────────── Iwencai (同花顺问财) search — China-friendly, primary source ──────────
    async def _iwencai_search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search via 同花顺问财 (Iwencai) OpenAPI. Primary source for Chinese financial queries.
        Uses news + announcement + report channels combined."""
        try:
            from .data_providers.iwencai_news import search_comprehensive
        except ImportError:
            return []

        iwencai_api_key = os.getenv("IWENCAI_API_KEY", "")
        if not iwencai_api_key:
            return []

        results = []
        try:
            data = await search_comprehensive(query)
            if data and data.get("status_code") == 0:
                items = data.get("data", [])
                for item in items[:max_results]:
                    title = item.get("title", item.get("headline", ""))
                    url = item.get("url", item.get("link", ""))
                    content = item.get("content", item.get("summary", "")) or title
                    source = item.get("source", item.get("channel", "同花顺问财"))
                    results.append({
                        "title": str(title)[:200],
                        "url": str(url) if url else "",
                        "content": str(content)[:500],
                        "source": f"Iwencai_{source}"
                    })
        except Exception as e:
            logger.warning(f"Iwencai search error: {e}")

        return results

    # ────────── EastMoney fallback (push2 API — stock data as search results) ──────────
    async def _eastmoney_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search via EastMoney push2 API. Returns stock quote/data as structured results.
        Used as fallback when web search and Iwencai are unavailable."""
        stock_code = self._extract_stock_code(query)
        if not stock_code:
            return []

        # Determine market prefix: 0=sz, 1=sh
        prefix = "0" if stock_code.startswith(("0", "3", "2")) else "1"
        secid = f"{prefix}.{stock_code}"
        em_code = f"sh{stock_code}" if prefix == "1" else f"sz{stock_code}"

        results = []

        # 1. Real-time quote via push2 API
        try:
            loop = asyncio.get_event_loop()
            def _get_quote():
                import urllib.request
                fields = "f43,f44,f45,f46,f47,f48,f50,f57,f58,f116,f117,f162,f167,f168,f169,f170,f171"
                url = f"https://push2delay.eastmoney.com/api/qt/stock/get?secid={secid}&fields={fields}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": _UA,
                    "Referer": "https://quote.eastmoney.com/",
                })
                resp = urllib.request.urlopen(req, timeout=10)
                import json
                return json.loads(resp.read())

            data = await asyncio.wait_for(loop.run_in_executor(None, _get_quote), timeout=12)
            d = (data or {}).get("data", {}) or {}
            if d:
                name = d.get("f58", "")
                price = d.get("f43", 0)
                change_pct = d.get("f170", 0)  # 涨跌幅
                change_amt = d.get("f169", 0)  # 涨跌额
                volume = d.get("f47", 0)
                amount = d.get("f48", 0)
                high = d.get("f44", 0)
                low = d.get("f45", 0)
                pe = d.get("f162", 0)
                pb = d.get("f167", 0)
                mkt_cap = d.get("f116", 0)

                title = f"{name}({stock_code}) 实时行情"
                content = (
                    f"最新价:{price} 涨跌幅:{change_pct}% 涨跌额:{change_amt} "
                    f"最高:{high} 最低:{low} 成交量:{volume} 成交额:{amount} "
                    f"总市值:{mkt_cap}亿 PE:{pe} PB:{pb}"
                )
                results.append({
                    "title": title,
                    "url": f"https://quote.eastmoney.com/{em_code}.html",
                    "content": content,
                    "source": "EastMoney"
                })
        except Exception as e:
            logger.warning(f"EastMoney quote fetch error for {stock_code}: {e}")

        # 2. Latest kline data for additional context
        if len(results) < max_results:
            try:
                loop = asyncio.get_event_loop()
                def _get_kline():
                    import urllib.request
                    url = (
                        f"https://push2delay.eastmoney.com/api/qt/stock/kline/get"
                        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
                        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                        f"&klt=101&fqt=0&end=20500101&lmt=10"
                    )
                    req = urllib.request.Request(url, headers={
                        "User-Agent": _UA,
                        "Referer": "https://quote.eastmoney.com/",
                    })
                    resp = urllib.request.urlopen(req, timeout=10)
                    import json
                    return json.loads(resp.read())

                data = await asyncio.wait_for(loop.run_in_executor(None, _get_kline), timeout=12)
                d = (data or {}).get("data", {}) or {}
                klines = d.get("klines", [])
                if klines:
                    # Format last 10 trading days as summary
                    lines = []
                    for k in klines[-10:]:
                        parts = k.split(",")
                        if len(parts) >= 11:
                            date, o, c, h, l, vol, amt = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
                            change = round((float(c) - float(o)) / float(o) * 100, 2) if float(o) != 0 else 0
                            lines.append(f"{date} O:{o} C:{c} H:{h} L:{l} V:{vol} Chg:{change}%")
                    content = " | ".join(lines[-5:])
                    results.append({
                        "title": f"{stock_code} 近期K线数据",
                        "url": f"https://quote.eastmoney.com/{em_code}.html",
                        "content": content,
                        "source": "EastMoney"
                    })
            except Exception as e:
                logger.warning(f"EastMoney kline fetch error for {stock_code}: {e}")

        return results

    # ────────── Sina fallback (Sina suggest + quotes) ──────────
    async def _sina_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search via Sina finance APIs. Uses suggest API to resolve stock names,
        then returns structured stock information."""
        results = []

        # Use Sina suggest API to resolve stock name → code
        try:
            loop = asyncio.get_event_loop()
            def _sina_suggest():
                import urllib.request
                from urllib.parse import quote
                encoded = quote(query[:50])  # Limit query length
                url = f"https://suggest3.sinajs.cn/suggest/type=11&key={encoded}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": _UA,
                    "Referer": "https://finance.sina.com.cn",
                })
                resp = urllib.request.urlopen(req, timeout=10)
                text = resp.read().decode("gbk", errors="replace")
                return text

            text = await asyncio.wait_for(loop.run_in_executor(None, _sina_suggest), timeout=12)
            # Format: var suggestvalue="name,11,code,shcode,...;name2,11,code2,...;"
            m = re.search(r'"([^"]*)"', text)
            if m:
                items = m.group(1).split(";")
                for item in items[:max_results]:
                    parts = item.split(",")
                    if len(parts) < 4 or parts[1] != "11":
                        continue
                    name, code, shcode = parts[0], parts[2], parts[3]
                    if not (len(code) == 6 and code.startswith(("6", "0", "3", "8", "4"))):
                        continue
                    prefix = "sh" if code.startswith("6") else "sz"
                    results.append({
                        "title": f"{name}({code}) — A股实时行情",
                        "url": f"https://finance.sina.com.cn/realstock/company/{prefix}{code}/nc.shtml",
                        "content": f"股票代码: {code}, 简称: {name}, 市场: A-Share, 新浪实时行情页面",
                        "source": "Sina"
                    })
        except Exception as e:
            logger.warning(f"Sina suggest error: {e}")

        # Augment with Sina quotes API for first match (richer content)
        if results:
            try:
                name = results[0]["title"].split("(")[0] if "(" in results[0]["title"] else ""
                code = self._extract_stock_code(results[0].get("title", ""))
                if not code:
                    code = self._extract_stock_code(query)
                if name and code:
                    prefix = "sh" if code.startswith("6") else "sz"
                    results[0]["content"] = (
                        f"股票代码: {code}, 简称: {name}, 市场: A-Share. "
                        f"更多信息请访问新浪财经: https://finance.sina.com.cn/realstock/company/{prefix}{code}/nc.shtml"
                    )
            except Exception:
                pass

        return results

    # ────────── Yahoo Finance fallback (global stocks) ──────────
    async def _yfinance_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search via Yahoo Finance for US/HK/global tickers. Returns company info
        and news as structured results."""
        results = []

        ticker = self._extract_ticker(query)
        if not ticker or len(ticker) < 2:
            return []

        try:
            loop = asyncio.get_event_loop()
            def _yf_lookup():
                import yfinance as yf
                out = []
                # Try direct ticker lookup
                for suffix in ["", ".HK", ".SZ", ".SS", ".T"]:
                    sym = ticker + suffix
                    try:
                        t = yf.Ticker(sym)
                        info = t.info
                        if info and info.get("shortName") and info.get("quoteType"):
                            name = info.get("shortName", "")
                            mkt = info.get("market", info.get("quoteType", ""))
                            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose", "N/A")
                            currency = info.get("currency", "")
                            out.append({
                                "title": f"{name} ({sym}) — Yahoo Finance",
                                "url": f"https://finance.yahoo.com/quote/{sym}",
                                "content": f"Symbol: {sym}, Market: {mkt}, Price: {price} {currency}, "
                                           f"Industry: {info.get('industry','')}, "
                                           f"Sector: {info.get('sector','')}, "
                                           f"Market Cap: {info.get('marketCap','')}",
                                "source": "YahooFinance"
                            })
                    except Exception:
                        continue
                return out

            items = await asyncio.wait_for(loop.run_in_executor(None, _yf_lookup), timeout=15)
            results.extend(items[:max_results])
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Yahoo Finance search error for '{ticker}': {e}")

        return results

    # ────────── MAIN SEARCH ──────────
    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search with fallback chain: Iwencai → SearXNG → EastMoney → Sina → yfinance.

        Each tier tries in order; returns as soon as any tier produces results.
        If ALL tiers fail, returns [] (but this should be rare with the fallbacks).
        """
        from .tools_config import is_skill_enabled

        if not query:
            return []

        # 1. Iwencai (primary source for Chinese financial data)
        if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
            results = await self._iwencai_search(query, max_results)
            if results:
                return self._sanitize_results(results)

        # 3. SearXNG fallback (if enabled and reachable)
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(query, max_results)
            if results:
                return self._sanitize_results(results)

        # 4. EastMoney stock data fallback (for Chinese stock code queries)
        results = await self._eastmoney_search(query, max_results)
        if results:
            return self._sanitize_results(results)

        # 5. Sina finance fallback (stock name → code resolution)
        results = await self._sina_search(query, max_results)
        if results:
            return self._sanitize_results(results)

        # 6. Yahoo Finance fallback (global tickers)
        results = await self._yfinance_search(query, max_results)
        if results:
            return self._sanitize_results(results)

        return []

    async def search_news(self, query: str, max_results: int = 10, global_only: bool = False) -> List[Dict[str, Any]]:
        """Search news with fallback chain: Iwencai → SearXNG → EastMoney → Sina → yfinance."""
        from .tools_config import is_skill_enabled

        if not query:
            return []

        if not global_only:
            # 2. Iwencai (primary source for Chinese financial news)
            if _IS_CHINA_SERVER or self._is_chinese_stock_query(query):
                results = await self._iwencai_search(query, max_results)
                if results:
                    return self._sanitize_results(results)

        # 3. SearXNG fallback (or global primary if global_only=True)
        if is_skill_enabled("searxng_backend"):
            results = await self._searxng_search(f"{query} latest news 2025", max_results, categories="news")
            if results:
                return self._sanitize_results(results)

        # 4. EastMoney stock data fallback
        results = await self._eastmoney_search(query, max_results)
        if results:
            return self._sanitize_results(results)

        # 5. Sina finance fallback
        results = await self._sina_search(query, max_results)
        if results:
            return self._sanitize_results(results)

        # 6. Yahoo Finance fallback (global tickers)
        results = await self._yfinance_search(query, max_results)
        if results:
            return self._sanitize_results(results)

        return []


search_service = SearchService()
