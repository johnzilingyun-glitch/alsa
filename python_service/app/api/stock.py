from fastapi import APIRouter

from ..services.market_data_service import market_data_service
from ..utils.responses import error_response, success_response

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/comprehensive_financials")
async def get_comprehensive_financials(symbol: str, market: str = "A-Share"):
    data = await market_data_service.get_financial_summary(symbol, market)
    if isinstance(data, dict) and data.get("error"):
        return error_response("FINANCIALS_FETCH_FAILED", data.get("error"), details=data)
    return success_response(data)
