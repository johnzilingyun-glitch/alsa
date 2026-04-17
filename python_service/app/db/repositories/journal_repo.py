from typing import List, Callable
from sqlmodel import Session, select
from ..models import DecisionEntry

class JournalRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, **data) -> DecisionEntry:
        with self.session_factory() as session:
            entry = DecisionEntry(**data)
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def list_entries(self) -> List[DecisionEntry]:
        with self.session_factory() as session:
            statement = select(DecisionEntry).order_by(DecisionEntry.created_at.desc())
            return session.exec(statement).all()

    def pending_reviews(self) -> List[DecisionEntry]:
        # Simple placeholder for "pending reviews" logic
        with self.session_factory() as session:
            statement = select(DecisionEntry).order_by(DecisionEntry.created_at.desc())
            return session.exec(statement).all()
