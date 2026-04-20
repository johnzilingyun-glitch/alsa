from fastapi import APIRouter, Query
from typing import List, Optional
from ..services.market_data_service import market_data_service

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/status")
async def market_status():
    return {"status": "ok", "sources": ["akshare", "sina", "yahoo"]}

@router.get("/indices")
async def get_indices(market: str = "A-Share"):
    data = await market_data_service.get_indices(market)
    return {"success": True, "data": data}

@router.get("/commodities")
async def get_commodities():
    """
    Fetch major commodities and macro indicators.
    """
    symbols = ["GC=F", "CL=F", "USDCNY=X", "^VIX", "^TNX"]
    data = await market_data_service.get_quotes(symbols)
    return {"success": True, "data": data}

@router.get("/quote/{symbol}")
async def get_symbol_quote(symbol: str):
    """
    Fetch a real-time quote for any symbol.
    """
    data = await market_data_service.get_quotes([symbol])
    if data and "error" in data[0]:
        return {"success": False, "error": data[0]["error"]}
    return {"success": True, "data": data[0] if data else None}

@router.get("/quotes")
async def get_batch_quotes(symbols: str = Query(..., description="Comma-separated list of symbols")):
    """
    Fetch real-time quotes for multiple symbols.
    """
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return {"success": False, "error": "No symbols provided"}
    
    data = await market_data_service.get_quotes(symbol_list)
    return {"success": True, "data": data}

@router.get("/history/{symbol}")
async def get_symbol_history(
    symbol: str, 
    period: str = Query("1mo", description="p1d, p5d, p1mo, p3mo, p6mo, p1y, p2y, p5y, p10y, pytd, pmax"),
    interval: str = Query("1d", description="1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo")
):
    """
    Fetch historical data for a symbol.
    """
    # Remove 'p' prefix from period if present (convenience)
    clean_period = period[1:] if period.startswith('p') else period
    data = await market_data_service.get_history(symbol, period=clean_period, interval=interval)
    return {"success": True, "data": data}
