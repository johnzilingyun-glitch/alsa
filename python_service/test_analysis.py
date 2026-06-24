import asyncio
from app.db.database import session_factory
from app.services.analysis_job_service import AnalysisJobService
from app.db.repositories.job_repo import JobRepository
from app.services.market_snapshot_service import MarketSnapshotService
from app.lake.parquet_store import ParquetMarketStore

async def main():
    session = session_factory()
    repo = JobRepository(session)
    store = ParquetMarketStore("data/lake")
    snapshot = MarketSnapshotService(store)
    service = AnalysisJobService(repo, snapshot)
    try:
        job_id = await service.start_job("AAPL", "US-Share", user_id="test_user")
        print(f"Success: {job_id}")
    except Exception:
        import traceback
        traceback.print_exc()

asyncio.run(main())
