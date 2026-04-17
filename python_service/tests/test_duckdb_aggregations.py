import sys
import os
import pytest
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.lake.parquet_store import ParquetMarketStore
from python_service.app.lake.duckdb_engine import DuckDBMarketQuery

def test_duckdb_cross_stock_aggregation(tmp_path):
    # Setup
    lake_root = tmp_path / "lake"
    store = ParquetMarketStore(str(lake_root))
    query_engine = DuckDBMarketQuery()
    
    # Store two stocks
    store.write_ohlc("ohlc", "A-Share", "600519", [{"trade_date": "2026-04-16", "close": 1700}])
    store.write_ohlc("ohlc", "A-Share", "600000", [{"trade_date": "2026-04-16", "close": 10}])
    
    # Query all stocks in the lake for a specific date
    glob_all = str(lake_root / "ohlc" / "market=A-Share" / "*" / "symbol=*" / "*.parquet")
    
    sql = f"""
        SELECT AVG(close) as avg_price 
        FROM read_parquet('{glob_all}') 
        WHERE trade_date = '2026-04-16'
    """
    res = query_engine.run_query(sql)
    assert float(res.iloc[0]['avg_price']) == 855.0 # (1700 + 10) / 2
