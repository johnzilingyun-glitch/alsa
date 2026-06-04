import os
import sys

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set test database path before importing app code
test_db_path = os.path.join(project_root, "python_service", "data", "test_app.db")
os.environ["SQLITE_PATH"] = test_db_path

import pytest
from sqlmodel import SQLModel
from sqlalchemy import text
from python_service.app.db.sqlite import engine

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize test database schema once for the session, clean up after session."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(test_db_path), exist_ok=True)
    # Initialize DB (creates all tables and runs migration logic)
    SQLModel.metadata.create_all(engine)
    
    # Run the same migration run in production init
    from python_service.app.db.sqlite import _migrate_alert_postmortem, _migrate_analysis_lineage
    _migrate_alert_postmortem(engine)
    _migrate_analysis_lineage(engine)
    
    yield
    
    # Cleanup database file after tests complete
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except Exception as e:
            print(f"Failed to remove test database: {e}")

@pytest.fixture(autouse=True)
def clean_database():
    """Truncate all tables before each test to ensure test isolation."""
    from sqlmodel import Session
    with Session(engine) as session:
        # Disable foreign key checks for SQLite truncation
        session.execute(text("PRAGMA foreign_keys = OFF;"))
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.execute(text(f"DELETE FROM {table.name};"))
        session.execute(text("PRAGMA foreign_keys = ON;"))
        session.commit()


@pytest.fixture
def session_factory():
    from python_service.app.db.sqlite import session_factory as factory
    return factory
