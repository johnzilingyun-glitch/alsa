from typing import List, Optional, Callable
from sqlmodel import Session, select
from ..models import SearchAlert
from datetime import datetime

class AlertRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, symbol: str, name: str, market: str, entry_price: float, target_price: float, stop_loss: float, currency: str = "CNY") -> SearchAlert:
        with self.session_factory() as session:
            # Check if an active alert already exists for this symbol
            statement = select(SearchAlert).where(
                SearchAlert.symbol == symbol, 
                SearchAlert.market == market,
                SearchAlert.status == "active"
            )
            existing = session.exec(statement).first()
            
            if existing:
                # Update existing alert with new AI guidance
                existing.entry_price = entry_price
                existing.target_price = target_price
                existing.stop_loss = stop_loss
                existing.currency = currency
                existing.created_at = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing
            
            # Create new alert
            alert = SearchAlert(
                symbol=symbol, 
                name=name, 
                market=market, 
                entry_price=entry_price, 
                target_price=target_price, 
                stop_loss=stop_loss,
                currency=currency
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def list_active(self) -> List[SearchAlert]:
        with self.session_factory() as session:
            statement = select(SearchAlert).where(SearchAlert.status == "active").order_by(SearchAlert.created_at.desc())
            return session.exec(statement).all()

    def update_status(self, alert_id: int, status: str):
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if alert:
                alert.status = status
                session.add(alert)
                session.commit()

    def delete_by_id(self, alert_id: int):
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if alert:
                session.delete(alert)
                session.commit()
