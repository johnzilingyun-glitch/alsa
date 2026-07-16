from typing import Optional, Callable, List
from sqlmodel import Session, select
from ..models import AnalysisJob, AnalysisRun
from ...time_utils import utc_now

class JobRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, job_id: str, symbol: str, market: str, level: str = "standard", model: Optional[str] = None, snapshot_id: Optional[str] = None, user_id: str = "default_user") -> AnalysisJob:
        with self.session_factory() as session:
            job = AnalysisJob(
                job_id=job_id, 
                user_id=user_id,
                symbol=symbol, 
                market=market, 
                analysis_level=level,
                requested_model=model,
                snapshot_id=snapshot_id,
                status="queued"
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def get_by_id(self, job_id: str) -> Optional[AnalysisJob]:
        with self.session_factory() as session:
            return session.get(AnalysisJob, job_id)

    def update_status(self, job_id: str, status: str, result_payload: Optional[str] = None, error_message: Optional[str] = None):
        with self.session_factory() as session:
            job = session.get(AnalysisJob, job_id)
            if job:
                job.status = status
                if status == "running" and not job.started_at:
                    job.started_at = utc_now()
                if status in ("completed", "failed", "cancelled"):
                    job.finished_at = utc_now()
                if result_payload:
                    job.result_payload = result_payload
                if error_message:
                    job.error_message = error_message
                session.add(job)
                session.commit()

    def get_analysis_run(self, analysis_id: str) -> Optional[AnalysisRun]:
        with self.session_factory() as session:
            return session.get(AnalysisRun, analysis_id)

    def get_runs_by_job(self, job_id: str) -> List[AnalysisRun]:
        with self.session_factory() as session:
            statement = select(AnalysisRun).where(AnalysisRun.job_id == job_id)
            return session.exec(statement).all()

    def recover_orphaned_jobs(self) -> int:
        """Mark all queued/running jobs as failed on server startup.
        
        These jobs have lost their in-memory asyncio tasks due to a process restart
        and can never complete. Marking them as 'failed' lets the frontend stop
        polling and display an appropriate error.
        
        Returns the count of recovered (marked as failed) jobs.
        """
        with self.session_factory() as session:
            statement = select(AnalysisJob).where(
                AnalysisJob.status.in_(["queued", "running"])
            )
            orphaned_jobs = session.exec(statement).all()
            count = 0
            for job in orphaned_jobs:
                job.status = "failed"
                job.error_message = "服务器重启，分析任务丢失。请重新提交。"
                session.add(job)
                count += 1
            if count > 0:
                session.commit()
            return count

    def delete_by_job_id(self, job_id: str) -> bool:
        with self.session_factory() as session:
            job = session.get(AnalysisJob, job_id)
            if not job:
                return False
            runs = session.exec(select(AnalysisRun).where(AnalysisRun.job_id == job_id)).all()
            for run in runs:
                session.delete(run)
            artifacts = session.exec(select(AnalysisJob).where(AnalysisJob.job_id == job_id)).all()
            session.delete(job)
            session.commit()
            return True

    def list_completed_by_symbol(self, symbol: str, limit: int = 10) -> list:
        """Get completed analysis jobs for a given symbol, most recent first."""
        with self.session_factory() as session:
            statement = (
                select(AnalysisJob)
                .where(AnalysisJob.symbol == symbol, AnalysisJob.status == "completed")
                .order_by(AnalysisJob.finished_at.desc())
                .limit(limit)
            )
            return session.exec(statement).all()

    def find_recent_running(self, symbol: str, market: str, within_seconds: int = 60) -> Optional[str]:
        """Find a recently created running/queued job for the same symbol+market.
        Returns job_id if found, None otherwise. Used to deduplicate rapid-fire submits."""
        from datetime import timedelta
        from ...time_utils import utc_now
        cutoff = utc_now() - timedelta(seconds=within_seconds)
        with self.session_factory() as session:
            statement = (
                select(AnalysisJob)
                .where(
                    AnalysisJob.symbol == symbol,
                    AnalysisJob.market == market,
                    AnalysisJob.status.in_(["queued", "running"]),
                    AnalysisJob.created_at >= cutoff
                )
                .order_by(AnalysisJob.created_at.asc())
                .limit(1)
            )
            result = session.exec(statement).first()
            return result.job_id if result else None

    def has_any_running(self) -> bool:
        """Check if there are ANY running or queued jobs across the entire system."""
        with self.session_factory() as session:
            statement = select(AnalysisJob).where(AnalysisJob.status.in_(["queued", "running"])).limit(1)
            result = session.exec(statement).first()
            return result is not None

    def has_running_for_user(self, user_id: str) -> bool:
        """Check if a specific user already has an *actively progressing* job.

        A job only blocks a new submission while it is genuinely recent AND
        making progress. Stuck jobs are reclaimed (auto-failed) on a much
        shorter window than before so a crashed/orphaned job does not block
        the user for the full 60-minute safety net:
          - queued job never picked up  -> reclaim after 10 min
          - running job with no progress     -> reclaim after 30 min (started_at age)
          - any job older than 60 min          -> reclaim (hard safety net)
        """
        from datetime import timedelta
        from ...time_utils import utc_now

        now = utc_now()
        created_cutoff = now - timedelta(minutes=60)   # hard safety net
        queued_cutoff = now - timedelta(minutes=10)   # never picked up
        running_cutoff = now - timedelta(minutes=30)   # started but stuck

        with self.session_factory() as session:
            statement = select(AnalysisJob).where(
                AnalysisJob.user_id == user_id,
                AnalysisJob.status.in_(["queued", "running"]),
            )
            active = session.exec(statement).all()

            blocking = False
            reclaimed = []
            for job in active:
                # Hard safety net: anything older than 60 min is reclaimed.
                if job.created_at < created_cutoff:
                    reclaimed.append(job)
                    continue
                if job.status == "queued":
                    # Only block while the queue slot is still fresh; otherwise
                    # it was never consumed by a worker and should be reclaimed.
                    if job.created_at >= queued_cutoff:
                        blocking = True
                    else:
                        reclaimed.append(job)
                else:  # running
                    # Block only if it actually started recently. A running job
                    # whose start is stale means the worker crashed mid-flight.
                    if job.started_at and job.started_at >= running_cutoff:
                        blocking = True
                    else:
                        reclaimed.append(job)

            for old_job in reclaimed:
                old_job.status = "failed"
                old_job.error_message = "任务超时（等待 API Key 或运行超过时限），请重新提交。"
                session.add(old_job)
            if reclaimed:
                session.commit()

            return blocking
