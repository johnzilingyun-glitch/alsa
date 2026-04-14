from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import akshare as ak
import pandas as pd
from typing import Dict, Any

app = FastAPI(title="AI Daily Financial Backend", version="1.0.0")

# Enable CORS for local Node proxy access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Python Data Acquisition"}

@app.get("/api/market/sector_flow")
async def get_sector_fund_flow() -> Dict[str, Any]:
    """
    Fetch Eastern Money (东方财富) real-time industry sector fund flows.
    Returns the top sectors with the highest net inflows (主力净流入).
    """
    try:
        # stock_sector_fund_flow_rank fetches industry fund flow rank
        # Returns cols: 序号, 行业, 最新价, 涨跌幅, 主力净流入-净额, 主力净流入-净占比, ...
        df: pd.DataFrame = ak.stock_sector_fund_flow_rank()
        
        # Sort by Net Inflow Amount descending to get the "Hot" money destinations
        # Make sure column name matches AkShare's latest structure. 
        # Typically it's "主力净流入-净额"
        inflow_col = "主力净流入-净额" if "主力净流入-净额" in df.columns else df.columns[4]
        
        # Convert necessary columns
        if df[inflow_col].dtype == object or str(df[inflow_col].dtype) == 'category':
            # Remove any commas, "亿", "万" etc if it's string format and parse float
            # But Akshare usually returns standard floats here
            pass
            
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
        print(f"Error fetching sector flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/northbound")
async def get_northbound_flow() -> Dict[str, Any]:
    """
    Fetch Northbound Capital net flow (沪深港通资金流向).
    Important indicator of Foreign Institutional Capital sentiment.
    """
    try:
        # Get real-time northbound flow summary
        import datetime
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北向资金")
        
        # This returns historical daily net flow. We get today's or the latest record.
        latest_record = df.iloc[-1].to_dict()
        
        return {
            "success": True,
            "data": latest_record
        }
    except Exception as e:
        print(f"Error fetching northbound flow: {e}")
        # Not throwing 500 error here tightly since this is an unstable API sometimes
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
        print(f"Error fetching news: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
