import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from python_service.app.db.sqlite import session_factory
from python_service.app.db.models import AnalysisJob
from sqlmodel import select

try:
    with session_factory() as session:
        statement = select(AnalysisJob).order_by(AnalysisJob.created_at.desc())
        job = session.exec(statement).first()
        if job:
            print(f"Latest Job ID: {job.job_id}")
            print(f"Market: {job.market}")
            print(f"Status: {job.status}")
            print(f"Created At: {job.created_at}")
        else:
            print("No jobs found.")
except Exception as e:
    print(f"Error: {e}")
