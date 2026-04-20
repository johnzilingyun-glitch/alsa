from fastapi import APIRouter
from .analysis import router as analysis_router
from .market import router as market_router
from .alerts import router as alerts_router
from .watchlist import router as watchlist_router
from .journal import router as journal_router
from .admin import router as admin_router
from .brain import router as brain_router

api_router = APIRouter()
api_router.include_router(analysis_router)
api_router.include_router(market_router)
api_router.include_router(alerts_router)
api_router.include_router(watchlist_router)
api_router.include_router(journal_router)
api_router.include_router(admin_router)
api_router.include_router(brain_router)
