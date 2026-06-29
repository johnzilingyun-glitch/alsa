import os
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import event
import sqlite3

# Import table models once so SQLModel.metadata is populated
from . import models as _models  # noqa: F401

# Unified Institutional Database Path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))

try:
    from dotenv import load_dotenv
    env_path = os.path.join(root_dir, ".env.runtime")
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass

DEFAULT_DB_PATH = os.path.join(root_dir, "data", "app.db")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fallback to SQLite if no DB URL is provided
    sqlite_path = os.getenv("SQLITE_PATH", DEFAULT_DB_PATH)
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    DATABASE_URL = f"sqlite:///{sqlite_path}"

# For PostgreSQL, we might need pool configurations
is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    event.listen(engine, "connect", _set_sqlite_pragma)
else:
    # PostgreSQL settings
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True
    )

def init_db():
    SQLModel.metadata.create_all(engine)
    # Legacy migration scripts logic (if needed, though SQLModel creates all columns)
    if is_sqlite:
        _migrate_alert_postmortem(engine)
        _migrate_alert_monitoring(engine)
        _migrate_analysis_lineage(engine)
        _migrate_mocktrade(engine)
        _migrate_agent_memory(engine)
        _migrate_user_last_login(engine)

def get_session():
    with Session(engine) as session:
        yield session

def build_session_factory(db_path: str):
    """Used for testing and initialization"""
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    
    def _test_set_sqlite_pragma(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
            
    event.listen(test_engine, "connect", _test_set_sqlite_pragma)
    SQLModel.metadata.create_all(test_engine)
    return lambda: Session(test_engine)

session_factory = lambda: Session(engine)

def _migrate_alert_postmortem(eng):
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

def _migrate_agent_memory(eng):
    """Create agent_memory table if it doesn't exist."""
    import sqlite3
    db_path = str(eng.url).replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            memory_id VARCHAR PRIMARY KEY,
            symbol VARCHAR,
            role VARCHAR,
            analysis_summary TEXT,
            key_conclusions TEXT DEFAULT '',
            confidence REAL DEFAULT 0.5,
            outcome VARCHAR DEFAULT 'unknown',
            created_at TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_memory_symbol ON agent_memory(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_memory_role ON agent_memory(role)")
    conn.commit()
    conn.close()

def _migrate_mocktrade(eng):
    import sqlite3
    db_path = str(eng.url).replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check MockTrade
    cursor.execute("PRAGMA table_info(mocktrade)")
    existing = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("commission", "REAL"),
        ("position_size_pct", "REAL"),
        ("realized_pnl", "REAL"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            try:
                cursor.execute(f"ALTER TABLE mocktrade ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass
                
    # Check MockAccount
    cursor.execute("PRAGMA table_info(mockaccount)")
    existing_acc = {row[1] for row in cursor.fetchall()}
    new_cols_acc = [
        ("purchasing_power", "REAL DEFAULT 1000000.0"),
        ("maintenance_margin", "REAL DEFAULT 0.0"),
    ]
    for col_name, col_type in new_cols_acc:
        if col_name not in existing_acc:
            try:
                cursor.execute(f"ALTER TABLE mockaccount ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()

def _migrate_alert_monitoring(eng):
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

def _migrate_user_last_login(eng):
    """Add last_login column to user table if missing."""
    import sqlite3
    db_path = str(eng.url).replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user)")
    existing = {row[1] for row in cursor.fetchall()}
    if "last_login" not in existing:
        cursor.execute("ALTER TABLE user ADD COLUMN last_login TIMESTAMP")
    conn.commit()
    conn.close()

