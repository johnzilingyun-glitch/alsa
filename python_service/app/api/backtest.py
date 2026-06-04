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
        engine = BacktestEngine(init_cash=100000.0)
        results = engine.run(req.start_date, req.end_date, req.model, req.market)
        
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        logger.info("Backtest completed successfully.")
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
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

