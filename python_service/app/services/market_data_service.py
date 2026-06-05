import asyncio
import os
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from ..utils.data_validation import validate_ak_data
from .search_service import search_service
from .data_providers import data_router

# Only import akshare if enabled (geo-blocked from non-China servers)
class DummyAkShare:
    def __getattr__(self, name):
        raise AttributeError(f"AkShare is disabled. Cannot call '{name}'")

_AKSHARE_ENABLED = os.getenv("AKSHARE_ENABLED", "false").lower() == "true"
if _AKSHARE_ENABLED:
    import akshare as ak
else:
    ak = DummyAkShare()
from ..utils.network import safe_ak_call

class MarketDataService:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300 # 5 minutes

    async def resolve_symbol(self, query: str, market: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Smart Recognition: Resolve a query (name or code) to a list of matching assets.
        """
        results = []
        
        # 1. Check if it's already a code
        if query.isdigit():
            if len(query) == 6:
                return [{"symbol": query, "name": "A-Share Code", "market": "A-Share"}]
            if len(query) <= 5:
                return [{"symbol": query, "name": "HK-Share Code", "market": "HK-Share"}]
        
        # 2. Search A-Shares if market is None or A-Share
        if market is None or market == "A-Share":
            try:
                df = await safe_ak_call(ak.stock_info_a_code_name)
                if df is not None and not df.empty:
                    # Fuzzy match on name or exact match on code
                    matches = df[df['name'].str.contains(query, na=False) | (df['code'] == query)]
                    for _, row in matches.head(5).iterrows():
                        results.append({
                            "symbol": row['code'],
                            "name": row['name'],
                            "market": "A-Share"
                        })
            except Exception as e:
                print(f"A-Share resolution error: {e}")

            # Fallback: Sina suggest API when AkShare is unavailable
            if not results:
                try:
                    import urllib.request
                    from urllib.parse import quote
                    encoded_key = quote(query)
                    url = f"https://suggest3.sinajs.cn/suggest/type=11&key={encoded_key}"
                    req = urllib.request.Request(url, headers={
                        "Referer": "https://finance.sina.com.cn",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    })
                    resp = urllib.request.urlopen(req, timeout=10)
                    text = resp.read().decode("gbk")
                    # Parse: var suggestvalue="name,11,code,shcode,name2,,name3,99,1,,,;..."
                    import re
                    m = re.search(r'"([^"]*)"', text)
                    if m:
                        for item in m.group(1).split(";"):
                            parts = item.split(",")
                            if len(parts) >= 4 and parts[1] == "11":  # type=11 = stock
                                code = parts[2]
                                name = parts[0]
                                if len(code) == 6 and code.startswith(("6", "0", "3", "8", "4")):
                                    # Only return exact name matches for clean auto-selection
                                    if name == query:
                                        results.append({
                                            "symbol": code,
                                            "name": name,
                                            "market": "A-Share"
                                        })
                except Exception as e:
                    print(f"A-Share resolution via Sina suggest failed: {e}")

        # 3. Search HK-Shares if market is None or HK-Share
        if not results and (market is None or market == "HK-Share"):
            try:
                # Use stock_hk_spot_em for a quick list of HK stocks
                df = await safe_ak_call(ak.stock_hk_spot_em)
                if df is not None and not df.empty:
                    matches = df[df['名称'].str.contains(query, na=False) | (df['代码'] == query)]
                    for _, row in matches.head(5).iterrows():
                        results.append({
                            "symbol": row['代码'],
                            "name": row['名称'],
                            "market": "HK-Share"
                        })
            except Exception as e:
                print(f"HK-Share resolution error: {e}")

        # 4. Search US-Shares (Yahoo Finance search) — only if no A/HK results
        if not results and (market is None or market == "US-Share"):
            try:
                # We can use a search service or yfinance if it supports it
                # For now, let's use a simple heuristic or a search API if available
                # Actually, search_service might have this
                search_results = await search_service.search(f"{query} stock symbol yahoo finance", max_results=5)
                # This is a bit slow, but US stocks are harder to list locally
                # Let's just return the query as US-Share if nothing else found and it looks like a symbol
                if query.isascii() and query.isalpha() and len(query) <= 5:
                    results.append({"symbol": query.upper(), "name": query.upper(), "market": "US-Share"})
            except Exception as e:
                print(f"US-Share resolution error: {e}")

        return results

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
                        # EV: use raw value if same currency or positive; recompute via FX if currency mismatch + negative
                        "enterpriseValue": self._compute_ev_with_fx(info),
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
        Fetch historical data for a symbol via the DataRouter.
        Routes to optimal provider based on market detection.
        """
        try:
            df = await data_router.get_history(symbol, period=period, interval=interval)
            if df is not None and not df.empty:
                return df.to_dict(orient="records")
            return []
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
                    except:
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
                if _AKSHARE_ENABLED:
                    try:
                        info_df = await safe_ak_call(ak.stock_individual_info_em, symbol=clean_symbol)
                        if validate_ak_data(info_df, min_rows=1):
                            ak_info = dict(zip(info_df['item'], info_df['value']))
                    except Exception as e:
                        print(f"AkShare info failed for {clean_symbol}: {e}")
                
                # Fetch financial indicator (AkShare fallback)
                ak_financials = {}
                if _AKSHARE_ENABLED:
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
                                "latestOcfPerShare": l0.get("每股经营现金流(元)"),
                            }
                            # Calculate 扣非净利润 YoY/QoQ from history
                            npd_key = "扣除非经常性损益后的净利润"
                            npd_alt = "扣非净利润"
                            if len(latest) >= 2:
                                npd0 = l0.get(npd_key) or l0.get(npd_alt)
                                npd1 = latest[1].get(npd_key) or latest[1].get(npd_alt)
                                if npd0 is not None and npd1 is not None and npd1 != 0:
                                    try:
                                        ak_financials["latestNetProfitDeductQoQ"] = (float(npd0) - float(npd1)) / abs(float(npd1))
                                    except (ValueError, TypeError):
                                        pass
                            if len(latest) >= 5:
                                npd0 = l0.get(npd_key) or l0.get(npd_alt)
                                npd4 = latest[4].get(npd_key) or latest[4].get(npd_alt)
                                if npd0 is not None and npd4 is not None and npd4 != 0:
                                    try:
                                        ak_financials["latestNetProfitDeductYoY"] = (float(npd0) - float(npd4)) / abs(float(npd4))
                                    except (ValueError, TypeError):
                                        pass
                    except:
                        pass
                
                # Fetch stock_financial_abstract_ths — primary source for quarterly history
                quarterly_history_rows = []
                if _AKSHARE_ENABLED:
                    try:
                        abstract_df = await safe_ak_call(ak.stock_financial_abstract_ths, symbol=clean_symbol)
                        if validate_ak_data(abstract_df, min_rows=1):
                            # Extract last 5 quarters as structured rows
                            for _, row in abstract_df.tail(5).iterrows():
                                qrow = {}
                                period = str(row.get("报告期", ""))
                                qrow["period"] = period
                                for field, key in [
                                    ("净利润", "netProfit"), ("净利润同比增长率", "netProfitYoY"),
                                    ("扣非净利润", "netProfitDeduct"), ("扣非净利润同比增长率", "netProfitDeductYoY"),
                                    ("营业总收入", "revenue"), ("营业总收入同比增长率", "revenueYoY"),
                                    ("基本每股收益", "eps"), ("每股净资产", "bvps"),
                                    ("每股经营现金流", "ocfPerShare"), ("销售毛利率", "grossMargin"),
                                    ("销售净利率", "netMargin"), ("净资产收益率", "roe"),
                                    ("资产负债率", "debtRatio"), ("流动比率", "currentRatio"),
                                    ("速动比率", "quickRatio"), ("存货周转率", "inventoryTurnover"),
                                ]:
                                    val = row.get(field)
                                    if val is not None and str(val).strip() and str(val) not in ("False", "None", "--"):
                                        qrow[key] = str(val)
                                quarterly_history_rows.append(qrow)
                            
                            # Also fill ak_financials from latest row
                            latest_row = abstract_df.iloc[-1]
                            if not ak_financials.get("latestNetProfitDeduct"):
                                npd_str = latest_row.get("扣非净利润")
                                if npd_str and npd_str != "False" and str(npd_str).strip():
                                    ak_financials["latestNetProfitDeduct"] = self._parse_cn_number(str(npd_str))
                            if not ak_financials.get("latestNetProfitDeductYoY"):
                                npd_yoy_str = latest_row.get("扣非净利润同比增长率")
                                if npd_yoy_str and npd_yoy_str != "False" and str(npd_yoy_str).strip():
                                    parsed_yoy = self._parse_cn_percent(str(npd_yoy_str))
                                    if parsed_yoy is not None:
                                        ak_financials["latestNetProfitDeductYoY"] = parsed_yoy
                            # QoQ from previous row
                            if len(abstract_df) >= 2 and ak_financials.get("latestNetProfitDeduct"):
                                prev_row = abstract_df.iloc[-2]
                                prev_npd_str = prev_row.get("扣非净利润")
                                if prev_npd_str and prev_npd_str != "False":
                                    prev_npd = self._parse_cn_number(str(prev_npd_str))
                                    curr_npd = ak_financials["latestNetProfitDeduct"]
                                    if prev_npd and curr_npd and prev_npd != 0:
                                        ak_financials["latestNetProfitDeductQoQ"] = (curr_npd - prev_npd) / abs(prev_npd)
                            if not ak_financials.get("latestNetProfit"):
                                np_str = latest_row.get("净利润")
                                if np_str and np_str != "False":
                                    ak_financials["latestNetProfit"] = self._parse_cn_number(str(np_str))
                            if not ak_financials.get("latestRoe"):
                                roe_str = latest_row.get("净资产收益率")
                                if roe_str and roe_str != "False":
                                    parsed_roe = self._parse_cn_percent(str(roe_str))
                                    if parsed_roe is not None:
                                        ak_financials["latestRoe"] = parsed_roe
                    except Exception as e:
                        print(f"stock_financial_abstract_ths failed for {clean_symbol}: {e}")

                # Fetch dividend info
                latest_dividend = {}
                if _AKSHARE_ENABLED:
                    try:
                        dividend_df = await safe_ak_call(ak.stock_history_dividend_detail, symbol=clean_symbol)
                        latest_dividend = dividend_df.iloc[0].to_dict() if validate_ak_data(dividend_df, min_rows=1) else {}
                    except:
                        pass

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
                            a_hist_pe = a_hist['Close'] / a_trailing_eps
                            a_hist_pe = a_hist_pe[(a_hist_pe > 0) & (a_hist_pe < 1000)]
                            if len(a_hist_pe) > 30:
                                a_pe_percentile = float((a_hist_pe < a_trailing_pe).sum()) / len(a_hist_pe)
                    except Exception:
                        pass

                # Fallback to search if critical metrics are missing (only when AkShare is enabled but failed)
                if _AKSHARE_ENABLED and not ak_financials.get("latestNetProfitDeduct"):
                    try:
                        print(f"Critical financials missing for {symbol}, falling back to search...")
                        query = f"{symbol} 最新财报 净利润 扣非净利润 营收环比 净利润同比 资本开支"
                        search_res = await search_service.quick_search(query)
                        ak_financials["searchContext"] = search_res
                    except Exception as e:
                        print(f"Search fallback for financials failed: {e}")


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
                    "netProfitDeductYoY": ak_financials.get("latestNetProfitDeductYoY"),
                    "netProfitDeductQoQ": ak_financials.get("latestNetProfitDeductQoQ"),
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
                    "operatingCashflow": yf_info.get("operatingCashflow"),
                    "capitalExpenditure": a_capital_expenditure,
                    "payoutRatio": yf_info.get("payoutRatio"),
                    "dividend": latest_dividend.get("派息"),
                    "dividendYield": ak_info.get("股息率") or yf_info.get("dividendYield"),
                    "heldPercentInsiders": yf_info.get("heldPercentInsiders"),
                    "heldPercentInstitutions": yf_info.get("heldPercentInstitutions"),
                    "fiftyTwoWeekHigh": yf_info.get("fiftyTwoWeekHigh"),
                    "fiftyTwoWeekLow": yf_info.get("fiftyTwoWeekLow"),
                    "price": yf_info.get("currentPrice") or yf_info.get("regularMarketPrice"),
                    "currency": "CNY",
                    "financialCurrency": "CNY",
                    "pePercentile": a_pe_percentile,
                    "financials": ak_financials,
                    "quarterlyHistory": quarterly_history_rows,
                    # Company identity fields (for factual grounding)
                    "longName": yf_info.get("longName") or ak_info.get("股票简称"),
                    "industry": yf_info.get("industry") or ak_info.get("行业"),
                    "sector": yf_info.get("sector"),
                    "exchange": yf_info.get("exchange"),
                    "listingDate": ak_info.get("上市时间"),
                    "longBusinessSummary": (yf_info.get("longBusinessSummary") or "")[:500],
                }
        except Exception as e:
            print(f"Financial summary fetch failed for {symbol}: {e}")
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
        except:
            pass
        return None

# Singleton instance
market_data_service = MarketDataService()
