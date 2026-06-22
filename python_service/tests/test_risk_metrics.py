import pytest
import pandas as pd
import numpy as np
import tempfile
import os
import sqlite3
from app.quant.risk_metrics import RiskMetrics
from app.db.database import build_session_factory, engine

def test_sqlite_wal_mode():
    # Test WAL mode initialization via build_session_factory
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_wal.db")
        # Creating session factory initializes DB and executes hooks
        session_factory = build_session_factory(db_path)
        
        # Verify journal_mode using direct sqlite3 connection
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        conn.close()
        
        assert journal_mode == "wal"

def test_compute_sortino():
    # Case 1: Empty returns
    empty_series = pd.Series([], dtype=float)
    assert RiskMetrics.compute_sortino(empty_series) == 0.0
    
    # Case 2: Standard series
    # Let's create returns: mean excess return should be positive, downside deviation should be non-zero
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.001, 0.02, 252))
    sortino = RiskMetrics.compute_sortino(returns, rf=0.03, periods_per_year=252)
    assert isinstance(sortino, float)
    assert sortino != 0.0
    
    # Case 3: No downside returns (all positive excess returns)
    pos_returns = pd.Series([0.05, 0.06, 0.07])
    # with rf=0.03, daily_rf = 0.03/252 = 0.000119. Excess returns are positive.
    assert RiskMetrics.compute_sortino(pos_returns, rf=0.03, periods_per_year=252) == 0.0

def test_compute_var():
    # Case 1: Empty returns
    empty_series = pd.Series([], dtype=float)
    assert RiskMetrics.compute_var(empty_series) == 0.0
    
    # Case 2: Standard series
    returns = pd.Series([0.01, -0.02, 0.015, -0.01, 0.03])
    var = RiskMetrics.compute_var(returns, confidence=0.95)
    assert isinstance(var, float)
    assert var < 0  # VaR for returns at 95% confidence should be negative (downside threshold)
