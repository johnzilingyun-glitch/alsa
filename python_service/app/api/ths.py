"""THS (同花顺) API routes — 分钟K线、盘口、大单、板块、问财等"""

import logging
from fastapi import APIRouter, Query
from typing import Optional

from ..services.data_providers.ths_provider import ths_provider
from ..utils.responses import success_response, error_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ths", tags=["ths"])


@router.get("/search")
async def search_symbols(keyword: str = Query(..., description="股票名称/代码/拼音")):
    try:
        data = await ths_provider.search_symbols(keyword)
        return success_response(data)
    except Exception as e:
        return error_response("THS_SEARCH_FAILED", str(e))


@router.get("/klines")
async def get_klines(
    code: str = Query(..., description="THSCODE, e.g. USHA600519"),
    interval: str = Query("5m", description="1m/5m/15m/30m/60m/120m/day/week/month"),
    count: int = Query(78, description="Number of bars"),
    adjust: str = Query("", description="forward/backward for 前复权/后复权"),
):
    try:
        data = await ths_provider.get_klines(code, interval, count, adjust)
        return success_response(data)
    except Exception as e:
        return error_response("THS_KLINES_FAILED", str(e))


@router.get("/intraday")
async def get_intraday(code: str = Query(..., description="THSCODE")):
    try:
        data = await ths_provider.get_intraday(code)
        return success_response(data)
    except Exception as e:
        return error_response("THS_INTRADAY_FAILED", str(e))


@router.get("/depth")
async def get_depth(codes: str = Query(..., description="Comma-separated THSCODEs")):
    try:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        data = await ths_provider.get_depth(code_list)
        return success_response(data)
    except Exception as e:
        return error_response("THS_DEPTH_FAILED", str(e))


@router.get("/big_order")
async def get_big_order(code: str = Query(..., description="THSCODE")):
    try:
        data = await ths_provider.get_big_order_flow(code)
        return success_response(data)
    except Exception as e:
        return error_response("THS_BIG_ORDER_FAILED", str(e))


@router.get("/auction/anomaly")
async def get_auction_anomaly(market: str = Query("USHA", description="USHA or USZA")):
    try:
        data = await ths_provider.get_call_auction_anomaly(market)
        return success_response(data)
    except Exception as e:
        return error_response("THS_AUCTION_FAILED", str(e))


@router.get("/quote/cn")
async def get_quote_cn(
    codes: str = Query(..., description="Comma-separated THSCODEs"),
    query_key: str = Query("基础数据", description="基础数据/扩展1/扩展2/汇总"),
):
    try:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        data = await ths_provider.get_market_data_cn(code_list, query_key)
        return success_response(data)
    except Exception as e:
        return error_response("THS_QUOTE_CN_FAILED", str(e))


@router.get("/quote/hk")
async def get_quote_hk(
    code: str = Query(..., description="THSCODE, e.g. UHKG00700"),
    query_key: str = Query("基础数据"),
):
    try:
        data = await ths_provider.get_market_data_hk(code, query_key)
        return success_response(data)
    except Exception as e:
        return error_response("THS_QUOTE_HK_FAILED", str(e))


@router.get("/quote/us")
async def get_quote_us(
    code: str = Query(..., description="THSCODE, e.g. UNQQAAPL"),
    query_key: str = Query("基础数据"),
):
    try:
        data = await ths_provider.get_market_data_us(code, query_key)
        return success_response(data)
    except Exception as e:
        return error_response("THS_QUOTE_US_FAILED", str(e))


@router.get("/index")
async def get_index(codes: str = Query(..., description="Comma-separated index THSCODEs")):
    try:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        data = await ths_provider.get_market_data_index(code_list)
        return success_response(data)
    except Exception as e:
        return error_response("THS_INDEX_FAILED", str(e))


@router.get("/industry")
async def get_industry():
    try:
        data = await ths_provider.get_ths_industry()
        return success_response(data)
    except Exception as e:
        return error_response("THS_INDUSTRY_FAILED", str(e))


@router.get("/concept")
async def get_concept():
    try:
        data = await ths_provider.get_ths_concept()
        return success_response(data)
    except Exception as e:
        return error_response("THS_CONCEPT_FAILED", str(e))


@router.get("/block/quote")
async def get_block_quote(
    code: str = Query(..., description="板块 THSCODE, e.g. URFI883404"),
    query_key: str = Query("基础数据", description="基础数据/扩展"),
):
    try:
        data = await ths_provider.get_market_data_block(code, query_key)
        return success_response(data)
    except Exception as e:
        return error_response("THS_BLOCK_FAILED", str(e))


@router.get("/block/constituents")
async def get_block_constituents(code: str = Query(..., description="板块 THSCODE")):
    try:
        data = await ths_provider.get_block_constituents(code)
        return success_response(data)
    except Exception as e:
        return error_response("THS_CONSTITUENTS_FAILED", str(e))


@router.get("/wencai")
async def wencai(query: str = Query(..., description="问财自然语言查询")):
    try:
        data = await ths_provider.wencai_nlp(query)
        return success_response(data)
    except Exception as e:
        return error_response("THS_WENCAI_FAILED", str(e))


@router.get("/news")
async def get_news():
    try:
        data = await ths_provider.get_news()
        return success_response(data)
    except Exception as e:
        return error_response("THS_NEWS_FAILED", str(e))


@router.get("/forex")
async def get_forex(
    code: str = Query(..., description="THSCODE, e.g. UFXBGBPUSD"),
    query_key: str = Query("基础数据"),
):
    try:
        data = await ths_provider.get_market_data_forex(code, query_key)
        return success_response(data)
    except Exception as e:
        return error_response("THS_FOREX_FAILED", str(e))


@router.get("/future")
async def get_future(
    code: str = Query(..., description="THSCODE, e.g. UCFSAU2506"),
    query_key: str = Query("基础数据"),
):
    try:
        data = await ths_provider.get_market_data_future(code, query_key)
        return success_response(data)
    except Exception as e:
        return error_response("THS_FUTURE_FAILED", str(e))
