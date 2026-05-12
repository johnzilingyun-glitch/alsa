import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .app.api.router import api_router
from .app.db.sqlite import init_db, build_session_factory, DATABASE_URL
from .app.services.market_data_service import market_data_service
from .app.db.repositories.watchlist_repo import WatchlistRepository
from .app.db.repositories.alert_repo import AlertRepository
from .app.db.repositories.journal_repo import JournalRepository
from .app.services.analysis_job_service import AnalysisJobService
from .app.db.repositories.job_repo import JobRepository
from .app.services.market_snapshot_service import MarketSnapshotService
from .app.lake.parquet_store import ParquetMarketStore

app = FastAPI(title="ALSA Institutional Backend", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Singletons
session_factory = build_session_factory(DATABASE_URL)
parquet_store = ParquetMarketStore()
job_repo = JobRepository(session_factory)
watchlist_repo = WatchlistRepository(session_factory)
alert_repo = AlertRepository(session_factory)
journal_repo = JournalRepository(session_factory)
market_snapshot_service = MarketSnapshotService(parquet_store)
analysis_job_service = AnalysisJobService(job_repo, market_snapshot_service)

# Dependency helpers
def get_analysis_job_service():
    return analysis_job_service

def get_watchlist_repo():
    return watchlist_repo

def get_alert_repo():
    return alert_repo

def get_journal_repo():
    return journal_repo

@app.on_event("startup")
async def startup_event():
    # Initialize Database
    init_db()
    
    # Recover orphaned jobs from previous crash/restart
    analysis_job_service.recover_orphaned_jobs()
    
    # Precompute loop for watchlist
    async def precompute_loop():
        while True:
            try:
                items = watchlist_repo.list_items()
                for item in items:
                    await market_data_service.precompute_financial_summary(item.symbol, item.market)
                await asyncio.sleep(300) # Every 5 minutes
            except Exception as e:
                print(f"Precompute loop error: {e}")
                await asyncio.sleep(60)

    asyncio.create_task(precompute_loop())

# Include the unified API router
app.include_router(api_router, prefix="/api")

@app.get("/api/health")
async def health_check():
    return {
        "success": True,
        "status": "ok",
        "service": "ALSA Institutional Backend"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("python_service.main:app", host="127.0.0.1", port=8001, reload=True)
