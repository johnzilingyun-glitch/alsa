from python_service.app.db.sqlite import build_session_factory, DATABASE_URL
from python_service.app.db.repositories.job_repo import JobRepository
from sqlmodel import Session, select
from python_service.app.models import AnalysisJob
import json

session_factory = build_session_factory(DATABASE_URL)
with session_factory() as session:
    statement = select(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(5)
    jobs = session.exec(statement).all()
    for job in jobs:
        print(f"ID: {job.job_id} | Status: {job.status} | Created: {job.created_at} | Error: {job.error_message}")
