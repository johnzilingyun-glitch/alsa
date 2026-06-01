"""
Mock Trading API — FastAPI routes for managing simulated trading accounts,
executing trades, viewing portfolio analytics, and anomaly logs.
"""
from fastapi import APIRouter, HTTPException, Query, Header
import logging
logger = logging.getLogger(__name__)
from pydantic import BaseModel
from typing import Optional, List
from sqlmodel import Session
from ..db.sqlite import session_factory
from ..services.mock_trading_service import MockTradingService

router = APIRouter(prefix="/mock-trading", tags=["mock-trading"])


# ── Pydantic Request Models ──────────────────────────────────────

class AccountCreate(BaseModel):
    name: str
    market: str = "A-Share"  # A-Share / HK-Share / US-Share
    initial_balance: Optional[float] = None  # None → use market default

class TradeExecute(BaseModel):
    account_id: str
    symbol: str
    market: str
    action: str  # BUY / SELL
    shares: int
    execution_price: float
    trigger_source: str = "MANUAL"  # MANUAL / AI_SIGNAL
    position_size_pct: Optional[float] = None

class SignalCheck(BaseModel):
    account_id: str
    alert_id: str
    symbol: str
    market: str
    entry_price: float
    target_price: float
    stop_loss: float
    current_price: float
    position_size_pct: Optional[float] = 10.0

class SnapshotCreate(BaseModel):
    account_id: str
    snapshot_date: str  # YYYY-MM-DD
    prices: dict  # { "AAPL": 190.5, ... }


# ── Helper ────────────────────────────────────────────────────────

def _get_service() -> MockTradingService:
    session = session_factory()
    return MockTradingService(session)


# ══════════════════════════════════════════════════════════════════
# Account Management
# ══════════════════════════════════════════════════════════════════

@router.post("/accounts", status_code=201)
async def create_account(payload: AccountCreate, x_user_id: Optional[str] = Header(None)):
    svc = _get_service()
    user_id = x_user_id or "default_user"
    acc = svc.create_account(
        name=payload.name,
        market=payload.market,
        initial_balance=payload.initial_balance,
        user_id=user_id,
    )
    return {"success": True, "data": {
        "account_id": acc.account_id,
        "name": acc.name,
        "market": acc.market,
        "currency": acc.currency,
        "initial_balance": acc.initial_balance,
        "current_cash": acc.current_cash,
        "status": acc.status,
    }}

@router.get("/accounts")
async def list_accounts(x_user_id: Optional[str] = Header(None)):
    svc = _get_service()
    user_id = x_user_id or "default_user"
    accounts = svc.list_accounts(user_id=user_id)
    return {"success": True, "data": [{
        "account_id": a.account_id,
        "name": a.name,
        "market": a.market,
        "currency": a.currency,
        "initial_balance": a.initial_balance,
        "current_cash": a.current_cash,
        "status": a.status,
        "created_at": str(a.created_at),
    } for a in accounts]}

@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    svc = _get_service()
    ok = svc.delete_account(account_id)
    if not ok:
        raise HTTPException(404, "Account not found")
    return {"success": True}

class MergeAccounts(BaseModel):
    source_account_ids: List[str]
    target_account_id: str

@router.post("/accounts/merge", status_code=200)
async def merge_accounts(payload: MergeAccounts):
    svc = _get_service()
    if payload.target_account_id in payload.source_account_ids:
        raise HTTPException(400, "Target account cannot be in source accounts")
    acc = svc.merge_accounts(payload.source_account_ids, payload.target_account_id)
    if not acc:
        raise HTTPException(404, "Target account not found or merge failed")
    return {"success": True, "data": {
        "account_id": acc.account_id,
        "name": acc.name,
        "current_cash": acc.current_cash,
        "initial_balance": acc.initial_balance,
    }}


# ══════════════════════════════════════════════════════════════════
# Trade Execution
# ══════════════════════════════════════════════════════════════════

@router.post("/trades")
async def execute_trade(payload: TradeExecute):
    svc = _get_service()
    trade = svc.execute_trade(
        account_id=payload.account_id,
        symbol=payload.symbol,
        market=payload.market,
        action=payload.action,
        shares=payload.shares,
        execution_price=payload.execution_price,
        trigger_source=payload.trigger_source,
        position_size_pct=payload.position_size_pct,
    )
    if not trade:
        raise HTTPException(400, "Trade execution failed (insufficient funds/shares or inactive account)")
    return {"success": True, "data": {
        "trade_id": trade.trade_id,
        "action": trade.action,
        "symbol": trade.symbol,
        "shares": trade.shares,
        "execution_price": trade.execution_price,
        "realized_pnl": trade.realized_pnl,
        "timestamp": str(trade.timestamp),
    }}

@router.get("/trades/{account_id}")
async def list_trades(account_id: str, symbol: Optional[str] = None):
    svc = _get_service()
    trades = svc.repo.list_trades(account_id, symbol=symbol)
    return {"success": True, "data": [{
        "trade_id": t.trade_id,
        "symbol": t.symbol,
        "market": t.market,
        "action": t.action,
        "shares": t.shares,
        "execution_price": t.execution_price,
        "realized_pnl": t.realized_pnl,
        "trigger_source": t.trigger_source,
        "timestamp": str(t.timestamp),
    } for t in trades]}


# ══════════════════════════════════════════════════════════════════
# Signal-Triggered Auto-Trade
# ══════════════════════════════════════════════════════════════════

@router.post("/signal-check")
async def check_signal(payload: SignalCheck):
    svc = _get_service()
    alert_dict = {
        "alert_id": payload.alert_id,
        "symbol": payload.symbol,
        "market": payload.market,
        "entry_price": payload.entry_price,
        "target_price": payload.target_price,
        "stop_loss": payload.stop_loss,
        "position_size_pct": payload.position_size_pct,
    }
    trade = svc.check_and_execute_signal(payload.account_id, alert_dict, payload.current_price)
    if not trade:
        return {"success": True, "data": None, "message": "No signal triggered"}
    return {"success": True, "data": {
        "trade_id": trade.trade_id,
        "action": trade.action,
        "symbol": trade.symbol,
        "shares": trade.shares,
        "execution_price": trade.execution_price,
        "realized_pnl": trade.realized_pnl,
    }}


# ══════════════════════════════════════════════════════════════════
# Portfolio & Analytics
# ══════════════════════════════════════════════════════════════════

@router.get("/portfolio/{account_id}")
async def get_portfolio(account_id: str):
    """Get portfolio summary. Prices are resolved server-side."""
    svc = _get_service()
    positions = svc.repo.list_positions(account_id)
    symbols = [p.symbol for p in positions]
    prices = {}
    if symbols:
        try:
            from ..services.market_data_service import market_data_service
            quotes = await market_data_service.get_quotes(symbols)
            for q in quotes:
                if "price" in q and q["price"] is not None:
                    prices[q["symbol"]] = q["price"]
        except Exception as e:
            logger.error(f"Failed to fetch server-side quotes for portfolio: {e}")
            
    summary = svc.get_portfolio_summary(account_id, prices)
    if not summary:
        raise HTTPException(404, "Account not found")
    return {"success": True, "data": summary}

@router.post("/portfolio/{account_id}")
async def get_portfolio_with_prices(account_id: str, prices: dict):
    """Get portfolio summary with explicit current prices and server-side fallback for missing ones."""
    svc = _get_service()
    positions = svc.repo.list_positions(account_id)
    missing_symbols = [p.symbol for p in positions if p.symbol not in prices]
    if missing_symbols:
        try:
            from ..services.market_data_service import market_data_service
            quotes = await market_data_service.get_quotes(missing_symbols)
            for q in quotes:
                if "price" in q and q["price"] is not None:
                    prices[q["symbol"]] = q["price"]
        except Exception as e:
            logger.error(f"Failed to fetch server-side missing quotes: {e}")

    summary = svc.get_portfolio_summary(account_id, prices)
    if not summary:
        raise HTTPException(404, "Account not found")
    return {"success": True, "data": summary}

@router.get("/positions/{account_id}")
async def list_positions(account_id: str):
    svc = _get_service()
    positions = svc.repo.list_positions(account_id)
    return {"success": True, "data": [{
        "position_id": p.position_id,
        "symbol": p.symbol,
        "market": p.market,
        "shares": p.shares,
        "average_cost": p.average_cost,
    } for p in positions]}


# ══════════════════════════════════════════════════════════════════
# Snapshots (Equity Curve Data)
# ══════════════════════════════════════════════════════════════════

@router.post("/snapshots")
async def create_snapshot(payload: SnapshotCreate):
    svc = _get_service()
    summary = svc.get_portfolio_summary(payload.account_id, payload.prices)
    if not summary:
        raise HTTPException(404, "Account not found")
    snap = svc.repo.save_snapshot(
        account_id=payload.account_id,
        snapshot_date=payload.snapshot_date,
        total_equity=summary["total_equity"],
        cash_balance=summary["current_cash"],
        positions_market_value=summary["positions_market_value"],
    )
    return {"success": True, "data": {
        "snapshot_id": snap.snapshot_id,
        "snapshot_date": snap.snapshot_date,
        "total_equity": snap.total_equity,
    }}

@router.get("/snapshots/{account_id}")
async def list_snapshots(
    account_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    svc = _get_service()
    snaps = svc.repo.list_snapshots(account_id, start_date, end_date)
    return {"success": True, "data": [{
        "snapshot_date": s.snapshot_date,
        "total_equity": s.total_equity,
        "cash_balance": s.cash_balance,
        "positions_market_value": s.positions_market_value,
    } for s in snaps]}


# ══════════════════════════════════════════════════════════════════
# Anomaly Logs
# ══════════════════════════════════════════════════════════════════

@router.get("/anomalies/{account_id}")
async def list_anomalies(account_id: str, symbol: Optional[str] = None):
    svc = _get_service()
    logs = svc.repo.list_anomalies(account_id, symbol=symbol)
    return {"success": True, "data": [{
        "log_id": l.log_id,
        "symbol": l.symbol,
        "event_type": l.event_type,
        "magnitude_pct": l.magnitude_pct,
        "news_reasoning": l.news_reasoning,
        "timestamp": str(l.timestamp),
    } for l in logs]}
