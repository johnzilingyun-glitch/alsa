from typing import List, Optional, Callable
from sqlmodel import Session, select
from ..models import SearchAlert
from ...time_utils import utc_now

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
                existing.created_at = utc_now()
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

    def record_postmortem(self, alert_id: str, exit_price: float, outcome_category: str,
                          mae_pct: float = None, mfe_pct: float = None,
                          notes: str = None, decision_quality: int = None) -> Optional[SearchAlert]:
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if not alert:
                return None
            alert.exit_price = exit_price
            alert.exit_date = utc_now()
            alert.outcome_category = outcome_category
            if alert.entry_price and alert.entry_price > 0:
                alert.realized_return_pct = round((exit_price - alert.entry_price) / alert.entry_price * 100, 2)
            alert.mae_pct = mae_pct
            alert.mfe_pct = mfe_pct
            alert.postmortem_notes = notes
            alert.decision_quality_score = decision_quality
            alert.status = "closed"
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def list_closed(self) -> List[SearchAlert]:
        with self.session_factory() as session:
            statement = select(SearchAlert).where(
                SearchAlert.status == "closed"
            ).order_by(SearchAlert.exit_date.desc())
            return session.exec(statement).all()

    def update_thesis(self, alert_id: str, thesis: str = None, invalidation_criteria: str = None,
                      thesis_stage: str = None, lessons_learned: str = None) -> Optional[SearchAlert]:
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if not alert:
                return None
            if thesis is not None:
                alert.thesis = thesis
            if invalidation_criteria is not None:
                alert.invalidation_criteria = invalidation_criteria
            if thesis_stage is not None:
                alert.thesis_stage = thesis_stage
            if lessons_learned is not None:
                alert.lessons_learned = lessons_learned
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def list_monitored(self) -> List[SearchAlert]:
        """List all alerts with monitoring enabled and status active."""
        with self.session_factory() as session:
            statement = select(SearchAlert).where(
                SearchAlert.monitoring_enabled == True,
                SearchAlert.status == "active"
            )
            return session.exec(statement).all()

    def enable_monitoring(self, alert_id: str, feishu_webhook_url: str = None,
                          step_in_plan: str = None, exit_rules: str = None,
                          thesis: str = None, invalidation_criteria: str = None) -> Optional[SearchAlert]:
        """Enable signal monitoring for an alert."""
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if not alert:
                return None
            alert.monitoring_enabled = True
            if feishu_webhook_url:
                alert.feishu_webhook_url = feishu_webhook_url
            if step_in_plan:
                alert.step_in_plan = step_in_plan
            if exit_rules:
                alert.exit_rules = exit_rules
            if thesis:
                alert.thesis = thesis
            if invalidation_criteria:
                alert.invalidation_criteria = invalidation_criteria
            alert.thesis_stage = "WATCHING"
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def disable_monitoring(self, alert_id: str) -> Optional[SearchAlert]:
        """Disable signal monitoring for an alert."""
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if not alert:
                return None
            alert.monitoring_enabled = False
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def update_check_state(self, alert_id: str, last_price: float):
        """Update the last check time and price for an alert."""
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if alert:
                alert.last_checked_at = utc_now()
                alert.last_price = last_price
                session.add(alert)
                session.commit()

    def mark_triggered(self, alert_id: str, trigger_type: str, price: float):
        """Mark an alert as triggered."""
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if alert:
                alert.status = "triggered"
                alert.trigger_type = trigger_type
                alert.triggered_at = utc_now()
                alert.last_price = price
                alert.monitoring_enabled = False  # Stop monitoring after trigger
                session.add(alert)
                session.commit()

    def increment_notify_count(self, alert_id: str):
        """Increment the notification counter."""
        with self.session_factory() as session:
            alert = session.get(SearchAlert, alert_id)
            if alert:
                alert.notify_count = (alert.notify_count or 0) + 1
                session.add(alert)
                session.commit()
