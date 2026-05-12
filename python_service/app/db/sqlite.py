import os
from sqlmodel import SQLModel, create_engine, Session

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

def get_session():
    with Session(engine) as session:
        yield session

def build_session_factory(db_path: str):
    """Used for testing and initialization"""
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)
    return lambda: Session(test_engine)

session_factory = lambda: Session(engine)
