from fastapi import APIRouter, Query
from typing import Optional, Dict, Any
import asyncio
import datetime
import logging
import pandas as pd
from ..services.market_data_service import market_data_service
from ..services.data_providers import data_router
from ..services.search_service import search_service
from ..utils.responses import success_response, error_response

logger = logging.getLogger(__name__)


def _format_yi(val: float) -> str:
    """Format yuan to 亿 string."""
    yi = val / 1e8
    return f"{yi:.2f}亿"


async def _fetch_sector_flow_data() -> Dict[str, Any]:
    """Fetch sector fund flow, used by /dashboard."""
    try:
        df = await asyncio.to_thread(ak.stock_fund_flow_industry, symbol="即时")
        if df is not None and not df.empty:
            df["净额"] = pd.to_numeric(df["净额"], errors="coerce").fillna(0)
            df["行业-涨跌幅"] = pd.to_numeric(df["行业-涨跌幅"], errors="coerce").fillna(0)
            df = df.sort_values(by="净额", ascending=False)
            records = df.to_dict(orient="records")
            for r in records:
                r["主力净流入-净额"] = r.get("净额", 0) * 1e8
                r["涨跌幅"] = r.get("行业-涨跌幅", 0)
                r["行业"] = r.get("行业", "未知")
            return {"topInflows": records[:5], "topOutflows": records[-3:]}
    except Exception as e:
        logger.warning(f"sector_flow primary failed: {e}")

    try:
        df = await asyncio.to_thread(ak.stock_sector_fund_flow_rank, indicator="今日", sector_type="行业资金流")
        if df is None or df.empty:
            df = await asyncio.to_thread(ak.stock_sector_fund_flow_rank, indicator="5日", sector_type="行业资金流")
        if df is not None and not df.empty:
            col_candidates = [c for c in df.columns if '主力' in c and '净额' in c]
            if col_candidates:
                inflow_col = col_candidates[0]
                df[inflow_col] = pd.to_numeric(df[inflow_col], errors='coerce').fillna(0)
                df = df.sort_values(by=inflow_col, ascending=False)
                chg_cols = [c for c in df.columns if '涨跌' in c and '幅' in c]
                chg_col = chg_cols[0] if chg_cols else None
                records = df.to_dict(orient="records")
                for r in records:
                    r["主力净流入-净额"] = r.get(inflow_col)
                    r["行业"] = r.get("名称", r.get("行业", "未知"))
                    r["涨跌幅"] = r.get(chg_col) if chg_col else r.get("涨跌幅", 0)
                return {"topInflows": records[:5], "topOutflows": records[-3:]}
    except Exception:
        pass
    return {"topInflows": [], "topOutflows": []}


async def _fetch_northbound_data() -> list:
    """Fetch northbound flow, used by /dashboard."""
    try:
        df = await asyncio.to_thread(ak.stock_hsgt_fund_flow_summary_em)
        if df is not None and not df.empty:
            return df.to_dict(orient="records")
        df_hist = await asyncio.to_thread(ak.stock_hsgt_board_rank_em, board="北上")
        if df_hist is not None and not df_hist.empty:
            return df_hist.head(5).to_dict(orient="records")
    except Exception:
        pass
    return []


def _derive_hot_sectors(sector_flow: dict) -> list:
    """Derive hot sectors from sector flow data — pure data, no AI."""
    top = sector_flow.get("topInflows", [])[:5]
    return [{
        "name": s.get("行业", ""),
        "inflow": s.get("主力净流入-净额", 0),
        "changePct": s.get("涨跌幅", 0),
        "companyCount": s.get("公司家数", 0),
        "leadStock": s.get("领涨股", ""),
        "leadStockPct": s.get("领涨股-涨跌幅", 0),
    } for s in top]


def _derive_recommendations(sector_flow: dict) -> list:
    """Derive recommendations from sector flow — deterministic, no AI."""
    top = sector_flow.get("topInflows", [])
    return [{
        "type": "Sector",
        "name": s.get("行业", ""),
        "reason": f"主力净流入{_format_yi(s.get('主力净流入-净额', 0))}，涨跌幅{s.get('涨跌幅', 0)}%",
    } for s in top if s.get("涨跌幅", 0) > 0][:3]

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/status")
async def market_status():
    return success_response({
        "status": "ok",
        "sources": ["api", "sina", "yahoo", "router"],
        "routerStats": data_router.get_runtime_stats(),
        "routerPolicies": data_router.get_policy_snapshot(),
    })

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
    data = await market_data_service.get_quotes_with_meta([symbol])
    if data and "error" in data[0]:
        return error_response("QUOTE_FETCH_FAILED", data[0]["error"])
    route_meta = data[0].get("_route_meta", {}) if data else {}
    return success_response(data[0] if data else None, meta={"route": route_meta})

@router.get("/quotes")
async def get_batch_quotes(symbols: str = Query(..., description="Comma-separated list of symbols")):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return error_response("INVALID_INPUT", "No symbols provided")
    
    data = await market_data_service.get_quotes_with_meta(symbol_list)
    routes = {row.get("symbol", f"idx_{i}"): row.get("_route_meta", {}) for i, row in enumerate(data)}
    return success_response(data, meta={"routes": routes})

@router.get("/history/{symbol}")
async def get_symbol_history(
    symbol: str, 
    period: str = Query("1mo"),
    interval: str = Query("1d")
):
    clean_period = period[1:] if period.startswith('p') else period
    data, route_meta = await market_data_service.get_history_with_meta(symbol, period=clean_period, interval=interval)
    return success_response(data, meta={"route": route_meta})

@router.get("/sector_flow")
async def get_sector_fund_flow() -> Dict[str, Any]:
    # Primary: stock_fund_flow_industry (uses datacenter API, more reliable)
    try:
        df = await asyncio.to_thread(ak.stock_fund_flow_industry, symbol="即时")
        if df is not None and not df.empty:
            df["净额"] = pd.to_numeric(df["净额"], errors="coerce").fillna(0)
            df["行业-涨跌幅"] = pd.to_numeric(df["行业-涨跌幅"], errors="coerce").fillna(0)
            df = df.sort_values(by="净额", ascending=False)
            records = df.to_dict(orient="records")
            for r in records:
                r["主力净流入-净额"] = r.get("净额", 0) * 1e8  # 亿元→元
                r["涨跌幅"] = r.get("行业-涨跌幅", 0)
                r["行业"] = r.get("行业", "未知")
            return success_response({
                "topInflows": records[:5],
                "topOutflows": records[-3:]
            })
    except Exception as e:
        logger.warning(f"stock_fund_flow_industry failed: {e}, trying fallback")

    # Fallback: stock_sector_fund_flow_rank (uses push2 API, may be blocked)
    try:
        df = await asyncio.to_thread(ak.stock_sector_fund_flow_rank, indicator="今日", sector_type="行业资金流")
        if df is None or df.empty:
            df = await asyncio.to_thread(ak.stock_sector_fund_flow_rank, indicator="5日", sector_type="行业资金流")

        if df is not None and not df.empty:
            col_candidates = [c for c in df.columns if '主力' in c and '净额' in c]
            if not col_candidates:
                col_candidates = [c for c in df.columns if '净流入' in c and '占比' not in c]

            if col_candidates:
                inflow_col = col_candidates[0]
                df[inflow_col] = pd.to_numeric(df[inflow_col], errors='coerce').fillna(0)
                df = df.sort_values(by=inflow_col, ascending=False)
                chg_cols = [c for c in df.columns if '涨跌' in c and '幅' in c]
                chg_col = chg_cols[0] if chg_cols else None
                records = df.to_dict(orient="records")
                for r in records:
                    r["主力净流入-净额"] = r.get(inflow_col)
                    r["行业"] = r.get("名称", r.get("行业", "未知"))
                    r["涨跌幅"] = r.get(chg_col) if chg_col else r.get("涨跌幅", 0)
                return success_response({
                    "topInflows": records[:5],
                    "topOutflows": records[-3:]
                })
    except Exception as e:
        return error_response("DATA_SOURCE_ERROR", str(e))
    return error_response("DATA_EMPTY", "No sector flow data available")

@router.get("/northbound")
async def get_northbound_flow() -> Dict[str, Any]:
    try:
        df = await asyncio.to_thread(ak.stock_hsgt_fund_flow_summary_em)
        if df is not None and not df.empty:
            records = df.to_dict(orient="records")
        else:
            df_hist = await asyncio.to_thread(ak.stock_hsgt_board_rank_em, board="北上")
            if df_hist is not None and not df_hist.empty:
                records = df_hist.head(5).to_dict(orient="records")
            else:
                records = []
        return success_response(records)
    except Exception as e:
        return error_response("NORTHBOUND_FETCH_FAILED", str(e))

@router.get("/news")
async def get_financial_news(market: str = "A-Share") -> Dict[str, Any]:
    data = await market_data_service.get_news(market)
    return success_response(data)

@router.get("/search")
async def search_web(query: str, max_results: int = 20):
    from ..services.input_sanitizer import input_sanitizer
    sanitized_query = input_sanitizer.sanitize_query(query)
    data = await search_service.search(sanitized_query, max_results=max_results)
    return success_response(data)

@router.get("/news_search")
async def search_news(query: str, max_results: int = 20):
    from ..services.input_sanitizer import input_sanitizer
    sanitized_query = input_sanitizer.sanitize_query(query)
    data = await search_service.search_news(sanitized_query, max_results=max_results)
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


@router.get("/dashboard")
async def get_market_dashboard(market: str = "A-Share") -> Dict[str, Any]:
    """Aggregate all market data into a single DTO. No AI — pure data routes."""
    needs_sectors = market in ("A-Share", "HK-Share")
    needs_northbound = market == "A-Share"

    indices_coro = market_data_service.get_indices(market)
    commodities_coro = market_data_service.get_quotes(["GC=F", "CL=F", "USDCNY=X", "^VIX", "^TNX"])
    news_coro = market_data_service.get_news(market)

    sector_coro = _fetch_sector_flow_data() if needs_sectors else asyncio.sleep(0)
    northbound_coro = _fetch_northbound_data() if needs_northbound else asyncio.sleep(0)

    indices, commodities, news, sector_flow, northbound = await asyncio.gather(
        indices_coro, commodities_coro, news_coro, sector_coro, northbound_coro,
        return_exceptions=True,
    )

    indices = indices if isinstance(indices, list) else []
    commodities = commodities if isinstance(commodities, list) else []
    news = news if isinstance(news, list) else []
    sector_flow = sector_flow if isinstance(sector_flow, dict) else {"topInflows": [], "topOutflows": []}
    northbound = northbound if isinstance(northbound, list) else []

    hot_sectors = _derive_hot_sectors(sector_flow)
    recommendations = _derive_recommendations(sector_flow)

    return success_response({
        "indices": indices,
        "commodities": commodities,
        "news": news,
        "sectorFlow": sector_flow,
        "northbound": northbound,
        "hotSectors": hot_sectors,
        "recommendations": recommendations,
        "updatedAt": datetime.datetime.now(datetime.UTC).isoformat(),
    })
