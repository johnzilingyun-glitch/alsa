"""Celery Worker — distributed task queue for ALSA analysis jobs.

Provides reliable async job execution with:
- Task acknowledgment after completion
- Retry with exponential backoff
- Soft/hard time limits
- Graceful degradation when Redis is unavailable
"""
import os
import asyncio
import logging
from celery import Celery

logger = logging.getLogger(__name__)

# Initialize Celery app
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "alsa_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task behavior
    task_track_started=True,
    task_acks_late=True,  # Ack after completion, not before
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker
    # Time limits
    task_soft_time_limit=600,   # 10 min soft limit (raises SoftTimeLimitExceeded)
    task_time_limit=900,        # 15 min hard limit (kills worker)
    # Retry policy
    task_default_retry_delay=60,
    task_max_retries=3,
    # Concurrency
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "2")),
    worker_max_tasks_per_child=100,  # Recycle workers after 100 tasks
    # Result settings
    result_expires=3600,  # Results expire after 1 hour
)

# Health check
celery_app.conf.beat_schedule = {}


@celery_app.task(name="app.worker.run_analysis_task", bind=True, max_retries=3)
def run_analysis_task(self, job_id: str, symbol: str, market: str, config: dict = None):
    """
    Celery task for running ALSA analysis workflow.
    
    Features:
    - Automatic retry on transient failures
    - Proper error handling and job status updates
    - Configurable timeout
    """
    from main import get_analysis_job_service
    from app.db.database import session_factory

    logger.info(f"[Celery] Starting analysis job {job_id} for {symbol} ({market})")

    try:
        service = get_analysis_job_service()
        asyncio.run(service._run_job(job_id, symbol, market, config))
        logger.info(f"[Celery] Completed analysis job {job_id}")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Celery] Job {job_id} failed: {error_msg}")

        # Update job status as failed
        try:
            with session_factory() as session:
                from app.db.repositories.job_repo import JobRepository
                repo = JobRepository(session)
                repo.update_status(job_id, "failed", error_message=error_msg)
        except Exception as db_err:
            logger.error(f"[Celery] Failed to update job status: {db_err}")

        # Retry on transient errors
        if any(code in error_msg for code in ["429", "503", "timeout", "connection"]):
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        raise


@celery_app.task(name="app.worker.run_sector_analysis_task", bind=True, max_retries=3)
def run_sector_analysis_task(
    self,
    job_id: str,
    sector_name: str,
    model: str = None,
    config: dict = None,
    target_date: str = None,
    level: str = "sector",
    pipeline_version: str = "production"
):
    """
    Celery task for running sector-level multi-expert analysis workflow.
    """
    from app.db.repositories.job_repo import JobRepository
    from app.db.database import session_factory

    if pipeline_version == "development":
        from app.services.serenity_graph import SerenityGraphService
        service = SerenityGraphService(JobRepository(session_factory))
    else:
        from app.services.sector_analysis_service import SectorAnalysisService
        service = SectorAnalysisService(JobRepository(session_factory))

    logger.info(f"[Celery] Starting sector analysis job {job_id} for {sector_name} ({level}, pipeline={pipeline_version})")

    try:
        asyncio.run(service._run_sector_job(job_id, sector_name, model=model, config=config, target_date=target_date, level=level))
        logger.info(f"[Celery] Completed sector analysis job {job_id}")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Celery] Sector job {job_id} failed: {error_msg}")

        # Update job status as failed
        try:
            with session_factory() as session:
                from app.db.repositories.job_repo import JobRepository
                repo = JobRepository(session)
                repo.update_status(job_id, "failed", error_message=error_msg)
        except Exception as db_err:
            logger.error(f"[Celery] Failed to update job status: {db_err}")

        # Retry on transient errors
        if any(code in error_msg for code in ["429", "503", "timeout", "connection"]):
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        raise


@celery_app.task(name="app.worker.health_check")
def health_check():
    """Simple health check task."""
    return {"status": "ok", "worker": "alsa_worker"}

