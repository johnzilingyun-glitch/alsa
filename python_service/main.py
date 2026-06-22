import os

# Apply AkShare requests.Session keep-alive patch BEFORE any other imports
from app.utils.akshare_patch import *  # noqa: F401, F403

# Initialize structured logging first
from app.logging import setup_logging
setup_logging()

import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.security import get_allowed_origins, require_api_token
from app.api import backtest
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.db.database import init_db, session_factory
from app.services.market_data_service import market_data_service
from app.db.repositories.watchlist_repo import WatchlistRepository
from app.db.repositories.alert_repo import AlertRepository
from app.db.repositories.journal_repo import JournalRepository
from app.services.analysis_job_service import AnalysisJobService
from app.db.repositories.job_repo import JobRepository
from app.services.market_snapshot_service import MarketSnapshotService
from app.lake.parquet_store import ParquetMarketStore
from app.services.signal_monitor_service import SignalMonitorService
from app.services.prediction_service import PredictionService

# Institutional modules
from app.risk.kill_switch import KillSwitch
from app.risk.pre_trade import PreTradeRiskGateway
from app.observability.metrics import MetricsCollector
from app.observability.audit import AuditLogger, AuditAction
from app.prompting.version_registry import prompt_version_registry

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    analysis_job_service.recover_orphaned_jobs()

    async def precompute_loop():
        while True:
            try:
                items = watchlist_repo.list_items()
                for item in items:
                    await market_data_service.precompute_financial_summary(item.symbol, item.market)
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Precompute loop error: {e}")
                await asyncio.sleep(60)

    # Signal monitoring loop — checks prices every 60s during market hours
    async def signal_monitor_loop():
        await asyncio.sleep(10)  # Wait for startup
        await signal_monitor.monitor_loop(interval_seconds=60)

    # API key cache cleanup — clear stale keys every 5 minutes to prevent leakage
    async def api_key_cleanup_loop():
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            analysis_job_service._clear_stale_keys()

    task = asyncio.create_task(precompute_loop())
    monitor_task = asyncio.create_task(signal_monitor_loop())
    cleanup_task = asyncio.create_task(api_key_cleanup_loop())
    prediction_task = asyncio.create_task(PredictionService.run_accuracy_loop(interval_seconds=3600))
    try:
        yield
    finally:
        signal_monitor.stop()
        task.cancel()
        monitor_task.cancel()
        cleanup_task.cancel()
        prediction_task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        try:
            await prediction_task
        except asyncio.CancelledError:
            pass


from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.limiter import limiter

app = FastAPI(
    title="ALSA Institutional Backend", 
    version="1.0.0", 
    lifespan=lifespan,
    description="Institutional-grade Quantitative Analysis API with Multi-User Support",
    contact={"name": "Support", "email": "support@alsa.example.com"},
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def record_api_metrics(request: Request, call_next):
    """Record API latency and status for observability."""
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000
    metrics_collector.record("api_latency_ms", latency_ms, tags={
        "endpoint": request.url.path,
        "method": request.method,
        "status": str(response.status_code),
    })
    return response

# Initialize Singletons
# session_factory is imported from database.py
parquet_store = ParquetMarketStore()
job_repo = JobRepository(session_factory)
watchlist_repo = WatchlistRepository(session_factory)
alert_repo = AlertRepository(session_factory)
signal_monitor = SignalMonitorService(alert_repo)
journal_repo = JournalRepository(session_factory)
market_snapshot_service = MarketSnapshotService(parquet_store)
analysis_job_service = AnalysisJobService(job_repo, market_snapshot_service)

# Institutional singletons
kill_switch = KillSwitch()
risk_gateway = PreTradeRiskGateway()
metrics_collector = MetricsCollector()
audit_logger = AuditLogger()
prompt_registry = prompt_version_registry

# Dependency helpers
def get_analysis_job_service():
    return analysis_job_service

def get_watchlist_repo():
    return watchlist_repo

def get_alert_repo():
    return alert_repo

def get_journal_repo():
    return journal_repo

def get_kill_switch():
    return kill_switch

def get_risk_gateway():
    return risk_gateway

def get_metrics_collector():
    return metrics_collector

def get_audit_logger():
    return audit_logger

def get_prompt_registry():
    return prompt_registry


# Auth router (no API_TOKEN required — users authenticate via JWT)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# Admin router (no API_TOKEN required — protected by x-admin-token)
app.include_router(admin_router, prefix="/api")

# Include the unified API router
app.include_router(api_router, prefix="/api", dependencies=[Depends(require_api_token)])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"], dependencies=[Depends(require_api_token)])
app.include_router(health_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("python_service.main:app", host="127.0.0.1", port=8001, reload=True)
