import asyncio
import akshare as ak
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Any
from ..utils.network import safe_ak_call
from ..utils.data_validation import validate_ak_data

class MarketDataService:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300 # 5 minutes

    async def get_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch real-time quotes for multiple symbols using yfinance.
        Handles A-Share symbol normalization (.SS/.SZ).
        """
        processed_symbols = []
        symbol_map = {}
        for s in symbols:
            if s.isdigit() and len(s) == 6:
                suffixed = f"{s}.SS" if s.startswith('6') else f"{s}.SZ"
                processed_symbols.append(suffixed)
                symbol_map[suffixed] = s
            else:
                processed_symbols.append(s)
                symbol_map[s] = s

        results = []
        try:
            loop = asyncio.get_event_loop()
            # Note: yf.download is better for batches but let's keep the ticker info logic for detail
            for ps in processed_symbols:
                try:
                    ticker = yf.Ticker(ps)
                    info = ticker.info
                    
                    price = info.get("currentPrice") or info.get("regularMarketPrice")
                    prev_close = info.get("regularMarketPreviousClose")
                    
                    change = 0
                    change_percent = 0
                    if price and prev_close:
                        change = price - prev_close
                        change_percent = (change / prev_close) * 100
                    
                    orig_symbol = symbol_map[ps]
                    results.append({
                        "symbol": orig_symbol,
                        "name": info.get("shortName") or info.get("longName") or orig_symbol,
                        "price": price,
                        "change": round(change, 4) if change else 0,
                        "changePercent": round(change_percent, 2) if change_percent else 0,
                        "previousClose": prev_close,
                        "marketCap": info.get("marketCap"),
                        "dividendYield": info.get("dividendYield"),
                        "dividendRate": info.get("dividendRate"),
                        "trailingPE": info.get("trailingPE"),
                        "forwardPE": info.get("forwardPE"),
                        "priceToBook": info.get("priceToBook"),
                        "pegRatio": info.get("pegRatio"),
                        "priceToSales": info.get("priceToSalesTrailing12Months"),
                        "enterpriseToEbitda": info.get("enterpriseToEbitda"),
                        "enterpriseValue": info.get("enterpriseValue"),
                        "returnOnEquity": info.get("returnOnEquity"),
                        "returnOnAssets": info.get("returnOnAssets"),
                        "grossMargins": info.get("grossMargins"),
                        "operatingMargins": info.get("operatingMargins"),
                        "profitMargins": info.get("profitMargins"),
                        "totalRevenue": info.get("totalRevenue"),
                        "revenueGrowth": info.get("revenueGrowth"),
                        "earningsGrowth": info.get("earningsGrowth"),
                        "eps": info.get("trailingEps"),
                        "freeCashflow": info.get("freeCashflow"),
                        "operatingCashflow": info.get("operatingCashflow"),
                        "debtToEquity": info.get("debtToEquity"),
                        "currentRatio": info.get("currentRatio"),
                        "quickRatio": info.get("quickRatio"),
                        "payoutRatio": info.get("payoutRatio"),
                        "heldPercentInsiders": info.get("heldPercentInsiders"),
                        "heldPercentInstitutions": info.get("heldPercentInstitutions"),
                        "currency": info.get("currency"),
                        "marketState": info.get("marketState"),
                        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                except Exception as e:
                    print(f"Error fetching quote for {ps}: {e}")
                    results.append({"symbol": symbol_map[ps], "error": str(e)})
                    
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
                    df = await safe_ak_call(ak.stock_zh_index_spot_em)
                except Exception as e:
                    print(f"AkShare index fetch failed: {e}")
                    df = None

                if not validate_ak_data(df, min_rows=1):
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
                try:
                    df = await safe_ak_call(ak.stock_news_em, symbol="300750")
                except:
                    df = None
                if not validate_ak_data(df, min_rows=1):
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
        cache_key = f"{market}:{symbol}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self._fetch_financial_summary(symbol, market)
        self._cache[cache_key] = result
        return result

    async def precompute_financial_summary(self, symbol: str, market: str = "US-Share") -> Dict[str, Any]:
        """
        Public method to trigger pre-computation and update cache.
        """
        result = await self._fetch_financial_summary(symbol, market)
        self._cache[f"{market}:{symbol}"] = result
        return result
    async def _fetch_financial_summary(self, symbol: str, market: str) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            if market == "US-Share" or symbol.startswith("^") or "=" in symbol:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                # Fetch financials for net income and revenue history
                financials = await loop.run_in_executor(None, lambda: ticker.financials)
                
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
                
                return {
                    "marketCap": info.get("marketCap"),
                    "dividendYield": info.get("dividendYield"),
                    "dividendRate": info.get("dividendRate"),
                    "trailingPE": info.get("trailingPE"),
                    "forwardPE": info.get("forwardPE"),
                    "priceToBook": info.get("priceToBook"),
                    "pegRatio": info.get("pegRatio"),
                    "priceToSales": info.get("priceToSalesTrailing12Months"),
                    "enterpriseToEbitda": info.get("enterpriseToEbitda"),
                    "enterpriseValue": info.get("enterpriseValue"),
                    "returnOnEquity": info.get("returnOnEquity"),
                    "returnOnAssets": info.get("returnOnAssets"),
                    "grossMargins": info.get("grossMargins"),
                    "operatingMargins": info.get("operatingMargins"),
                    "profitMargins": info.get("profitMargins"),
                    "totalRevenue": info.get("totalRevenue"),
                    "revenueGrowth": info.get("revenueGrowth"),
                    "earningsGrowth": info.get("earningsGrowth"),
                    "revenueCagr3y": revenue_cagr_3y,
                    "incomeCagr3y": income_cagr_3y,
                    "eps": info.get("trailingEps"),
                    "freeCashflow": info.get("freeCashflow"),
                    "operatingCashflow": info.get("operatingCashflow"),
                    "capitalExpenditure": info.get("capitalExpenditure"),
                    "debtToEquity": info.get("debtToEquity"),
                    "currentRatio": info.get("currentRatio"),
                    "quickRatio": info.get("quickRatio"),
                    "payoutRatio": info.get("payoutRatio"),
                    "heldPercentInsiders": info.get("heldPercentInsiders"),
                    "heldPercentInstitutions": info.get("heldPercentInstitutions"),
                    "inventoryTurnover": info.get("inventoryTurnover"),
                    "assetTurnover": info.get("assetTurnover"),
                    "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
                    "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
                    "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                    "netIncomeHistory": net_income,
                    "currency": info.get("currency")
                }
            elif market == "A-Share":
                clean_symbol = symbol[:6]
                yf_symbol = f"{clean_symbol}.SS" if clean_symbol.startswith('6') else f"{clean_symbol}.SZ"
                
                # Use yfinance as the primary source for ratios and complex metrics for A-Shares too
                # since AkShare's ratio endpoint has been unstable
                ticker = yf.Ticker(yf_symbol)
                yf_info = {}
                try:
                    yf_info = ticker.info
                except:
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
                    except:
                        pass

                ak_info = {}
                try:
                    info_df = await safe_ak_call(ak.stock_individual_info_em, symbol=clean_symbol)
                    if validate_ak_data(info_df, min_rows=1):
                        ak_info = dict(zip(info_df['item'], info_df['value']))
                except Exception as e:
                    print(f"AkShare info failed for {clean_symbol}: {e}")
                
                # Fetch financial indicator (AkShare fallback)
                ak_financials = {}
                try:
                    indicator_df = await safe_ak_call(ak.stock_financial_analysis_indicator_em, symbol=clean_symbol)
                    if validate_ak_data(indicator_df, min_rows=1):
                        latest = indicator_df.head(5).to_dict(orient="records")
                        l0 = latest[0]
                        ak_financials = {
                            "history": latest,
                            "latestNetProfit": l0.get("净利润"),
                            "latestNetProfitDeduct": l0.get("扣除非经常性损益后的净利润") or l0.get("扣非净利润"),
                            "latestGrowth": l0.get("净利润同比增长率"),
                            "latestRevenue": l0.get("营业收入"),
                            "latestRoe": l0.get("净资产收益率"),
                            "latestGrossMargin": l0.get("销售毛利率"),
                            "latestDebtRatio": l0.get("资产负债率"),
                            "latestAssetTurnover": l0.get("总资产周转率(次)") or l0.get("总资产周转率"),
                            "latestInventoryTurnover": l0.get("存货周转率(次)") or l0.get("存货周转率"),
                            "latestCurrentRatio": l0.get("流动比率"),
                            "latestQuickRatio": l0.get("速动比率"),
                            "latestCapex": l0.get("每股经营现金流(元)") # Estimate Capex if not direct
                        }
                except:
                    pass
                
                # Fetch dividend info
                latest_dividend = {}
                try:
                    dividend_df = await safe_ak_call(ak.stock_history_dividend_detail, symbol=clean_symbol)
                    latest_dividend = dividend_df.iloc[0].to_dict() if validate_ak_data(dividend_df, min_rows=1) else {}
                except:
                    pass

                # Combine data
                return {
                    "marketCap": ak_info.get("总市值") or yf_info.get("marketCap"),
                    "circulatingMarketCap": ak_info.get("流通市值"),
                    "pe": yf_info.get("trailingPE") or ak_info.get("市盈率-动态"),
                    "pb": yf_info.get("priceToBook") or ak_info.get("市净率"),
                    "pegRatio": yf_info.get("pegRatio"),
                    "priceToSales": yf_info.get("priceToSalesTrailing12Months"),
                    "enterpriseToEbitda": yf_info.get("enterpriseToEbitda"),
                    "enterpriseValue": yf_info.get("enterpriseValue"),
                    "roe": yf_info.get("returnOnEquity") or ak_financials.get("latestRoe"),
                    "roa": yf_info.get("returnOnAssets"),
                    "grossMargin": yf_info.get("grossMargins") or ak_financials.get("latestGrossMargin"),
                    "operatingMargin": yf_info.get("operatingMargins"),
                    "profitMargin": yf_info.get("profitMargins"),
                    "revenue": yf_info.get("totalRevenue") or ak_financials.get("latestRevenue"),
                    "revenueGrowth": yf_info.get("revenueGrowth") or revenue_yoy,
                    "revenueYoY": revenue_yoy,
                    "revenueQoQ": revenue_qoq,
                    "earningsGrowth": yf_info.get("earningsGrowth") or net_profit_yoy,
                    "netProfit": ak_financials.get("latestNetProfit") or yf_info.get("netIncomeToCommon"),
                    "netProfitDeduct": ak_financials.get("latestNetProfitDeduct"),
                    "netProfitYoY": net_profit_yoy or ak_financials.get("latestGrowth"),
                    "netProfitQoQ": net_profit_qoq,
                    "netProfitGrowth": ak_financials.get("latestGrowth") or net_profit_yoy,
                    "revenueCagr3y": revenue_cagr_3y,
                    "incomeCagr3y": income_cagr_3y,
                    "eps": yf_info.get("trailingEps"),
                    "debtToEquity": yf_info.get("debtToEquity"),
                    "debtRatio": ak_financials.get("latestDebtRatio"),
                    "currentRatio": ak_financials.get("latestCurrentRatio") or yf_info.get("currentRatio"),
                    "quickRatio": ak_financials.get("latestQuickRatio") or yf_info.get("quickRatio"),
                    "inventoryTurnover": ak_financials.get("latestInventoryTurnover") or yf_info.get("inventoryTurnover"),
                    "assetTurnover": ak_financials.get("latestAssetTurnover") or yf_info.get("assetTurnover"),
                    "freeCashflow": yf_info.get("freeCashflow"),
                    "operatingCashflow": ak_financials.get("latestCapex") or yf_info.get("operatingCashflow"),
                    "capitalExpenditure": yf_info.get("capitalExpenditure"),
                    "payoutRatio": yf_info.get("payoutRatio"),
                    "dividend": latest_dividend.get("派息"),
                    "dividendYield": ak_info.get("股息率") or yf_info.get("dividendYield"),
                    "heldPercentInsiders": yf_info.get("heldPercentInsiders"),
                    "heldPercentInstitutions": yf_info.get("heldPercentInstitutions"),
                    "currency": "CNY",
                    "financials": ak_financials
                }
        except Exception as e:
            print(f"Financial summary fetch failed for {symbol}: {e}")
            return {"error": str(e)}
        return {}

    def _calculate_cagr(self, series) -> float:
        try:
            if series is None or len(series) < 2: return None
            # Values are typically in reverse chronological order
            vals = series.tolist()
            if len(vals) >= 4: # 3 years difference
                start_val = vals[3]
                end_val = vals[0]
                if start_val > 0 and end_val > 0:
                    return (end_val / start_val) ** (1/3) - 1
            elif len(vals) >= 2:
                start_val = vals[-1]
                end_val = vals[0]
                years = len(vals) - 1
                if start_val > 0 and end_val > 0:
                    return (end_val / start_val) ** (1/years) - 1
        except:
            pass
        return None

# Singleton instance
market_data_service = MarketDataService()
