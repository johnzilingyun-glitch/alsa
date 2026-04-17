import sys
import os
import pytest
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.lake.parquet_store import ParquetMarketStore
from python_service.app.lake.duckdb_engine import DuckDBMarketQuery

def test_parquet_and_duckdb_round_trip(tmp_path):
    # Setup
    lake_root = tmp_path / "lake"
    store = ParquetMarketStore(str(lake_root))
    query_engine = DuckDBMarketQuery()
    
    # Mock OHLC data (Ensure trade_date is present as per Task 3 spec)
    rows = [
        {"trade_date": "2026-04-16", "close": 1698, "volume": 15678},
        {"trade_date": "2026-04-15", "close": 1650, "volume": 14000}
    ]
    
    # Write
    store.write_ohlc("ohlc", "A-Share", "600519", rows)
    
    # Verify file exists
    glob_pattern = store.glob_path("ohlc", "A-Share", "600519")
    
    # Query via DuckDB
    result = query_engine.latest_close(glob_pattern)
    assert result["close"] == 1698
