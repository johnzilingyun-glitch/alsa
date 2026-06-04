import os
from sqlmodel import SQLModel, create_engine, Session

# Import table models once so SQLModel.metadata is populated for every init path.
from . import models as _models  # noqa: F401

# Unified Institutional Database Path
current_dir = os.path.dirname(os.path.abspath(__file__))
# Navigate up to the project root (python_service/app/db -> python_service/app -> python_service -> root)
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
DEFAULT_DB_PATH = os.path.join(root_dir, "data", "app.db")

DATABASE_URL = os.getenv("SQLITE_PATH", DEFAULT_DB_PATH)
# Ensure directory exists
os.makedirs(os.path.dirname(DATABASE_URL), exist_ok=True)

engine = create_engine(f"sqlite:///{DATABASE_URL}", connect_args={"check_same_thread": False})

def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate_alert_postmortem(engine)
    _migrate_alert_monitoring(engine)
    _migrate_analysis_lineage(engine)

def get_session():
    with Session(engine) as session:
        yield session

def build_session_factory(db_path: str):
    """Used for testing and initialization"""
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)
    return lambda: Session(test_engine)

session_factory = lambda: Session(engine)


def _migrate_alert_postmortem(eng):
    """Add postmortem columns to searchalert table if they don't exist."""
    import sqlite3
    db_path = str(eng.url).replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(searchalert)")
    existing = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("exit_price", "REAL"),
        ("exit_date", "TIMESTAMP"),
        ("outcome_category", "VARCHAR"),
        ("realized_return_pct", "REAL"),
        ("mae_pct", "REAL"),
        ("mfe_pct", "REAL"),
        ("postmortem_notes", "VARCHAR"),
        ("decision_quality_score", "INTEGER"),
        ("thesis", "VARCHAR"),
        ("invalidation_criteria", "VARCHAR"),
        ("thesis_stage", "VARCHAR"),
        ("lessons_learned", "VARCHAR"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE searchalert ADD COLUMN {col_name} {col_type}")
    conn.commit()
    conn.close()


def _migrate_analysis_lineage(eng):
    import sqlite3
    db_path = str(eng.url).replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(analysisrun)")
    existing = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("prompt_version", "VARCHAR DEFAULT 'v1'"),
        ("model_provider", "VARCHAR DEFAULT 'unknown'"),
        ("model_name", "VARCHAR DEFAULT 'unknown'"),
        ("model_version", "VARCHAR"),
        ("schema_version", "VARCHAR DEFAULT 'analysis.v1'"),
        ("approval_state", "VARCHAR DEFAULT 'draft'"),
        ("human_reviewer", "VARCHAR"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE analysisrun ADD COLUMN {col_name} {col_type}")
    conn.commit()
    conn.close()


def _migrate_alert_monitoring(eng):
    """Add signal monitoring columns to searchalert table if they don't exist."""
    import sqlite3
    db_path = str(eng.url).replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(searchalert)")
    existing = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("monitoring_enabled", "BOOLEAN DEFAULT 0"),
        ("feishu_webhook_url", "VARCHAR"),
        ("last_checked_at", "TIMESTAMP"),
        ("last_price", "REAL"),
        ("trigger_type", "VARCHAR"),
        ("notify_count", "INTEGER DEFAULT 0"),
        ("step_in_plan", "VARCHAR"),
        ("exit_rules", "VARCHAR"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE searchalert ADD COLUMN {col_name} {col_type}")
    conn.commit()
    conn.close()
