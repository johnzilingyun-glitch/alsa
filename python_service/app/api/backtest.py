from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import subprocess
import os
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class BacktestRequest(BaseModel):
    start_date: str
    end_date: str
    model: str
    market: str = "CN"

# Path to the qlib project
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
QLIB_DIR = os.path.join(PROJECT_ROOT, "PaperTrading_System")
RESULTS_FILE = os.path.join(QLIB_DIR, "execution_layer", "results.json")

def run_qlib_subprocess(req: BacktestRequest):
    python_exec = os.path.join(QLIB_DIR, ".venv_qlib", "bin", "python")
    script = os.path.join(QLIB_DIR, "execution_layer", "run_backtest_core.py")
    
    # Clean previous result
    if os.path.exists(RESULTS_FILE):
        try:
            os.remove(RESULTS_FILE)
        except Exception:
            pass
            
    try:
        logger.info(f"Starting Qlib backtest subprocess for {req.model} from {req.start_date} to {req.end_date}")
        result = subprocess.run(
            [python_exec, script, "--start", req.start_date, "--end", req.end_date, "--model", req.model],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Backtest completed successfully.")
        logger.debug(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Backtest failed: {e.stderr}")

@router.post("/run")
async def trigger_backtest(req: BacktestRequest, background_tasks: BackgroundTasks):
    """
    Trigger backtest in a background task so we don't block the API.
    """
    if not os.path.exists(os.path.join(QLIB_DIR, ".venv_qlib")):
        raise HTTPException(status_code=500, detail="Qlib virtual environment not found.")
        
    background_tasks.add_task(run_qlib_subprocess, req)
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
        return {"status": "completed", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
