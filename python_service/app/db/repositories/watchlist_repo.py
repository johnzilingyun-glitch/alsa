from typing import List, Optional, Callable
from sqlmodel import Session, select
from ..models import WatchlistItem

class WatchlistRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, symbol: str, name: str, market: str) -> WatchlistItem:
        with self.session_factory() as session:
            item = WatchlistItem(symbol=symbol, name=name, market=market)
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def list_items(self) -> List[WatchlistItem]:
        with self.session_factory() as session:
            statement = select(WatchlistItem).order_by(WatchlistItem.added_at.desc())
            return session.exec(statement).all()

    def delete_by_symbol(self, symbol: str, market: str):
        with self.session_factory() as session:
            statement = select(WatchlistItem).where(
                WatchlistItem.symbol == symbol, 
                WatchlistItem.market == market
            )
            item = session.exec(statement).first()
            if item:
                session.delete(item)
                session.commit()
