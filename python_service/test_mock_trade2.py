import asyncio
from sqlmodel import Session
from app.db.database import session_factory, init_db
from app.services.mock_trading_service import MockTradingService
import json

init_db()

session = session_factory()
svc = MockTradingService(session)

acc = svc.create_account("TestA", "A-Share")

# Buy 100
svc.execute_trade(acc.account_id, "600519", "A-Share", "BUY", 100, 1500.0, "MANUAL")

# Sell 100 - should fail T+1
res = svc.execute_trade(acc.account_id, "600519", "A-Share", "SELL", 100, 1600.0, "MANUAL")
print("Sell result:", "Success" if res else "Failed")

trades = svc.repo.list_trades(acc.account_id)
for t in trades:
    print(t.action, t.shares, t.commission)
