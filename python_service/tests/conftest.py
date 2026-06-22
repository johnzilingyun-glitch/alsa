import os
import sys

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set test database path before importing app code
test_db_path = os.path.join(project_root, "python_service", "data", "test_app.db")
os.environ["SQLITE_PATH"] = test_db_path
os.environ["API_TOKEN"] = "mock-token"

# Prevent double-loading of SQLModel tables.
# conftest imports via python_service.app.* while main.py imports via app.*.
# Without aliasing, Python sees two different module objects for the same code,
# causing "Table already defined" errors. Fix: import via python_service.app
# first, then alias all sub-modules so app.* resolves to the same objects.
import python_service.app  # noqa: E402

# Pre-import the sqlite module (and its models) under the python_service path
from python_service.app.db.database import engine  # noqa: E402, F401

# Now alias: app.* → python_service.app.*
if "app" not in sys.modules:
    sys.modules["app"] = python_service.app
for name in list(sys.modules.keys()):
    if name.startswith("python_service.app."):
        alias = "app." + name[len("python_service.app."):]
        if alias not in sys.modules:
            sys.modules[alias] = sys.modules[name]

import pytest  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlalchemy import text  # noqa: E402

TEST_API_TOKEN = "mock-token"


@pytest.fixture(autouse=True)
def _set_test_api_token():
    """Re-set API_TOKEN before every test.

    load_dotenv('.env.runtime', override=True) in llm_gateway/brain_manager
    overwrites the env var during module-level app imports.  This fixture
    ensures the correct token is in place when the test body runs.
    """
    os.environ["API_TOKEN"] = TEST_API_TOKEN


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize test database schema once for the session, clean up after session."""
    os.makedirs(os.path.dirname(test_db_path), exist_ok=True)
    SQLModel.metadata.create_all(engine)

    from python_service.app.db.database import _migrate_alert_postmortem, _migrate_analysis_lineage
    _migrate_alert_postmortem(engine)
    _migrate_analysis_lineage(engine)

    yield

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
        session.execute(text("PRAGMA foreign_keys = OFF;"))
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.execute(text(f"DELETE FROM {table.name};"))
        session.execute(text("PRAGMA foreign_keys = ON;"))
        session.commit()


@pytest.fixture
def session_factory():
    from python_service.app.db.database import session_factory as factory
    return factory
