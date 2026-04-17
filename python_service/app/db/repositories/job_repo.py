from typing import Optional, Callable
from sqlmodel import Session, select
from ..models import AnalysisJob

class JobRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, job_id: str, symbol: str, market: str) -> AnalysisJob:
        with self.session_factory() as session:
            job = AnalysisJob(
                job_id=job_id, 
                symbol=symbol, 
                market=market, 
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
