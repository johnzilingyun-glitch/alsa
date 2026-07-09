import asyncio
import traceback
import sys
import os
from app.db.database import session_factory, init_db
from app.services.analysis_job_service import AnalysisJobService
from app.db.repositories.job_repo import JobRepository
from app.services.market_snapshot_service import MarketSnapshotService
from app.lake.parquet_store import ParquetMarketStore

async def main():
    init_db()
    
    # Create a job record first so update_status works
    with session_factory() as session:
        from app.db.models import AnalysisJob
        job = AnalysisJob(
            job_id="test_job_999",
            symbol="000792",
            market="A-Share",
            requested_model="deepseek-chat",
            status="queued"
        )
        session.merge(job)
        session.commit()

    repo = JobRepository(session_factory)
    store = ParquetMarketStore("data/lake")
    snapshot = MarketSnapshotService(store)
    service = AnalysisJobService(repo, snapshot)
    
    ds_key = os.getenv("DEEPSEEK_API_KEY")
    print("Using DeepSeek API key:", ds_key[:10] if ds_key else None)
    
    # Trigger run_job directly so we can catch and print the traceback
    try:
        await service._run_job(
            job_id="test_job_999",
            symbol="000792",
            market="A-Share",
            config={
                "language": "zh-CN",
                "model": "deepseek-chat",
                "deepseekApiKey": ds_key
            },
            verification_mode="quick"
        )
    except Exception as e:
        print("CATCHED EXCEPTION IN TEST_JOB_FAIL:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
