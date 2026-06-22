from typing import List, Optional
from sqlmodel import Session, select
from ..models import (
    MockAccount, MockPosition, MockTrade, MockAccountSnapshot, AnomalyLog,
    PendingOrder, MARKET_DEFAULT_BALANCE, MARKET_CURRENCY,
)
from datetime import datetime
from ...time_utils import utc_now


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

    def merge_accounts(self, source_account_ids: List[str], target_account_id: str, total_cash_to_add: float, total_initial_balance_to_add: float):
        """Move all positions, trades, anomalies, and snapshots from source accounts to target account."""
        target_account = self.get_account(target_account_id)
        if not target_account:
            return False

        # Add converted cash and initial balance
        target_account.current_cash += total_cash_to_add
        target_account.initial_balance += total_initial_balance_to_add
        self.session.add(target_account)

        # Merge relationships
        for source_id in source_account_ids:
            # Positions: if target already has same symbol/market, merge shares and average cost
            stmt_pos = select(MockPosition).where(MockPosition.account_id == source_id)
            source_positions = self.session.exec(stmt_pos).all()
            for src_pos in source_positions:
                tgt_pos = self.get_position(target_account_id, src_pos.symbol, src_pos.market)
                if tgt_pos:
                    if src_pos.shares > 0:
                        new_shares = tgt_pos.shares + src_pos.shares
                        new_cost = ((tgt_pos.shares * tgt_pos.average_cost) + (src_pos.shares * src_pos.average_cost)) / new_shares
                        tgt_pos.shares = new_shares
                        tgt_pos.average_cost = new_cost
                        self.session.add(tgt_pos)
                    self.session.delete(src_pos)
                else:
                    src_pos.account_id = target_account_id
                    self.session.add(src_pos)

            # Trades
            stmt_trades = select(MockTrade).where(MockTrade.account_id == source_id)
            source_trades = self.session.exec(stmt_trades).all()
            for trade in source_trades:
                trade.account_id = target_account_id
                self.session.add(trade)

            # Anomalies
            stmt_anomalies = select(AnomalyLog).where(AnomalyLog.account_id == source_id)
            source_anomalies = self.session.exec(stmt_anomalies).all()
            for anomaly in source_anomalies:
                anomaly.account_id = target_account_id
                self.session.add(anomaly)

            # Snapshots
            stmt_snapshots = select(MockAccountSnapshot).where(MockAccountSnapshot.account_id == source_id)
            source_snapshots = self.session.exec(stmt_snapshots).all()
            for snapshot in source_snapshots:
                snapshot.account_id = target_account_id
                self.session.add(snapshot)
            
            # Archive source account
            src_acc = self.get_account(source_id)
            if src_acc:
                src_acc.status = "archived"
                self.session.add(src_acc)

        self.session.commit()
        self.session.refresh(target_account)
        return target_account


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
            position.updated_at = utc_now()
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        return position

    # ── Pending Orders CRUD ───────────────────────────────────────

    def create_pending_order(self, account_id: str, symbol: str, market: str, action: str, order_type: str, shares: int, target_price: float, stop_price: Optional[float] = None) -> PendingOrder:
        order = PendingOrder(
            account_id=account_id,
            symbol=symbol,
            market=market,
            action=action,
            order_type=order_type,
            shares=shares,
            target_price=target_price,
            stop_price=stop_price,
            status="pending"
        )
        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_pending_order(self, order_id: str) -> Optional[PendingOrder]:
        return self.session.get(PendingOrder, order_id)

    def list_pending_orders(self, account_id: str, symbol: Optional[str] = None, status: str = "pending") -> List[PendingOrder]:
        stmt = select(PendingOrder).where(PendingOrder.account_id == account_id, PendingOrder.status == status)
        if symbol:
            stmt = stmt.where(PendingOrder.symbol == symbol)
        stmt = stmt.order_by(PendingOrder.created_at.desc())  # type: ignore[union-attr]
        return list(self.session.exec(stmt).all())

    def update_pending_order_status(self, order_id: str, status: str) -> bool:
        order = self.get_pending_order(order_id)
        if order:
            order.status = status
            self.session.add(order)
            self.session.commit()
            return True
        return False

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
        commission: Optional[float] = None,
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
            commission=commission,
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

    def get_today_bought_shares(self, account_id: str, symbol: str, market: str) -> int:
        from datetime import datetime, time
        from ...time_utils import utc_now
        today_start = datetime.combine(utc_now().date(), time.min)
        stmt = select(MockTrade).where(
            MockTrade.account_id == account_id,
            MockTrade.symbol == symbol,
            MockTrade.market == market,
            MockTrade.action == "BUY",
            MockTrade.timestamp >= today_start
        )
        trades = self.session.exec(stmt).all()
        return sum(t.shares for t in trades)

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
