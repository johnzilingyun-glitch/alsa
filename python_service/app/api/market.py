from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Dict, Any
import pandas as pd
import akshare as ak
from ..services.market_data_service import market_data_service
from ..services.search_service import search_service
from ..utils.network import safe_ak_call
from ..utils.responses import success_response, error_response

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/status")
async def market_status():
    return success_response({"status": "ok", "sources": ["akshare", "sina", "yahoo"]})

@router.get("/indices")
async def get_indices(market: str = "A-Share"):
    data = await market_data_service.get_indices(market)
    return success_response(data)

@router.get("/commodities")
async def get_commodities():
    symbols = ["GC=F", "CL=F", "USDCNY=X", "^VIX", "^TNX"]
    data = await market_data_service.get_quotes(symbols)
    return success_response(data)

@router.get("/quote/{symbol}")
async def get_symbol_quote(symbol: str):
    data = await market_data_service.get_quotes([symbol])
    if data and "error" in data[0]:
        return error_response("QUOTE_FETCH_FAILED", data[0]["error"])
    return success_response(data[0] if data else None)

@router.get("/quotes")
async def get_batch_quotes(symbols: str = Query(..., description="Comma-separated list of symbols")):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return error_response("INVALID_INPUT", "No symbols provided")
    
    data = await market_data_service.get_quotes(symbol_list)
    return success_response(data)

@router.get("/history/{symbol}")
async def get_symbol_history(
    symbol: str, 
    period: str = Query("1mo"),
    interval: str = Query("1d")
):
    clean_period = period[1:] if period.startswith('p') else period
    data = await market_data_service.get_history(symbol, period=clean_period, interval=interval)
    return success_response(data)

@router.get("/sector_flow")
async def get_sector_fund_flow() -> Dict[str, Any]:
    max_retries = 3
    inflow_col = "主力净流入-净额"
    for attempt in range(max_retries):
        try:
            df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
            if df.empty:
                df = ak.stock_sector_fund_flow_rank(indicator="5日", sector_type="行业资金流")
            if not df.empty:
                df = df.sort_values(by=inflow_col, ascending=False)
                return success_response({
                    "topInflows": df.head(5).to_dict(orient="records"),
                    "topOutflows": df.tail(3).to_dict(orient="records")
                })
        except Exception as e:
            if attempt == max_retries - 1:
                return error_response("DATA_SOURCE_ERROR", str(e))
    return error_response("DATA_EMPTY", "No sector flow data available")

@router.get("/northbound")
async def get_northbound_flow() -> Dict[str, Any]:
    try:
        df = await safe_ak_call(ak.stock_hsgt_fund_flow_summary_em)
        if df.empty:
            df_hist = await safe_ak_call(ak.stock_hsgt_board_rank_em, board="北上")
            records = df_hist.head(5).to_dict(orient="records")
        else:
            records = df.to_dict(orient="records")
        return success_response(records)
    except Exception as e:
        return error_response("NORTHBOUND_FETCH_FAILED", str(e))

@router.get("/news")
async def get_financial_news(market: str = "A-Share") -> Dict[str, Any]:
    data = await market_data_service.get_news(market)
    return success_response(data)

@router.get("/search")
async def search_web(query: str, max_results: int = 20):
    data = await search_service.search(query, max_results=max_results)
    return success_response(data)

@router.get("/news_search")
async def search_news(query: str, max_results: int = 20):
    data = await search_service.search_news(query, max_results=max_results)
    return success_response(data)

@router.get("/lhb")
async def get_stock_lhb(symbol: str, date: Optional[str] = None):
    try:
        import datetime
        now = datetime.datetime.now()
        if not date:
            date = (now - datetime.timedelta(days=1)).strftime("%Y%m%d") if now.hour < 18 else now.strftime("%Y%m%d")
        
        df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
        if df.empty:
            return error_response("NO_DATA", f"No LHB data for {date}")
        row = df[df['代码'] == symbol]
        return success_response(row.to_dict(orient="records"))
    except Exception as e:
        return error_response("LHB_FETCH_FAILED", str(e))
