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
    
    service.set_api_key("gemini", "dummy_key")
    
    job_id = await service.start_job("AAPL", "US-Share", user_id="test_user")
    
    while True:
        job = service.get_status(job_id)
        if job.status in ["completed", "failed", "cancelled"]:
            print("Status:", job.status)
            print("Error:", job.error_message)
            if job.error_message:
                print("Job record:", job.model_dump())
            break
        await asyncio.sleep(1)

asyncio.run(main())
