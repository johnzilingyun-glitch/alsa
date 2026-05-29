from typing import List, Optional
from sqlmodel import Session, select
from ..models import (
    MockAccount, MockPosition, MockTrade, MockAccountSnapshot, AnomalyLog,
    MARKET_DEFAULT_BALANCE, MARKET_CURRENCY,
)
from datetime import datetime


class MockTradingRepo:
    def __init__(self, session: Session):
        self.session = session

    # ── Account CRUD ──────────────────────────────────────────────

    def create_account(
        self,
        name: str,
        market: str = "A-Share",
        user_id: str = "default_user",
        initial_balance: Optional[float] = None,
    ) -> MockAccount:
        balance = initial_balance if initial_balance is not None else MARKET_DEFAULT_BALANCE.get(market, 1000000.0)
        currency = MARKET_CURRENCY.get(market, "CNY")
        account = MockAccount(
            name=name,
            user_id=user_id,
            market=market,
            currency=currency,
            initial_balance=balance,
            current_cash=balance,
        )
        self.session.add(account)
        self.session.commit()
        self.session.refresh(account)
        return account

    def get_account(self, account_id: str) -> Optional[MockAccount]:
        return self.session.get(MockAccount, account_id)

    def list_accounts(self, user_id: str = "default_user") -> List[MockAccount]:
        statement = select(MockAccount).where(MockAccount.user_id == user_id, MockAccount.status == "active")
        return list(self.session.exec(statement).all())

    def delete_account(self, account_id: str) -> bool:
        """Soft-delete by setting status to 'archived'."""
        account = self.get_account(account_id)
        if account:
            account.status = "archived"
            self.session.add(account)
            self.session.commit()
            return True
        return False

    def update_cash(self, account_id: str, delta: float) -> bool:
        account = self.get_account(account_id)
        if account:
            account.current_cash += delta
            self.session.add(account)
            self.session.commit()
            return True
        return False

    # ── Position CRUD ─────────────────────────────────────────────

    def get_position(self, account_id: str, symbol: str, market: str) -> Optional[MockPosition]:
        statement = select(MockPosition).where(
            MockPosition.account_id == account_id,
            MockPosition.symbol == symbol,
            MockPosition.market == market,
        )
        return self.session.exec(statement).first()

    def list_positions(self, account_id: str) -> List[MockPosition]:
        statement = select(MockPosition).where(MockPosition.account_id == account_id, MockPosition.shares > 0)
        return list(self.session.exec(statement).all())

    def upsert_position(self, account_id: str, symbol: str, market: str, shares: int, average_cost: float) -> MockPosition:
        position = self.get_position(account_id, symbol, market)
        if not position:
            position = MockPosition(
                account_id=account_id,
                symbol=symbol,
                market=market,
                shares=shares,
                average_cost=average_cost,
            )
        else:
            position.shares = shares
            position.average_cost = average_cost
            position.updated_at = datetime.utcnow()
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    # ── Trade Ledger ──────────────────────────────────────────────

    def record_trade(
        self,
        account_id: str,
        symbol: str,
        market: str,
        action: str,
        shares: int,
        execution_price: float,
        trigger_source: str,
        related_alert_id: Optional[str] = None,
        position_size_pct: Optional[float] = None,
        realized_pnl: Optional[float] = None,
    ) -> MockTrade:
        trade = MockTrade(
            account_id=account_id,
            symbol=symbol,
            market=market,
            action=action,
            shares=shares,
            execution_price=execution_price,
            trigger_source=trigger_source,
            related_alert_id=related_alert_id,
            position_size_pct=position_size_pct,
            realized_pnl=realized_pnl,
        )
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def list_trades(self, account_id: str, symbol: Optional[str] = None) -> List[MockTrade]:
        stmt = select(MockTrade).where(MockTrade.account_id == account_id)
        if symbol:
            stmt = stmt.where(MockTrade.symbol == symbol)
        stmt = stmt.order_by(MockTrade.timestamp.desc())  # type: ignore[union-attr]
        return list(self.session.exec(stmt).all())

    # ── Snapshot ──────────────────────────────────────────────────

    def save_snapshot(self, account_id: str, snapshot_date: str, total_equity: float, cash_balance: float, positions_market_value: float) -> MockAccountSnapshot:
        snap = MockAccountSnapshot(
            account_id=account_id,
            snapshot_date=snapshot_date,
            total_equity=total_equity,
            cash_balance=cash_balance,
            positions_market_value=positions_market_value,
        )
        self.session.add(snap)
        self.session.commit()
        self.session.refresh(snap)
        return snap

    def list_snapshots(self, account_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[MockAccountSnapshot]:
        stmt = select(MockAccountSnapshot).where(MockAccountSnapshot.account_id == account_id)
        if start_date:
            stmt = stmt.where(MockAccountSnapshot.snapshot_date >= start_date)
        if end_date:
            stmt = stmt.where(MockAccountSnapshot.snapshot_date <= end_date)
        stmt = stmt.order_by(MockAccountSnapshot.snapshot_date)  # type: ignore[union-attr]
        return list(self.session.exec(stmt).all())

    # ── Anomaly Log ──────────────────────────────────────────────

    def log_anomaly(self, account_id: str, event_type: str, magnitude_pct: float, symbol: Optional[str] = None, news_reasoning: Optional[str] = None) -> AnomalyLog:
        entry = AnomalyLog(
            account_id=account_id,
            symbol=symbol,
            event_type=event_type,
            magnitude_pct=magnitude_pct,
            news_reasoning=news_reasoning,
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def list_anomalies(self, account_id: str, symbol: Optional[str] = None) -> List[AnomalyLog]:
        stmt = select(AnomalyLog).where(AnomalyLog.account_id == account_id)
        if symbol:
            stmt = stmt.where(AnomalyLog.symbol == symbol)
        stmt = stmt.order_by(AnomalyLog.timestamp.desc())  # type: ignore[union-attr]
        return list(self.session.exec(stmt).all())
