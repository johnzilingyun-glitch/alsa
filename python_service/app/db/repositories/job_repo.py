from typing import Optional, Callable, List
from sqlmodel import Session, select
from ..models import AnalysisJob, AnalysisRun

class JobRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, job_id: str, symbol: str, market: str, level: str = "standard", model: Optional[str] = None, snapshot_id: Optional[str] = None) -> AnalysisJob:
        with self.session_factory() as session:
            job = AnalysisJob(
                job_id=job_id, 
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

    def update_status(self, job_id: str, status: str, result_payload: Optional[str] = None):
        with self.session_factory() as session:
            job = session.get(AnalysisJob, job_id)
            if job:
                job.status = status
                if result_payload:
                    job.result_payload = result_payload
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
