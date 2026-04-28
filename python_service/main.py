from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import akshare as ak
import pandas as pd
from typing import Dict, Any
import time
import asyncio
try:
    from .technicals import analyze as analyze_technicals
    from .snapshot_manager import save_market_snapshot, SNAPSHOT_DIR
    from .app.api.router import api_router
    from .app.utils.network import safe_ak_call
except (ImportError, ValueError):
    from technicals import analyze as analyze_technicals
    from snapshot_manager import save_market_snapshot, SNAPSHOT_DIR
    from app.api.router import api_router
    from app.utils.network import safe_ak_call


import polars as pl
import duckdb
import uuid

app = FastAPI(title="AI Daily Financial Backend", version="1.0.0")

# Enable CORS for local Node proxy access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    async def precompute_loop():
        while True:
            try:
                # 获取 watchlist 默认列表中的所有股票
                items = watchlist_repo.list_items()
                for item in items:
                    await market_data_service.precompute_financial_summary(item.symbol, item.market)
                await asyncio.sleep(300) # 每5分钟更新一次
            except Exception as e:
                print(f"Precompute loop error: {e}")
                await asyncio.sleep(60)

    asyncio.create_task(precompute_loop())
from .app.db.sqlite import build_session_factory, DATABASE_URL
from .app.lake.parquet_store import ParquetMarketStore
from .app.db.repositories.job_repo import JobRepository
from .app.services.market_snapshot_service import MarketSnapshotService
from .app.services.analysis_job_service import AnalysisJobService
from .app.services.brain_manager import brain_manager
from .app.db.repositories.watchlist_repo import WatchlistRepository
from .app.db.repositories.journal_repo import JournalRepository
from .app.services.market_data_service import market_data_service
from .app.db.repositories.alert_repo import AlertRepository

# Singletons for simplicity in this analytical app
session_factory = build_session_factory(DATABASE_URL)
parquet_store = ParquetMarketStore()
job_repo = JobRepository(session_factory)
watchlist_repo = WatchlistRepository(session_factory)
journal_repo = JournalRepository(session_factory)
alert_repo = AlertRepository(session_factory)

market_snapshot_service = MarketSnapshotService(parquet_store)
analysis_job_service = AnalysisJobService(job_repo, market_snapshot_service)

# Dependency helpers
def get_analysis_job_service():
    return analysis_job_service

def get_watchlist_repo():
    return watchlist_repo

def get_journal_repo():
    return journal_repo

def get_alert_repo():
    return alert_repo

# --- A-Share Spot Cache (avoids pulling 5000+ rows per request) ---
_spot_cache: Dict[str, Any] = {"df": None, "ts": 0}
SPOT_CACHE_TTL = 30  # seconds

# --- Job Management ---
analysis_jobs: Dict[str, Dict[str, Any]] = {}

def get_duckdb_conn():
    return duckdb.connect(database=':memory:') # Or a local file for persistent analysis

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
                # Fallback to 5-day flow if today is empty (weekends/holidays)
                df = ak.stock_sector_fund_flow_rank(indicator="5日", sector_type="行业资金流")
                
            if df.empty:
                raise ValueError("AkShare returned empty dataframe for sector flow")

            # Sort by Net Inflow Amount descending
            df = df.sort_values(by=inflow_col, ascending=False)

            # 【增强校验】如果获取到的记录太少，视为数据质量故障
            if len(df) < 5:
                raise ValueError("AkShare data insufficient")

            # Get Top 5 sectors
            top_sectors = df.head(5).to_dict(orient="records")
            # Get Bottom 3 sectors
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
        "code": "AKSHARE_DATA_SOURCE_UNAVAILABLE",
        "message": "【数据源异常】AkShare API 连接中断，行业资金流数据暂不可用。请稍后重试。",
        "error": last_error,
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
        df = await safe_ak_call(ak.stock_hsgt_fund_flow_summary_em)
        
        if df.empty:
            # Fallback to historical daily flow to get the "recent" flow
            df_hist = await safe_ak_call(ak.stock_hsgt_board_rank_em, board="北上")
            records = df_hist.head(5).to_dict(orient="records")
        else:
            records = df.to_dict(orient="records")
        
        # Check for "暂停" (Paused) status and annotate
        for r in records:
            if "暂停" in str(r.get("当日成交净买入", "")) or "暂停" in str(r.get("当日实时额度", "")):
                r["status_note"] = "A股通当前处于暂停交易或额度受限状态（可能为非交易时段或节假日）。"

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

@app.get("/api/stock/hk_spot")
async def get_stock_hk_spot(
    symbol: str = Query(..., pattern=r"^\d{1,5}$", description="1-5 digit HK stock code")
) -> Dict[str, Any]:
    """
    Fetch real-time HK-Share stock quote from EastMoney via AkShare.
    """
    try:
        # stock_hk_spot_em returns real-time quotes for all HK stocks
        # We search for the specific symbol
        df = await safe_ak_call(ak.stock_hk_spot_em)
        if df.empty:
            return {"success": False, "error": "No HK data available"}
            
        # Symbol in AkShare HK is usually just the code string or zero-padded
        # EastMoney HK symbols in AkShare are typically strings like '00700'
        row = df[df['代码'] == symbol.padStart(5, '0') if len(symbol) < 5 else symbol]
        if row.empty:
            # Try fuzzy match if exact fails
            row = df[df['代码'].str.contains(symbol)]
            
        if row.empty:
            return {"success": False, "error": f"Symbol {symbol} not found in HK market"}
            
        data = row.iloc[0].to_dict()
        clean_data = {k: (None if pd.isna(v) else v) for k, v in data.items()}
        
        return {"success": True, "data": clean_data}
    except Exception as e:
        print(f"Error fetching HK stock spot: {e}")
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
            try:
                df = await safe_ak_call(ak.stock_zh_a_spot_em)
                _spot_cache = {"df": df, "ts": now}
            except Exception as e:
                print(f"Failed to refresh spot cache: {e}")
                if _spot_cache["df"] is None:
                    return {"success": False, "error": f"Data source unavailable: {e}"}
        
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
            df = await safe_ak_call(ak.stock_zh_a_hist, symbol=symbol[:6], period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
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
        
        df = await safe_ak_call(ak.stock_zh_a_hist, symbol=symbol, period=period, start_date=start_date, end_date=end_date, adjust="qfq")
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
        df = await safe_ak_call(ak.stock_individual_info_em, symbol=symbol)
        info = dict(zip(df['item'], df['value']))
        
        return {"success": True, "data": info}
    except Exception as e:
        print(f"Error fetching valuation: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/stock/comprehensive_financials")
async def get_comprehensive_financials(
    symbol: str,
    market: str = "A-Share"
) -> Dict[str, Any]:
    """
    Fetch unified financial metrics: Market Cap, Net Profit history, Dividends.
    """
    data = await market_data_service.get_financial_summary(symbol, market)
    if "error" in data:
        return {"success": False, "error": data["error"]}
    return {"success": True, "data": data}

# --- New Financial Dimension Endpoints ---

@app.get("/api/stock/lhb")
async def get_stock_lhb(
    symbol: str = Query(..., description="Stock code"),
    date: str = Query(None, description="Date in YYYYMMDD format")
) -> Dict[str, Any]:
    """
    Fetch Dragon-Tiger (Longhu Bang) detail info.
    """
    try:
        import datetime
        now = datetime.datetime.now()
        # If it's before 18:00, today's LHB might not be out yet, try yesterday
        if now.hour < 18:
            date = (now - datetime.timedelta(days=1)).strftime("%Y%m%d")
        elif date is None:
            date = now.strftime("%Y%m%d")
            
        df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
        
        # If still empty, try back up to 3 days (handling weekends)
        max_back = 3
        while df.empty and max_back > 0:
            date = (datetime.datetime.strptime(date, "%Y%m%d") - datetime.timedelta(days=1)).strftime("%Y%m%d")
            df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
            max_back -= 1

        if df.empty:
            return {"success": False, "error": "No LHB data available for the last few days"}
            
        row = df[df['代码'] == symbol]
        if row.empty:
            return {"success": False, "error": f"No LHB data for {symbol} on {date}"}
            
        return {"success": True, "data": row.to_dict(orient="records"), "date": date}
    except Exception as e:
        print(f"Error fetching LHB: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/stock/margin")
async def get_stock_margin(
    symbol: str = Query(..., description="Stock code")
) -> Dict[str, Any]:
    """
    Fetch margin trading detail info.
    """
    try:
        import datetime
        now = datetime.datetime.now()
        # Margin data usually updates late at night or next morning. Try yesterday if today fails.
        date = now.strftime("%Y%m%d")
        
        def _get_df(d):
            if symbol.startswith('6'):
                return ak.stock_margin_detail_sse(date=d)
            else:
                return ak.stock_margin_detail_szse(date=d)

        df = _get_df(date)
        if df.empty:
            date = (now - datetime.timedelta(days=1)).strftime("%Y%m%d")
            df = _get_df(date)
            
        # Try one more day back for weekends
        if df.empty:
            date = (now - datetime.timedelta(days=2)).strftime("%Y%m%d")
            df = _get_df(date)

        if df.empty:
            return {"success": False, "error": "No margin data available for the last 3 days"}

        code_cols = [c for c in df.columns if '代码' in c]
        if code_cols:
            row = df[df[code_cols[0]] == symbol]
            if not row.empty:
                return {"success": True, "data": row.iloc[0].to_dict(), "date": date}
                
        return {"success": False, "error": f"No margin data for {symbol} on {date}"}
    except Exception as e:
        print(f"Error fetching margin: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/stock/notices")
async def get_stock_notices(
    symbol: str = Query(..., description="Stock code")
) -> Dict[str, Any]:
    """
    Fetch recent corporate announcements.
    """
    try:
        # Easy endpoint for A-share notices
        df = ak.stock_npq_em(symbol=symbol)
        if df.empty:
            return {"success": False, "error": "No notices found"}
        records = df.head(5).to_dict(orient="records")
        return {"success": True, "data": records}
    except Exception as e:
        print(f"Error fetching notices: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/market/social_trends")
async def get_social_trends() -> Dict[str, Any]:
    """
    Aggregates economic news and sentiment as a proxy for social trends.
    """
    try:
        df = ak.news_economic_baidu()
        records = df.head(10).to_dict(orient="records") if hasattr(df, 'head') else []
        return {"success": True, "data": records}
    except Exception as e:
        print(f"Error fetching social trends: {e}")
        return {"success": False, "error": str(e)}

# Analysis Job Endpoints handled via api_router / analysis_router

@app.get("/api/analysis/query")
async def query_historical_analysis(query_sql: str):
    """
    Example DuckDB query over the Parquet data lake.
    """
    try:
        con = duckdb.connect()
        # Create a view over the Parquet snapshots
        con.execute(f"CREATE VIEW snapshots AS SELECT * FROM read_parquet('{SNAPSHOT_DIR}/*.parquet')")
        res = con.execute(query_sql).pl()
        return {"success": True, "data": res.to_dicts()}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Brain & Evolution handled via router ---

from datetime import datetime

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
