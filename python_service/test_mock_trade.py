from app.db.database import session_factory, init_db
from app.services.mock_trading_service import MockTradingService

# Initialize the db to trigger migrations
init_db()

# create account
session = session_factory()
svc = MockTradingService(session)

acc = svc.create_account("TestAccount", "US-Share")
print(f"Created account: {acc.account_id}")

# insert trade
trade = svc.repo.record_trade(
    account_id=acc.account_id,
    symbol="AAPL",
    market="US-Share",
    action="BUY",
    shares=100,
    execution_price=150.0,
    trigger_source="MANUAL",
    commission=1.5
)
print(f"Trade id: {trade.trade_id}")

trades = svc.repo.list_trades(acc.account_id)
print(f"Trades len: {len(trades)}")
for t in trades:
    print(f"Trade: {t.trade_id}, {t.timestamp}, pnl: {t.realized_pnl}, commission: {t.commission}")
