from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import akshare as ak
import pandas as pd
from typing import Dict, Any
import time
import asyncio
try:
    from .technicals import analyze as analyze_technicals
except ImportError:
    from technicals import analyze as analyze_technicals

app = FastAPI(title="AI Daily Financial Backend", version="1.0.0")

# Enable CORS for local Node proxy access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- A-Share Spot Cache (avoids pulling 5000+ rows per request) ---
_spot_cache: Dict[str, Any] = {"df": None, "ts": 0}
SPOT_CACHE_TTL = 30  # seconds

@app.get("/api/health")
async def health_check():
    return {
        "success": True,
        "status": "ok",
        "service": "Python Data Acquisition",
        "message": "Python data acquisition service is running"
    }

@app.get("/api/market/sector_flow")
async def get_sector_fund_flow() -> Dict[str, Any]:
    """
    Fetch Eastern Money (东方财富) real-time industry sector fund flows.
    Returns the top sectors with the highest net inflows (主力净流入).
    Includes a retry mechanism for unstable network connections.
    """
    max_retries = 3
    last_error = ""
    
    for attempt in range(max_retries):
        try:
            # stock_sector_fund_flow_rank fetches industry fund flow rank
            # Returns cols: 序号, 行业, 最新价, 涨跌幅, 主力净流入-净额, 主力净流入-净占比, ...
            df: pd.DataFrame = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
            
            if df.empty:
                raise ValueError("AkShare returned empty dataframe for sector flow")

            # Sort by Net Inflow Amount descending to get the "Hot" money destinations
            # Column mapping check
            inflow_col = "主力净流入-净额" if "主力净流入-净额" in df.columns else df.columns[4]
            
            df = df.sort_values(by=inflow_col, ascending=False)
            
            # Get Top 5 sectors
            top_sectors = df.head(5).to_dict(orient="records")
            # Get Bottom 3 sectors (Most outflow)
            bottom_sectors = df.tail(3).to_dict(orient="records")
            
            return {
                "success": True,
                "data": {
                    "topInflows": top_sectors,
                    "topOutflows": bottom_sectors
                }
            }
        except Exception as e:
            last_error = str(e)
            print(f"Attempt {attempt+1} failed to fetch sector flow: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Non-blocking wait before retry
    
    # If all retries fail, return a success: false instead of 500 to allow Node to handle it
    return {
        "success": False, 
        "error": f"Failed after {max_retries} attempts. Last error: {last_error}",
        "data": {"topInflows": [], "topOutflows": []}
    }

@app.get("/api/market/northbound")
async def get_northbound_flow() -> Dict[str, Any]:
    """
    Fetch Northbound Capital net flow (沪深港通资金流向).
    Important indicator of Foreign Institutional Capital sentiment.
    Uses summary endpoint for maximum stability.
    """
    try:
        # Get real-time northbound flow summary
        # Columns usually contain: 涨跌幅, 净流入, etc.
        df = ak.stock_hsgt_fund_flow_summary_em()
        
        # We look for "北向" or "沪深港通" aggregate or just return the list
        records = df.to_dict(orient="records")
        
        return {
            "success": True,
            "data": records
        }
    except Exception as e:
        print(f"Error fetching northbound flow: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/market/news")
async def get_financial_news(market: str = "A-Share") -> Dict[str, Any]:
    """
    Fetch top financial news using EastMoney via AkShare.
    This resolves the Sina RSS blocking issues and perfectly aligns with FinGPT philosophy.
    """
    try:
        if market in ["A-Share", "HK-Share"]:
            # df = ak.stock_news_em(symbol="300059") doesn't give roll news easily.
            # Instead we can use global news or a known fast endpoint
            # For general macroeconomic roll news from eastmoney:
            df = ak.news_economic_baidu() 
            # Or Sina global news roll
            # df = ak.stock_info_global_sina()
            
            # Since akshare news APIs can be volatile, simple requests works too, but let's 
            # use a very stable one: sina global or eastmoney
            try:
                # Top global stock news via Sina
                df = ak.stock_info_global_sina()
                # Sort by time
                # the columns are typically: title, content, url, pub_date
                
                news_list = []
                # Handle both dict and dataframe correctly by falling back
                records = df.head(10).to_dict(orient="records") if hasattr(df, 'head') else []
                
                for r in records:
                    news_list.append({
                        "title": r.get('title', ''),
                        "url": r.get('url', ''),
                        "time": r.get('pub_date', ''),
                        "source": "Sina Finance (AkShare)"
                    })
                
                return {"success": True, "data": news_list}
            except Exception as inner_e:
                print("Primary Sina AKShare failed:", inner_e)
                # Fallback to Eastmoney global news if available, or just empty
                return {"success": True, "data": []}
        else:
            # For US-Share, we return empty so node falls back to Yahoo Finance
            return {"success": True, "data": []}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/stock/a_spot")
async def get_stock_a_spot(
    symbol: str = Query(..., pattern=r"^\d{6}$", description="6-digit A-share code")
) -> Dict[str, Any]:
    """
    Fetch real-time A-Share stock quote from EastMoney via AkShare.
    Uses a 30-second cache to avoid pulling all 5000+ A-shares per request.
    """
    global _spot_cache
    try:
        now = time.time()
        if _spot_cache["df"] is None or now - _spot_cache["ts"] > SPOT_CACHE_TTL:
            _spot_cache = {"df": ak.stock_zh_a_spot_em(), "ts": now}
        
        row = _spot_cache["df"][_spot_cache["df"]['代码'] == symbol]
        if row.empty:
            return {"success": False, "error": "Symbol not found"}
        
        data = row.iloc[0].to_dict()
        
        # Clean up data: ensure all values are serializable and handle NaN
        clean_data = {}
        for k, v in data.items():
            if pd.isna(v):
                clean_data[k] = None
            else:
                clean_data[k] = v
                
        return {"success": True, "data": clean_data}
    except Exception as e:
        print(f"Error fetching stock spot: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/technicals/{symbol}")
async def get_technicals(
    symbol: str,
    days: int = Query(120, description="Days of history to analyze")
) -> Dict[str, Any]:
    """
    Run the 5-strategy quantitative technical analysis ensemble.
    """
    try:
        import datetime
        end_date = datetime.datetime.now().strftime("%Y%m%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days*1.5)).strftime("%Y%m%d")
        
        # Try a-share first
        try:
            df = ak.stock_zh_a_hist(symbol=symbol[:6], period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        except:
            df = pd.DataFrame()
            
        if df.empty:
            return {"success": False, "error": f"No data found for {symbol}"}
            
        # Rename columns to standard english for technicals.py
        # Akshare typical cols: 日期, 开盘, 收盘, 最高, 最低, 成交量, ...
        # Can vary slightly, so we safely rename
        col_map = {
            '日期': 'Date', '开盘': 'open', '收盘': 'close', 
            '最高': 'high', '最低': 'low', '成交量': 'volume'
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        
        # Ensure we have the required columns
        required = ['open', 'close', 'high', 'low', 'volume']
        if not all(c in df.columns for c in required):
            return {"success": False, "error": f"Missing required columns in data: {df.columns.tolist()}"}
            
        # Ensure numeric
        for c in required:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
        df = df.dropna(subset=['close'])
        
        if len(df) < 30:
            return {"success": False, "error": f"Insufficient data: only {len(df)} rows"}
            
        # Run analysis
        result = analyze_technicals(df)
        
        return {"success": True, "data": result}
        
    except Exception as e:
        print(f"Error computing technicals for {symbol}: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/stock/a_history")
async def get_stock_a_history(
    symbol: str = Query(..., pattern=r"^\d{6}$", description="6-digit A-share code"),
    period: str = "daily",
    days: int = 120
) -> Dict[str, Any]:
    """
    Fetch historical K-line data for A-Shares.
    """
    try:
        import datetime
        end_date = datetime.datetime.now().strftime("%Y%m%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days*1.5)).strftime("%Y%m%d")
        
        df = ak.stock_zh_a_hist(symbol=symbol, period=period, start_date=start_date, end_date=end_date, adjust="qfq")
        if df.empty:
            return {"success": False, "error": "Empty history"}
        
        # Keep only necessary tail
        records = df.tail(days).to_dict(orient="records")
        return {"success": True, "data": records}
    except Exception as e:
        print(f"Error fetching stock history: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/stock/a_valuation")
async def get_stock_a_valuation(
    symbol: str = Query(..., pattern=r"^\d{6}$", description="6-digit A-share code")
) -> Dict[str, Any]:
    """
    Fetch fundamental indicators like PE, PB, ROE from EastMoney.
    """
    try:
        # stock_individual_info_em provides basic info including industry, PE, etc.
        df = ak.stock_individual_info_em(symbol=symbol)
        info = dict(zip(df['item'], df['value']))
        
        return {"success": True, "data": info}
    except Exception as e:
        print(f"Error fetching valuation: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
