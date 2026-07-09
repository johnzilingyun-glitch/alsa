import asyncio
from app.db.database import session_factory, init_db
from app.services.analysis_job_service import AnalysisJobService
from app.db.repositories.job_repo import JobRepository
from app.services.market_snapshot_service import MarketSnapshotService
from app.lake.parquet_store import ParquetMarketStore

async def main():
    init_db()
    repo = JobRepository(session_factory)
    store = ParquetMarketStore("data/lake")
    snapshot = MarketSnapshotService(store)
    service = AnalysisJobService(repo, snapshot)
    
    # Patch to avoid hanging
    async def mock_wait(self, job_id, provider, config):
        return "fake_key"
    AnalysisJobService._wait_for_api_key = mock_wait
    
    try:
        await service._run_job('test_job_1', 'MSFT', 'US-Share')
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
