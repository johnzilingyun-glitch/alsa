"""
Sentiment data service: fetches real-time sentiment indicators from APIs.
- Northbound (陆股通) flows for individual stocks
- Stock comment/sentiment scores from Eastmoney
- Dragon-tiger board (龙虎榜) data
- Xueqiu/Eastmoney forum scraping via Crawl4AI
"""

import asyncio
import time
from typing import Dict, Any, Optional
import logging

import requests
import pandas as pd

logger = logging.getLogger(__name__)

# EastMoney datacenter base URL (same as AStockDirectProvider)
_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 500,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> list:
    """EastMoney datacenter unified query helper (mirrors a_stock_direct.py)."""
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
            _DATACENTER_URL, params=params,
            headers={"User-Agent": _UA}, timeout=15,
        )
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception as e:
        logger.warning(f"EastMoney datacenter error ({report_name}): {e}", exc_info=True)
    return []


class SentimentDataService:
    """Fetches quantitative sentiment data from API + forum scraping."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: int = 300  # 5 minutes, same as market_data_service
        self._comment_cache: Optional[pd.DataFrame] = None  # Full stock_comment_em DataFrame
        self._comment_cache_ts: float = 0.0  # timestamp for TTL check
        self._comment_cache_ttl: int = 3600  # comment table is large; refresh hourly

    def _cache_get(self, key: str) -> Optional[Any]:
        """Get from cache if not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts < self._cache_ttl:
            return value
        del self._cache[key]
        return None

    def _cache_set(self, key: str, value: Any) -> None:
        """Set cache entry with current timestamp."""
        self._cache[key] = (value, time.time())

    async def get_northbound_flow(self, symbol: str, days: int = 10) -> Dict[str, Any]:
        """Get northbound (陆股通) individual stock flow data.

        Uses EastMoney datacenter's RPT_MUTUAL_STOCK_NORTHSTA report
        (same data source as akshare's stock_hsgt_stock_statistics_em).
        """
        cache_key = f"nb_{symbol}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        result: Dict[str, Any] = {"symbol": symbol, "source": "陆股通个股"}
        try:
            code = symbol.replace(".SH", "").replace(".SZ", "")
            data = await asyncio.to_thread(
                lambda: _eastmoney_datacenter(
                    "RPT_MUTUAL_STOCK_NORTHSTA",
                    filter_str=f'(SECURITY_CODE="{code}")',
                    page_size=days + 10,
                    sort_columns="TRADE_DATE",
                    sort_types="-1",
                )
            )
            if data:
                records = []
                for row in data[:days]:
                    records.append({
                        "date": str(row.get("TRADE_DATE", "")),
                        "close": row.get("CLOSE_PRICE"),
                        "change_pct": row.get("CHANGE_RATE"),
                        "shares_held": row.get("HOLD_SHARES"),
                        "market_value": row.get("HOLD_MARKET_CAP"),
                        "pct_of_float": row.get("HOLD_RATIO"),
                        "daily_change_shares": row.get("ADD_SHARES"),
                        "daily_change_value": row.get("ADD_MARKET_CAP"),
                    })
                result["data"] = records
                result["latest"] = records[-1] if records else None

                # Calculate 5-day net inflow from ADD_MARKET_CAP
                recent_additions = [
                    r.get("ADD_MARKET_CAP") for r in data[:5]
                    if r.get("ADD_MARKET_CAP") is not None
                ]
                total_inflow = sum(recent_additions) if recent_additions else None
                result["five_day_net_inflow"] = total_inflow
                result["five_day_trend"] = "净流入" if total_inflow and total_inflow > 0 else "净流出"
            else:
                result["data"] = []
                result["error"] = "无陆股通持股数据（可能不在沪港通/深港通名单中）"
        except Exception as e:
            logger.error(f"Northbound flow fetch failed for {symbol}: {e}", exc_info=True)
            result["data"] = []
            result["error"] = str(e)

        self._cache_set(cache_key, result)
        return result

    async def get_stock_sentiment_score(self, symbol: str) -> Dict[str, Any]:
        """Get Eastmoney comprehensive sentiment score for a stock.

        Uses EastMoney datacenter's RPT_DMSK_TS_STOCKNEW report
        (same data source as akshare's stock_comment_em).
        """
        cache_key = f"sentiment_{symbol}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        result: Dict[str, Any] = {"symbol": symbol, "source": "东方财富综合评价"}
        try:
            # Load full comment table if not cached or TTL expired
            now = time.time()
            if self._comment_cache is None or (now - self._comment_cache_ts) > self._comment_cache_ttl:
                data = await asyncio.to_thread(
                    lambda: _eastmoney_datacenter(
                        "RPT_DMSK_TS_STOCKNEW",
                        columns="ALL",
                        page_size=500,
                    )
                )
                if data:
                    self._comment_cache = pd.DataFrame(data)
                    self._comment_cache_ts = now
                    logger.info(f"Loaded {len(data)} stock comment records from EastMoney")
                else:
                    self._comment_cache = pd.DataFrame()
                    self._comment_cache_ts = now

            if self._comment_cache is not None and not self._comment_cache.empty:
                code = symbol.replace(".SH", "").replace(".SZ", "")
                # Determine code column: if already Chinese-named, use "代码"; otherwise use "SECURITY_CODE"
                code_col = "代码" if "代码" in self._comment_cache.columns else "SECURITY_CODE"
                match = self._comment_cache[self._comment_cache[code_col] == code]
                if not match.empty:
                    r = match.iloc[0]
                    result["data"] = {
                        "composite_score": r.get("综合得分") if "综合得分" in self._comment_cache.columns else r.get("TOTAL_SCORE"),
                        "institutional_participation": r.get("机构参与度") if "机构参与度" in self._comment_cache.columns else r.get("ORG_PARTICIPATE"),
                        "attention_index": r.get("关注指数") if "关注指数" in self._comment_cache.columns else r.get("FOCUS_INDEX"),
                        "main_cost": r.get("主力成本") if "主力成本" in self._comment_cache.columns else r.get("MAIN_COST"),
                        "ranking": r.get("目前排名") if "目前排名" in self._comment_cache.columns else r.get("RANK"),
                        "ranking_change": r.get("上升") if "上升" in self._comment_cache.columns else r.get("RISE"),
                        "turnover_rate": r.get("换手率") if "换手率" in self._comment_cache.columns else r.get("TURNOVERRATE"),
                        "pe": r.get("市盈率") if "市盈率" in self._comment_cache.columns else r.get("PE_DYNAMIC"),
                        "date": str(r.get("交易日", "")) if "交易日" in self._comment_cache.columns else str(r.get("TRADE_DATE", "")),
                    }
                else:
                    result["error"] = "未找到该股票评分数据"
            else:
                result["error"] = "东方财富评分数据不可用"
        except Exception as e:
            logger.error(f"Sentiment score fetch failed for {symbol}: {e}", exc_info=True)
            result["error"] = str(e)

        self._cache_set(cache_key, result)
        return result

    def _detect_market(self, symbol: str) -> str:
        """Detect market type: 'A', 'HK', 'US'."""
        if symbol.endswith(".HK"):
            return "HK"
        if symbol.startswith(("0", "3", "6")) and len(symbol.replace(".SH", "").replace(".SZ", "")) == 6:
            return "A"
        return "US"

    async def get_forum_sentiment(self, symbol: str, name: str) -> Dict[str, Any]:
        """Scrape sentiment from financial forums using Crawl4AI.
        A-shares: 雪球 + 东方财富股吧
        US stocks: StockTwits + Reddit (wallstreetbets)
        HK stocks: 雪球 + 富途牛牛
        """
        cache_key = f"forum_{symbol}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        result: Dict[str, Any] = {"symbol": symbol, "source": "论坛情绪抓取"}
        forum_data = []
        market = self._detect_market(symbol)
        code = symbol.replace(".SH", "").replace(".SZ", "").replace(".HK", "")

        if market == "A":
            # 1. Eastmoney Guba
            try:
                guba_url = f"https://guba.eastmoney.com/list,{code}.html"
                content = await self._crawl_page(guba_url)
                if content:
                    forum_data.append({"source": "东方财富股吧", "url": guba_url, "content": content[:2000]})
            except Exception as e:
                logger.warning(f"Eastmoney Guba scrape failed: {e}")

            # 2. Xueqiu
            try:
                xq_symbol = f"SH{code}" if code.startswith("6") else f"SZ{code}"
                xueqiu_url = f"https://xueqiu.com/S/{xq_symbol}"
                content = await self._crawl_page(xueqiu_url)
                if content:
                    forum_data.append({"source": "雪球", "url": xueqiu_url, "content": content[:2000]})
            except Exception as e:
                logger.warning(f"Xueqiu scrape failed: {e}")

        elif market == "US":
            # 1. StockTwits
            try:
                ticker = symbol.upper()
                st_url = f"https://stocktwits.com/symbol/{ticker}"
                content = await self._crawl_page(st_url)
                if content:
                    forum_data.append({"source": "StockTwits", "url": st_url, "content": content[:2000]})
            except Exception as e:
                logger.warning(f"StockTwits scrape failed: {e}")

            # 2. Reddit r/wallstreetbets search
            try:
                reddit_url = f"https://www.reddit.com/r/wallstreetbets/search/?q={symbol}&sort=new&t=week"
                content = await self._crawl_page(reddit_url)
                if content:
                    forum_data.append({"source": "Reddit WSB", "url": reddit_url, "content": content[:2000]})
            except Exception as e:
                logger.warning(f"Reddit scrape failed: {e}")

            # 3. X/Twitter search (via nitter or direct)
            try:
                x_url = f"https://x.com/search?q=%24{symbol}&src=typed_query&f=live"
                content = await self._crawl_page(x_url)
                if content:
                    forum_data.append({"source": "X (Twitter)", "url": x_url, "content": content[:2000]})
            except Exception as e:
                logger.warning(f"X scrape failed: {e}")

        elif market == "HK":
            # 1. Xueqiu HK
            try:
                xueqiu_url = f"https://xueqiu.com/S/{code.zfill(5)}.HK" if len(code) < 5 else f"https://xueqiu.com/S/{code}.HK"
                content = await self._crawl_page(xueqiu_url)
                if content:
                    forum_data.append({"source": "雪球", "url": xueqiu_url, "content": content[:2000]})
            except Exception as e:
                logger.warning(f"Xueqiu HK scrape failed: {e}")

            # 2. Futu/富途牛牛
            try:
                futu_url = f"https://www.futunn.com/stock/{code.zfill(5)}-HK"
                content = await self._crawl_page(futu_url)
                if content:
                    forum_data.append({"source": "富途牛牛", "url": futu_url, "content": content[:2000]})
            except Exception as e:
                logger.warning(f"Futu scrape failed: {e}")

        result["forums"] = forum_data
        self._cache_set(cache_key, result)
        return result

    async def _crawl_page(self, url: str) -> Optional[str]:
        """Crawl a page using Crawl4AI and return markdown content."""
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

            browser_config = BrowserConfig(
                headless=True,
                text_mode=True,
                extra_args=["--disable-gpu", "--no-sandbox"],
            )
            crawl_config = CrawlerRunConfig(
                wait_until="domcontentloaded",
                page_timeout=15000,
                word_count_threshold=50,
            )

            async with AsyncWebCrawler(config=browser_config, verbose=False) as crawler:
                result = await crawler.arun(url, config=crawl_config)
                if result.success and result.markdown:
                    return result.markdown.raw_markdown[:3000]
        except Exception as e:
            logger.warning(f"Crawl4AI failed for {url}: {e}")
        return None

    async def get_all_sentiment_data(self, symbol: str, name: str) -> Dict[str, Any]:
        """Get all sentiment data for a stock in one call. Adapts by market type."""
        market = self._detect_market(symbol)

        if market == "A":
            # A-shares: northbound flow + Eastmoney score + forums
            nb_task = self.get_northbound_flow(symbol)
            score_task = self.get_stock_sentiment_score(symbol)
            nb_data, score_data = await asyncio.gather(nb_task, score_task, return_exceptions=True)
        else:
            # US/HK: no northbound flow or Eastmoney score
            nb_data = {"symbol": symbol, "data": [], "note": "非A股，无陆股通数据"}
            score_data = {"symbol": symbol, "note": "非A股，无东方财富评分"}

        # Forum scraping (all markets, with timeout)
        forum_data = {}
        try:
            forum_data = await asyncio.wait_for(
                self.get_forum_sentiment(symbol, name),
                timeout=30
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Forum sentiment timed out or failed: {e}")
            forum_data = {"symbol": symbol, "forums": [], "error": "论坛抓取超时"}

        return {
            "market": market,
            "northbound_flow": nb_data if not isinstance(nb_data, Exception) else {"error": str(nb_data)},
            "sentiment_score": score_data if not isinstance(score_data, Exception) else {"error": str(score_data)},
            "forum_sentiment": forum_data,
        }


sentiment_data_service = SentimentDataService()
