
import sys
import os
import json
# Add project root to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from python_service.app.db.database import session_factory
from python_service.app.db.models import AnalysisJob
from sqlmodel import select

with session_factory() as session:
    statement = select(AnalysisJob).order_by(AnalysisJob.created_at.desc())
    job = session.exec(statement).first()
    if job:
        print(f"Job ID: {job.job_id}")
        payload = job.result_payload or {}
        discussion = payload.get("discussion", [])
        for m in discussion:
            start_content = m['content'][:50].replace('\n', ' ')
            print(f"Role: {m['role']} | Content Start: {start_content}")
