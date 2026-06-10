from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import json
import logging
from ..services.backtest_engine_service import BacktestEngine

router = APIRouter()
logger = logging.getLogger(__name__)

class BacktestRequest(BaseModel):
    start_date: str
    end_date: str
    model: str
    market: str = "CN"
    config: Optional[Dict[str, Any]] = None

# Path to the qlib project for saving results
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
QLIB_DIR = os.path.join(PROJECT_ROOT, "PaperTrading_System")
if not os.path.exists(QLIB_DIR):
    os.makedirs(os.path.join(QLIB_DIR, "execution_layer"), exist_ok=True)
RESULTS_FILE = os.path.join(QLIB_DIR, "execution_layer", "results.json")

def run_native_backtest(req: BacktestRequest):
    # Clean previous result
    if os.path.exists(RESULTS_FILE):
        try:
            os.remove(RESULTS_FILE)
        except Exception:
            pass
            
    try:
        logger.info(f"Starting Native backtest for {req.model} from {req.start_date} to {req.end_date}")
        
        cfg = req.config or {}
        init_cash = float(cfg.get("initial_capital") if cfg.get("initial_capital") is not None else cfg.get("initial_cash", 100000.0))
        commission = float(cfg.get("commission") if cfg.get("commission") is not None else cfg.get("rate", 0.0003))
        strategy_params = dict(cfg.get("strategy_params", {}) or {})
        target_symbol = cfg.get("target_symbol")
        if target_symbol:
            strategy_params["target_symbol"] = target_symbol.strip()
        
        engine = BacktestEngine(init_cash=init_cash, commission=commission)
        
        import asyncio
        results = asyncio.run(engine.run(req.start_date, req.end_date, req.model, req.market, params=strategy_params))
        
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        logger.info("Backtest completed successfully.")
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        # write error to results.json so frontend knows
        error_result = {"status": "error", "message": str(e)}
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(error_result, f, indent=2)

@router.post("/run")
async def trigger_backtest(req: BacktestRequest, background_tasks: BackgroundTasks):
    """
    Trigger backtest in a background task so we don't block the API.
    """
    background_tasks.add_task(run_native_backtest, req)
    return {"status": "started", "message": "Backtest running in background"}

@router.get("/results")
async def get_backtest_results():
    """
    Check if results.json exists and return it.
    """
    if not os.path.exists(RESULTS_FILE):
        return {"status": "running_or_not_started"}
        
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if data.get("status") == "error":
            return {"status": "error", "message": data.get("message")}
            
        return {"status": "completed", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConvertToMockRequest(BaseModel):
    market: str = "A-Share"
    initial_capital: float = 1000000.0
    strategy_name: str = "MockAgent"


@router.post("/convert-to-mock")
async def convert_to_mock(req: ConvertToMockRequest):
    """
    One-click convert backtest results into a mock trading account.
    Reads the last backtest results, creates a new mock account,
    and seeds positions from the final trade holdings.
    """
    if not os.path.exists(RESULTS_FILE):
        return {"success": False, "message": "No backtest results found. Please run a backtest first."}
    
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if data.get("status") == "error":
            return {"success": False, "message": f"Last backtest failed: {data.get('message')}"}
        
        # Reconstruct final positions from trade list
        trades = data.get("trades", [])
        positions: dict = {}  # symbol -> { shares, last_price }
        for t in trades:
            sym = t.get("symbol", "")
            action = t.get("action", "")
            shares = t.get("shares", 0)
            price = t.get("price", 0)
            if sym not in positions:
                positions[sym] = {"shares": 0, "last_price": price}
            if action == "BUY":
                positions[sym]["shares"] += shares
            elif action == "SELL":
                positions[sym]["shares"] -= shares
            positions[sym]["last_price"] = price
        
        # Filter to only symbols with positive holdings
        held = {sym: info for sym, info in positions.items() if info["shares"] > 0}
        
        # Create mock account and seed positions
        from ..db.sqlite import session_factory
        from ..services.mock_trading_service import MockTradingService
        
        session = session_factory()
        svc = MockTradingService(session)
        
        account_name = f"回测转模拟盘 ({req.strategy_name})"
        account = svc.create_account(
            name=account_name,
            market=req.market,
            initial_balance=req.initial_capital,
        )
        
        # Seed positions by executing BUY trades at their last known price
        market_code = "A-Share" if req.market in ("A-Share", "CN") else req.market
        for sym, info in held.items():
            try:
                svc.execute_trade(
                    account_id=account.account_id,
                    symbol=sym,
                    market=market_code,
                    action="BUY",
                    shares=info["shares"],
                    execution_price=info["last_price"],
                    trigger_source="BACKTEST_CONVERT",
                )
            except Exception as e:
                logger.warning(f"Failed to seed position {sym}: {e}")
        
        return {
            "success": True,
            "data": {
                "account_id": account.account_id,
                "account_name": account_name,
                "positions_count": len(held),
                "market": req.market,
            }
        }
    except Exception as e:
        logger.error(f"Convert to mock failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}

