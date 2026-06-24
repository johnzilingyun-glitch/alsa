from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Dict, Any
import pandas as pd
import akshare as ak
from ..quant.polars_indicators import compute_indicator_frame
from ..utils.responses import success_response, error_response
from ..utils.network import safe_ak_call

router = APIRouter(prefix="/technicals", tags=["technicals"])

class IndicatorRequest(BaseModel):
    data: List[Dict[str, Any]]

@router.post("/calculate")
async def calculate_indicators(request: IndicatorRequest):
    try:
        df = compute_indicator_frame(request.data)
        if df.is_empty():
            return error_response("COMPUTE_FAILED", "Unable to compute indicators")
        return success_response(df.to_dicts())
    except Exception as e:
        return error_response("INTERNAL_ERROR", str(e))

@router.get("/{symbol}")
async def get_technicals(
    symbol: str,
    days: int = Query(120, description="Days of history to analyze")
):
    """
    Run quantitative technical analysis ensemble for a symbol.
    """
    try:
        import datetime
        end_date = datetime.datetime.now().strftime("%Y%m%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=int(days*1.5))).strftime("%Y%m%d")
        
        # Try a-share first (heuristic)
        try:
            df = await safe_ak_call(ak.stock_zh_a_hist, symbol=symbol[:6], period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        except:
            df = pd.DataFrame()
            
        if df.empty:
            return error_response("SYMBOL_NOT_FOUND", f"No data found for {symbol}")
            
        # Rename columns to standard english
        col_map = {'日期': 'Date', '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume'}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        
        # Ensure numeric and drop NA
        for c in ['open', 'close', 'high', 'low', 'volume']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['close'])
        
        if len(df) < 30:
            return error_response("INSUFFICIENT_DATA", f"Insufficient data: only {len(df)} rows")
            
        # Import analysis from technicals.py in parent dir if available
        try:
            from ..technicals import analyze as analyze_technicals
            result = analyze_technicals(df)
            return success_response(result)
        except ImportError:
            # Fallback if the module structure is different
            return error_response("MODULE_NOT_FOUND", "Technical analysis module not found")
        
    except Exception as e:
        return error_response("TECHNICAL_ANALYSIS_FAILED", str(e))
