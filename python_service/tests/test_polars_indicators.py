import sys
import os
import pytest
import polars as pl

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.quant.polars_indicators import compute_indicator_frame

def test_compute_indicator_frame_has_core_columns():
    # Setup mock data (need at least 20 rows for MA20 and 14 for RSI)
    rows = [{"trade_date": f"2026-04-{i:02d}", "close": 100 + i, "high": 101 + i, "low": 99 + i, "volume": 1000 + i} for i in range(1, 40)]
    
    # Compute
    frame = compute_indicator_frame(rows)
    
    # Verify columns exist
    assert "ma_20" in frame.columns
    assert "macd" in frame.columns
    assert "rsi_14" in frame.columns
    
    # Verify a value (ma_5 for first few rows will be null, but row 6 should have it)
    assert frame["ma_5"][5] is not None
