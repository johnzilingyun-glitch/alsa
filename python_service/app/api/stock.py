from fastapi import APIRouter

from ..services.market_data_service import market_data_service

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/comprehensive_financials")
async def get_comprehensive_financials(symbol: str, market: str = "A-Share"):
    data = await market_data_service.get_financial_summary(symbol, market)
    if isinstance(data, dict) and data.get("error"):
        return {"success": False, "error": data.get("error"), "data": data}
    return {"success": True, "data": data}
