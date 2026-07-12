"""
Sentiment data service: fetches real-time sentiment indicators from APIs.
- Northbound (陆股通) flows for individual stocks
- Stock comment/sentiment scores from Eastmoney
- Dragon-tiger board (龙虎榜) data
- Xueqiu/Eastmoney forum scraping via Crawl4AI
"""

import asyncio
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SentimentDataService:
    """Fetches quantitative sentiment data from API + forum scraping."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._comment_cache: Optional[Any] = None  # Full stock_comment_em DataFrame

    async def get_northbound_flow(self, symbol: str, days: int = 10) -> Dict[str, Any]:
        """Get northbound (陆股通) individual stock flow data."""
        cache_key = f"nb_{symbol}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result: Dict[str, Any] = {"symbol": symbol, "source": "陆股通个股"}
        try:
            # Remove suffix for API
            code = symbol.replace(".SH", "").replace(".SZ", "")
            df = await asyncio.to_thread(ak.stock_hsgt_individual_em, symbol=code)
            if df is not None and not df.empty:
                recent = df.tail(days)
                records = []
                for _, row in recent.iterrows():
                    records.append({
                        "date": str(row.get("持股日期", "")),
                        "close": row.get("当日收盘价"),
                        "change_pct": row.get("当日涨跌幅"),
                        "shares_held": row.get("持股数量"),
                        "market_value": row.get("持股市值"),
                        "pct_of_float": row.get("持股数量占A股百分比"),
                        "daily_change_shares": row.get("今日增持股数"),
                        "daily_change_value": row.get("今日增持资金"),
                    })
                result["data"] = records
                result["latest"] = records[-1] if records else None

                # Calculate 5-day net inflow
                last5 = recent.tail(5)
                total_inflow = last5["今日增持资金"].sum() if "今日增持资金" in last5.columns else None
                result["five_day_net_inflow"] = total_inflow
                result["five_day_trend"] = "净流入" if total_inflow and total_inflow > 0 else "净流出"
            else:
                result["data"] = []
                result["error"] = "无陆股通持股数据（可能不在沪港通/深港通名单中）"
        except Exception as e:
            result["data"] = []
            result["error"] = str(e)

        self._cache[cache_key] = result
        return result

    async def get_stock_sentiment_score(self, symbol: str) -> Dict[str, Any]:
        """Get Eastmoney comprehensive sentiment score for a stock."""
        cache_key = f"sentiment_{symbol}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result: Dict[str, Any] = {"symbol": symbol, "source": "东方财富综合评价"}
        try:
            # Load full comment table if not cached
            if self._comment_cache is None:
                self._comment_cache = await asyncio.to_thread(ak.stock_comment_em)

            if self._comment_cache is not None and not self._comment_cache.empty:
                code = symbol.replace(".SH", "").replace(".SZ", "")
                row = self._comment_cache[self._comment_cache["代码"] == code]
                if not row.empty:
                    r = row.iloc[0]
                    result["data"] = {
                        "composite_score": r.get("综合得分"),
                        "institutional_participation": r.get("机构参与度"),
                        "attention_index": r.get("关注指数"),
                        "main_cost": r.get("主力成本"),
                        "ranking": r.get("目前排名"),
                        "ranking_change": r.get("上升"),
                        "turnover_rate": r.get("换手率"),
                        "pe": r.get("市盈率"),
                        "date": str(r.get("交易日", "")),
                    }
                else:
                    result["error"] = "未找到该股票评分数据"
            else:
                result["error"] = "东方财富评分数据不可用"
        except Exception as e:
            result["error"] = str(e)

        self._cache[cache_key] = result
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
        if cache_key in self._cache:
            return self._cache[cache_key]

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
        self._cache[cache_key] = result
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
