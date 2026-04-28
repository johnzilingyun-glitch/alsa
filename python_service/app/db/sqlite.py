from sqlmodel import SQLModel, create_engine, Session
import os

DATABASE_URL = os.getenv("SQLITE_PATH", "python_service/data/app_v3.db")
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
