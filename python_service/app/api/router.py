from fastapi import APIRouter
from .analysis import router as analysis_router
from .market import router as market_router
from .alerts import router as alerts_router
from .watchlist import router as watchlist_router
from .journal import router as journal_router
from .brain import router as brain_router
from .technicals import router as technicals_router
from .screening import router as screening_router
from .sector import router as sector_router
from .institutional import router as institutional_router
from .mock_trading import router as mock_trading_router
from .reflections import router as reflections_router
from .trade_intents import router as trade_intents_router
from .stock import router as stock_router
from .predictions import router as predictions_router
from .ths import router as ths_router

api_router = APIRouter()
api_router.include_router(analysis_router)
api_router.include_router(market_router)
api_router.include_router(alerts_router)
api_router.include_router(watchlist_router)
api_router.include_router(journal_router)
api_router.include_router(brain_router)
api_router.include_router(technicals_router)
api_router.include_router(screening_router)
api_router.include_router(sector_router)
api_router.include_router(institutional_router)
api_router.include_router(mock_trading_router)
api_router.include_router(reflections_router)
api_router.include_router(trade_intents_router)
api_router.include_router(stock_router)
api_router.include_router(predictions_router)
api_router.include_router(ths_router)
