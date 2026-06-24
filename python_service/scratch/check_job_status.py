from python_service.app.db.database import build_session_factory, DATABASE_URL
from sqlmodel import select
from python_service.app.models import AnalysisJob

session_factory = build_session_factory(DATABASE_URL)
with session_factory() as session:
    statement = select(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(5)
    jobs = session.exec(statement).all()
    for job in jobs:
        print(f"ID: {job.job_id} | Status: {job.status} | Created: {job.created_at} | Error: {job.error_message}")
