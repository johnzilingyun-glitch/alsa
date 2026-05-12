from typing import List, Callable
from sqlmodel import Session, select
from ..models import JournalEntry

class JournalRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, **data) -> JournalEntry:
        with self.session_factory() as session:
            entry = JournalEntry(**data)
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def list_entries(self) -> List[JournalEntry]:
        with self.session_factory() as session:
            statement = select(JournalEntry).order_by(JournalEntry.created_at.desc())
            return session.exec(statement).all()

    def pending_reviews(self) -> List[JournalEntry]:
        # Simple placeholder for "pending reviews" logic
        with self.session_factory() as session:
            statement = select(JournalEntry).order_by(JournalEntry.created_at.desc())
            return session.exec(statement).all()
