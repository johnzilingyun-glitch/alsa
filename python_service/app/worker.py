import os
import asyncio
from celery import Celery
import logging

logger = logging.getLogger(__name__)

# Initialize Celery app
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "alsa_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=4
)

@celery_app.task(name="app.worker.run_analysis_task", bind=True)
def run_analysis_task(self, job_id: str, symbol: str, market: str, config: dict = None):
    """
    Celery wrapper task for running the ALSA async analysis workflow.
    """
    from app.services.analysis_job_service import analysis_job_service
    from app.db.database import session_factory
    
    logger.info(f"[Celery] Starting analysis job {job_id} for {symbol} on {market}")
    
    # Run the async job directly
    try:
        # Check database connection or anything required
        asyncio.run(analysis_job_service._run_job(job_id, symbol, market, config))
        logger.info(f"[Celery] Finished analysis job {job_id}")
    except Exception as e:
        logger.error(f"[Celery] Error in job {job_id}: {str(e)}", exc_info=True)
        # Update job status as failed
        with session_factory() as session:
            from app.db.repositories.job_repo import JobRepository
            repo = JobRepository(session)
            repo.update_status(job_id, "failed", error_message=str(e))
        raise
