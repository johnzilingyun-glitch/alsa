from datetime import datetime, timedelta

from sqlmodel import Session

from python_service.app.db.database import engine
from python_service.app.db.models import AnalysisJob
from python_service.app.db.repositories.job_repo import JobRepository
from python_service.app.time_utils import utc_now


def _make_job(job_id, user_id, status, age_minutes, started_age_minutes=None):
    created = utc_now() - timedelta(minutes=age_minutes)
    started = None
    if started_age_minutes is not None:
        started = utc_now() - timedelta(minutes=started_age_minutes)
    job = AnalysisJob(
        job_id=job_id,
        user_id=user_id,
        symbol="600519",
        market="A-Share",
        status=status,
        created_at=created,
        started_at=started,
    )
    with Session(engine) as session:
        session.add(job)
        session.commit()
    return job


def _repo():
    return JobRepository(lambda: Session(engine))


def test_recent_running_job_blocks():
    _make_job("j_active", "u1", "running", age_minutes=2, started_age_minutes=2)
    assert _repo().has_running_for_user("u1") is True


def test_recent_queued_job_blocks():
    _make_job("j_q", "u2", "queued", age_minutes=2)
    assert _repo().has_running_for_user("u2") is True


def test_stuck_queued_never_picked_up_does_not_block():
    # queued > 10 min but never consumed by a worker -> reclaimed, no block
    _make_job("j_q_stuck", "u3", "queued", age_minutes=25)
    assert _repo().has_running_for_user("u3") is False


def test_stuck_running_crashed_does_not_block():
    # running but started > 30 min ago -> worker crashed mid-flight, reclaimed
    _make_job("j_r_stuck", "u4", "running", age_minutes=45, started_age_minutes=45)
    assert _repo().has_running_for_user("u4") is False


def test_stuck_jobs_auto_failed():
    _make_job("j_q_stuck2", "u5", "queued", age_minutes=25)
    _make_job("j_r_stuck2", "u5", "running", age_minutes=45, started_age_minutes=45)
    _repo().has_running_for_user("u5")
    with Session(engine) as session:
        q = session.get(AnalysisJob, "j_q_stuck2")
        r = session.get(AnalysisJob, "j_r_stuck2")
        assert q.status == "failed"
        assert r.status == "failed"


def test_unrelated_user_not_blocked():
    _make_job("j_other", "u6", "running", age_minutes=1, started_age_minutes=1)
    assert _repo().has_running_for_user("someone_else") is False


def test_hard_safety_net_reclaims_old_job():
    # created > 60 min ago is reclaimed even if "running" with fresh started_at
    _make_job("j_old", "u7", "running", age_minutes=90, started_age_minutes=1)
    assert _repo().has_running_for_user("u7") is False
    with Session(engine) as session:
        assert session.get(AnalysisJob, "j_old").status == "failed"
