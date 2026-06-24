from unittest.mock import patch
from python_service.app.lake.duckdb_engine import DuckDBMarketQuery
from python_service.app.lake.parquet_store import ParquetMarketStore

def test_duckdb_cache_ttl(tmp_path):
    # Setup test lake directory
    lake_root = tmp_path / "lake"
    store = ParquetMarketStore(str(lake_root))
    query_engine = DuckDBMarketQuery()
    
    # Reset internal query engine cache to avoid interference from other tests
    query_engine._cache = {}
    
    # Write actual mock data to the temporary store
    store.write_ohlc("ohlc", "A-Share", "600089", [
        {"trade_date": "2026-04-16", "close": 15.0}
    ])
    parquet_glob = store.glob_path("ohlc", "A-Share", "600089")
    
    # Base timestamp
    current_time = 1000.0
    
    with patch("time.time", side_effect=lambda: current_time):
        # 1. First query: should query from DuckDB and populate cache
        # We patch the database connection's execute method to verify it is called
        with patch.object(query_engine.con, "execute", wraps=query_engine.con.execute) as mock_execute:
            res1 = query_engine.latest_close(parquet_glob)
            assert res1["close"] == 15.0
            assert mock_execute.call_count == 1
        
        # 2. Second query: within 30s TTL, should hit cache (no DuckDB execution)
        with patch.object(query_engine.con, "execute", wraps=query_engine.con.execute) as mock_execute:
            res2 = query_engine.latest_close(parquet_glob)
            assert res2["close"] == 15.0
            assert mock_execute.call_count == 0  # Verified: cache hit, execute NOT called
            
        # 3. Advance clock by 31 seconds to expire cache
        current_time += 31.0
        
        # 4. Third query: expired TTL, should query from DuckDB again and refresh cache
        with patch.object(query_engine.con, "execute", wraps=query_engine.con.execute) as mock_execute:
            res3 = query_engine.latest_close(parquet_glob)
            assert res3["close"] == 15.0
            assert mock_execute.call_count == 1  # Verified: cache miss, execute called again
