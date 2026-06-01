"""
TDD Tests for the AI Mock Trading System.
Covers: DB CRUD, execution engine, signal-triggered auto-trade, anomaly detection, portfolio analytics.
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine
from python_service.app.db.models import MockAccount, MockPosition, MockTrade, MARKET_DEFAULT_BALANCE
from python_service.app.db.repositories.mock_trading_repo import MockTradingRepo
from python_service.app.services.mock_trading_service import MockTradingService


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(name="mem_session")
def mem_session_fixture():
    """In-memory SQLite session for fast, isolated tests."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="repo")
def repo_fixture(mem_session: Session):
    return MockTradingRepo(mem_session)


@pytest.fixture(name="service")
def service_fixture(mem_session: Session):
    return MockTradingService(mem_session)


# ═══════════════════════════════════════════════════════════════════
# Phase 1: Database CRUD
# ═══════════════════════════════════════════════════════════════════

class TestAccountCRUD:
    def test_create_a_share_account(self, repo: MockTradingRepo):
        acc = repo.create_account(name="A股测试", market="A-Share")
        assert acc.account_id.startswith("acc_")
        assert acc.market == "A-Share"
        assert acc.currency == "CNY"
        assert acc.initial_balance == 1_000_000.0
        assert acc.current_cash == 1_000_000.0

    def test_create_hk_account_default_balance(self, repo: MockTradingRepo):
        acc = repo.create_account(name="港股测试", market="HK-Share")
        assert acc.currency == "HKD"
        assert acc.initial_balance == 2_000_000.0

    def test_create_us_account_default_balance(self, repo: MockTradingRepo):
        acc = repo.create_account(name="US Test", market="US-Share")
        assert acc.currency == "USD"
        assert acc.initial_balance == 1_000_000.0

    def test_create_account_custom_balance(self, repo: MockTradingRepo):
        acc = repo.create_account(name="Custom", market="A-Share", initial_balance=500_000.0)
        assert acc.initial_balance == 500_000.0

    def test_list_accounts(self, repo: MockTradingRepo):
        repo.create_account(name="Acc1")
        repo.create_account(name="Acc2")
        assert len(repo.list_accounts()) == 2

    def test_user_separation(self, repo: MockTradingRepo):
        repo.create_account(name="User1_Acc1", user_id="user_1")
        repo.create_account(name="User1_Acc2", user_id="user_1")
        repo.create_account(name="User2_Acc1", user_id="user_2")
        
        user1_accs = repo.list_accounts(user_id="user_1")
        user2_accs = repo.list_accounts(user_id="user_2")
        
        assert len(user1_accs) == 2
        assert len(user2_accs) == 1
        assert all(a.user_id == "user_1" for a in user1_accs)
        assert all(a.user_id == "user_2" for a in user2_accs)

    def test_delete_account(self, repo: MockTradingRepo):
        acc = repo.create_account(name="ToDelete")
        assert repo.delete_account(acc.account_id) is True
        assert len(repo.list_accounts()) == 0
        assert repo.get_account(acc.account_id) is not None
        assert repo.get_account(acc.account_id).status == "archived"


class TestPositionCRUD:
    def test_upsert_new_position(self, repo: MockTradingRepo):
        acc = repo.create_account(name="Acc")
        pos = repo.upsert_position(acc.account_id, "AAPL", "US-Share", 100, 150.0)
        assert pos.shares == 100
        assert pos.average_cost == 150.0

    def test_upsert_existing_position(self, repo: MockTradingRepo):
        acc = repo.create_account(name="Acc")
        pos1 = repo.upsert_position(acc.account_id, "AAPL", "US-Share", 100, 150.0)
        pos2 = repo.upsert_position(acc.account_id, "AAPL", "US-Share", 200, 155.0)
        assert pos2.position_id == pos1.position_id
        assert pos2.shares == 200

    def test_list_positions_only_nonzero(self, repo: MockTradingRepo):
        acc = repo.create_account(name="Acc")
        repo.upsert_position(acc.account_id, "AAPL", "US-Share", 100, 150.0)
        repo.upsert_position(acc.account_id, "TSLA", "US-Share", 0, 0.0)
        positions = repo.list_positions(acc.account_id)
        assert len(positions) == 1


class TestTradeLedger:
    def test_record_and_list_trades(self, repo: MockTradingRepo):
        acc = repo.create_account(name="Acc")
        repo.record_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 150.0, "AI_SIGNAL")
        repo.record_trade(acc.account_id, "AAPL", "US-Share", "SELL", 50, 160.0, "AI_SIGNAL", realized_pnl=500.0)
        trades = repo.list_trades(acc.account_id)
        assert len(trades) == 2

    def test_list_trades_filtered_by_symbol(self, repo: MockTradingRepo):
        acc = repo.create_account(name="Acc")
        repo.record_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 150.0, "AI_SIGNAL")
        repo.record_trade(acc.account_id, "TSLA", "US-Share", "BUY", 10, 200.0, "MANUAL")
        assert len(repo.list_trades(acc.account_id, symbol="AAPL")) == 1


# ═══════════════════════════════════════════════════════════════════
# Phase 2: Execution Engine
# ═══════════════════════════════════════════════════════════════════

class TestExecutionEngine:
    def test_buy_updates_cash_and_position(self, service: MockTradingService):
        acc = service.create_account(name="Test", market="US-Share")
        trade = service.execute_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 150.0, "MANUAL")
        assert trade is not None
        assert trade.action == "BUY"
        updated = service.repo.get_account(acc.account_id)
        assert updated.current_cash == 1_000_000.0 - 15_075.0
        pos = service.repo.get_position(acc.account_id, "AAPL", "US-Share")
        assert pos.shares == 100
        assert pos.average_cost == 150.75

    def test_buy_averaging_up(self, service: MockTradingService):
        acc = service.create_account(name="Test", market="US-Share")
        service.execute_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 100.0, "MANUAL")
        service.execute_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 200.0, "MANUAL")
        pos = service.repo.get_position(acc.account_id, "AAPL", "US-Share")
        assert pos.shares == 200
        assert pos.average_cost == 150.75

    def test_sell_with_realized_pnl(self, service: MockTradingService):
        acc = service.create_account(name="Test", market="US-Share")
        service.execute_trade(acc.account_id, "TSLA", "US-Share", "BUY", 10, 200.0, "MANUAL")
        trade = service.execute_trade(acc.account_id, "TSLA", "US-Share", "SELL", 5, 250.0, "MANUAL")
        assert trade is not None
        assert trade.realized_pnl == 238.75
        updated = service.repo.get_account(acc.account_id)
        assert updated.current_cash == 999_233.75

    def test_sell_all_zeroes_position(self, service: MockTradingService):
        acc = service.create_account(name="Test", market="US-Share")
        service.execute_trade(acc.account_id, "TSLA", "US-Share", "BUY", 10, 200.0, "MANUAL")
        service.execute_trade(acc.account_id, "TSLA", "US-Share", "SELL", 10, 250.0, "MANUAL")
        pos = service.repo.get_position(acc.account_id, "TSLA", "US-Share")
        assert pos.shares == 0

    def test_insufficient_funds_rejects_buy(self, service: MockTradingService):
        acc = service.create_account(name="Poor", market="A-Share", initial_balance=100.0)
        trade = service.execute_trade(acc.account_id, "600519.SH", "A-Share", "BUY", 1, 1800.0, "MANUAL")
        assert trade is None

    def test_insufficient_shares_rejects_sell(self, service: MockTradingService):
        acc = service.create_account(name="Empty", market="US-Share")
        trade = service.execute_trade(acc.account_id, "AAPL", "US-Share", "SELL", 1, 150.0, "MANUAL")
        assert trade is None

    def test_trade_on_archived_account_rejected(self, service: MockTradingService):
        acc = service.create_account(name="Archived", market="US-Share")
        service.delete_account(acc.account_id)
        trade = service.execute_trade(acc.account_id, "AAPL", "US-Share", "BUY", 1, 150.0, "MANUAL")
        assert trade is None


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Signal-Triggered Auto-Trade
# ═══════════════════════════════════════════════════════════════════

class TestSignalTriggered:
    def _make_alert(self, **overrides):
        base = {
            "alert_id": "alt_test123",
            "symbol": "AAPL",
            "market": "US-Share",
            "entry_price": 150.0,
            "target_price": 200.0,
            "stop_loss": 130.0,
            "position_size_pct": 10.0,
        }
        base.update(overrides)
        return base

    def test_entry_trigger_buys(self, service: MockTradingService):
        acc = service.create_account(name="Signal Test", market="US-Share")
        alert = self._make_alert()
        trade = service.check_and_execute_signal(acc.account_id, alert, 150.0)
        assert trade is not None
        assert trade.action == "BUY"
        assert trade.trigger_source == "AI_SIGNAL"
        pos = service.repo.get_position(acc.account_id, "AAPL", "US-Share")
        assert pos.shares > 0

    def test_no_trigger_when_price_between_entry_and_target(self, service: MockTradingService):
        acc = service.create_account(name="No Trigger", market="US-Share")
        alert = self._make_alert()
        trade = service.check_and_execute_signal(acc.account_id, alert, 175.0)
        assert trade is None

    def test_target_hit_sells_all(self, service: MockTradingService):
        acc = service.create_account(name="Target Hit", market="US-Share")
        alert = self._make_alert()
        service.execute_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 150.0, "MANUAL")
        trade = service.check_and_execute_signal(acc.account_id, alert, 200.0)
        assert trade is not None
        assert trade.action == "SELL"
        pos = service.repo.get_position(acc.account_id, "AAPL", "US-Share")
        assert pos.shares == 0

    def test_stop_loss_hit_sells_all(self, service: MockTradingService):
        acc = service.create_account(name="Stop Loss", market="US-Share")
        alert = self._make_alert()
        service.execute_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 150.0, "MANUAL")
        trade = service.check_and_execute_signal(acc.account_id, alert, 130.0)
        assert trade is not None
        assert trade.action == "SELL"

    def test_no_double_buy(self, service: MockTradingService):
        acc = service.create_account(name="NoDblBuy", market="US-Share")
        alert = self._make_alert()
        service.check_and_execute_signal(acc.account_id, alert, 150.0)
        trade = service.check_and_execute_signal(acc.account_id, alert, 148.0)
        assert trade is None


# ═══════════════════════════════════════════════════════════════════
# Phase 4: Anomaly Detection
# ═══════════════════════════════════════════════════════════════════

class TestAnomalyDetection:
    def test_stock_spike_logged(self, service: MockTradingService):
        acc = service.create_account(name="Anomaly Test")
        anomalies = service.check_anomalies(acc.account_id, {"600519.SH": 8.5})
        assert len(anomalies) == 1
        assert anomalies[0]["event_type"] == "SPIKE"
        assert anomalies[0]["symbol"] == "600519.SH"

    def test_stock_drop_logged(self, service: MockTradingService):
        acc = service.create_account(name="Anomaly Test")
        anomalies = service.check_anomalies(acc.account_id, {"TSLA": -9.2})
        assert len(anomalies) == 1
        assert anomalies[0]["event_type"] == "DROP"

    def test_no_anomaly_below_threshold(self, service: MockTradingService):
        acc = service.create_account(name="Anomaly Test")
        anomalies = service.check_anomalies(acc.account_id, {"AAPL": 3.5})
        assert len(anomalies) == 0

    def test_account_level_anomaly(self, service: MockTradingService):
        acc = service.create_account(name="Anomaly Test")
        anomalies = service.check_anomalies(acc.account_id, {}, account_equity_change_pct=-3.5)
        assert len(anomalies) == 1
        assert anomalies[0]["symbol"] is None

    def test_multiple_anomalies(self, service: MockTradingService):
        acc = service.create_account(name="Multi Anomaly")
        anomalies = service.check_anomalies(
            acc.account_id,
            {"TSLA": -8.0, "AAPL": 10.0, "GOOGL": 2.0},
            account_equity_change_pct=-4.0,
        )
        assert len(anomalies) == 3


# ═══════════════════════════════════════════════════════════════════
# Phase 5: Portfolio Analytics
# ═══════════════════════════════════════════════════════════════════

class TestPortfolioAnalytics:
    def test_portfolio_summary(self, service: MockTradingService):
        acc = service.create_account(name="Portfolio", market="US-Share")
        service.execute_trade(acc.account_id, "AAPL", "US-Share", "BUY", 100, 150.0, "MANUAL")
        service.execute_trade(acc.account_id, "TSLA", "US-Share", "BUY", 50, 200.0, "MANUAL")
        summary = service.get_portfolio_summary(acc.account_id, {"AAPL": 160.0, "TSLA": 180.0})
        assert summary is not None
        assert summary["currency"] == "USD"
        assert len(summary["positions"]) == 2
        aapl = next(p for p in summary["positions"] if p["symbol"] == "AAPL")
        assert aapl["unrealized_pnl"] == (100 * 160) - 15075.0
        tsla = next(p for p in summary["positions"] if p["symbol"] == "TSLA")
        assert tsla["unrealized_pnl"] == (50 * 180) - 10050.0

    def test_empty_portfolio_summary(self, service: MockTradingService):
        acc = service.create_account(name="Empty", market="A-Share")
        summary = service.get_portfolio_summary(acc.account_id, {})
        assert summary is not None
        assert summary["total_equity"] == 1_000_000.0
        assert summary["total_pnl"] == 0.0
        assert len(summary["positions"]) == 0
