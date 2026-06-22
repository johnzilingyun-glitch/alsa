from app.db.database import session_factory, init_db
from app.db.repositories.job_repo import JobRepository

init_db()
repo = JobRepository(session_factory)
result = repo.has_running_for_user("test_user")
print("Has running:", result)
