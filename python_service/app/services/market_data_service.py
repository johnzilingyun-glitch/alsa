import asyncio
import akshare as ak
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Any

class MarketDataService:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300 # 5 minutes

    async def get_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch real-time quotes for multiple symbols using yfinance.
        """
        results = []
        try:
            # yfinance is synchronous, but we can run it in a thread pool to avoid blocking FastAPI
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: yf.download(symbols, period="1d", interval="1m", group_by='ticker', progress=False))
            
            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    
                    price = info.get("currentPrice") or info.get("regularMarketPrice")
                    prev_close = info.get("regularMarketPreviousClose")
                    
                    change = 0
                    change_percent = 0
                    if price and prev_close:
                        change = price - prev_close
                        change_percent = (change / prev_close) * 100
                    
                    results.append({
                        "symbol": symbol,
                        "name": info.get("shortName") or info.get("longName") or symbol,
                        "price": price,
                        "change": round(change, 4) if change else 0,
                        "changePercent": round(change_percent, 2) if change_percent else 0,
                        "previousClose": prev_close,
                        "marketCap": info.get("marketCap"),
                        "dividendYield": info.get("dividendYield"),
                        "dividendRate": info.get("dividendRate"),
                        "currency": info.get("currency"),
                        "marketState": info.get("marketState"),
                        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                except Exception as e:
                    print(f"Error fetching quote for {symbol}: {e}")
                    results.append({"symbol": symbol, "error": str(e)})
                    
        except Exception as e:
            print(f"Batch fetch failed: {e}")
            
        return results

    async def get_indices(self, market: str = "A-Share") -> List[Dict[str, Any]]:
        """
        Fetch major indices for a given market with specific source optimization.
        """
        try:
            loop = asyncio.get_event_loop()
            if market == "A-Share":
                # For A-Shares, AkShare (EastMoney) is far more reliable than yfinance
                try:
                    df = await loop.run_in_executor(None, lambda: ak.stock_zh_index_spot_em())
                except Exception as e:
                    print(f"AkShare index fetch failed: {e}")
                    df = None

                if df is None or df.empty:
                    # Fallback to yfinance if AkShare fails
                    return await self.get_quotes(["000001.SS", "399001.SZ", "399006.SZ"])
                
                # Filter for core indices
                targets = {
                    "上证指数": "000001.SS",
                    "深证成指": "399001.SZ",
                    "创业板指": "399006.SZ",
                    "沪深300": "000300.SS",
                    "中证500": "000905.SS", # Added CSI 500
                    "上证50": "000016.SS"
                }
                
                results = []
                # Use standard column mappings in case they vary
                col_name = "名称" if "名称" in df.columns else "name"
                col_price = "最新价" if "最新价" in df.columns else "last"
                col_change = "涨跌额" if "涨跌额" in df.columns else "change"
                col_pct = "涨跌幅" if "涨跌幅" in df.columns else "pct_change"

                for _, row in df.iterrows():
                    name = row.get(col_name)
                    if name in targets:
                        price = float(row.get(col_price) or 0)
                        change = float(row.get(col_change) or 0)
                        pct = float(row.get(col_pct) or 0)
                        
                        # In some AkShare versions, pct is already in % (e.g. 1.5), 
                        # but we should ensure it's handled consistently.
                        # Usually EM spot returns % values.
                        
                        results.append({
                            "symbol": targets[name],
                            "name": name,
                            "price": price,
                            "change": round(change, 4),
                            "changePercent": round(pct, 2),
                            "previousClose": round(price - change, 4) if price and change else 0,
                            "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                
                # Sort according to targets order
                sorted_results = []
                target_symbols = list(targets.values())
                for sym in target_symbols:
                    match = next((r for r in results if r["symbol"] == sym), None)
                    if match:
                        sorted_results.append(match)
                
                # Ensure we also include HSI for context in A-Share view if missing
                if not any(r["symbol"] == "^HSI" for r in sorted_results):
                    hsi = await self.get_quotes(["^HSI"])
                    if hsi and "error" not in hsi[0]:
                        sorted_results.append(hsi[0])
                        
                return sorted_results
            else:
                # For US and HK, yfinance is generally stable
                symbols = {
                    "HK-Share": ["^HSI", "^HSTECH", "^HSCE", "^HSCCI"],
                    "US-Share": ["^GSPC", "^IXIC", "^DJI", "^RUT", "^SOX"]
                }.get(market, ["^GSPC"])
                
                return await self.get_quotes(symbols)
                
        except Exception as e:
            print(f"Indices fetch failed for {market}: {e}")
            return []

    async def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> List[Dict[str, Any]]:
        """
        Fetch historical data for a symbol.
        """
        try:
            loop = asyncio.get_event_loop()
            ticker = yf.Ticker(symbol)
            df = await loop.run_in_executor(None, lambda: ticker.history(period=period, interval=interval))
            
            if df.empty:
                return []
                
            df = df.reset_index()
            # Convert timestamp to string
            if 'Date' in df.columns:
                df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
            elif 'Datetime' in df.columns:
                df['Datetime'] = df['Datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
                
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"History fetch failed for {symbol}: {e}")
            return []

    async def get_news(self, market: str) -> List[Dict[str, Any]]:
        """
        Fetch general market news.
        """
        try:
            if market == "A-Share":
                # Use akshare for A-Share news
                loop = asyncio.get_event_loop()
                df = await loop.run_in_executor(None, lambda: ak.stock_news_em(symbol="300750")) # Example symbol for general news
                if df.empty:
                    return []
                
                # Transform to standard format
                items = []
                for _, row in df.head(10).iterrows():
                    items.append({
                        "title": row["新闻标题"],
                        "url": row["新闻链接"],
                        "time": row["发布时间"],
                        "source": "EastMoney"
                    })
                return items
            else:
                # Use yfinance for others
                loop = asyncio.get_event_loop()
                search = await loop.run_in_executor(None, lambda: yf.search("SPY", newsCount=8))
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
            print(f"News fetch failed for {market}: {e}")
            return []

    async def get_financial_summary(self, symbol: str, market: str = "US-Share") -> Dict[str, Any]:
        """
        Fetch net profit, dividends, and other key financial indicators.
        """
        try:
            loop = asyncio.get_event_loop()
            if market == "US-Share" or symbol.startswith("^") or "=" in symbol:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                # Fetch financials for net income
                financials = await loop.run_in_executor(None, lambda: ticker.financials)
                
                net_income = {}
                if financials is not None and not financials.empty and 'Net Income' in financials.index:
                    series = financials.loc['Net Income']
                    # Convert index (dates) to strings
                    net_income = {str(k)[:10]: v for k, v in series.items()}
                
                return {
                    "marketCap": info.get("marketCap"),
                    "dividendYield": info.get("dividendYield"),
                    "dividendRate": info.get("dividendRate"),
                    "netIncomeHistory": net_income,
                    "currency": info.get("currency")
                }
            elif market == "A-Share":
                clean_symbol = symbol[:6]
                info_df = await loop.run_in_executor(None, lambda: ak.stock_individual_info_em(symbol=clean_symbol))
                info = dict(zip(info_df['item'], info_df['value']))
                
                # Fetch financial indicator for net profit and growth
                indicator_df = await loop.run_in_executor(None, lambda: ak.stock_financial_analysis_indicator_em(symbol=clean_symbol))
                
                financials = {}
                if not indicator_df.empty:
                    # columns like "净利润", "净利润同比增长率", "每股收益", etc.
                    latest = indicator_df.head(5).to_dict(orient="records")
                    financials = {
                        "history": latest,
                        "latestNetProfit": latest[0].get("净利润") if latest else None,
                        "latestGrowth": latest[0].get("净利润同比增长率") if latest else None
                    }
                
                return {
                    "marketCap": info.get("总市值"),
                    "circulatingMarketCap": info.get("流通市值"),
                    "pe": info.get("市盈率-动态"),
                    "pb": info.get("市净率"),
                    "financials": financials
                }
        except Exception as e:
            print(f"Financial summary fetch failed for {symbol}: {e}")
            return {"error": str(e)}
        return {}

# Singleton instance
market_data_service = MarketDataService()
