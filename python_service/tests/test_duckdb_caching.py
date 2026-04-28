import pytest
import time
from app.lake.duckdb_engine import DuckDBMarketQuery

def test_duckdb_cache_ttl():
    query_engine = DuckDBMarketQuery()
    parquet_glob = "alsa/python_service/data/lake/ohlc/market=A-Share/year=2026/symbol=600089/*.parquet"

    # First query (populate cache)
    start = time.time()
    query_engine.latest_close(parquet_glob)
    first_duration = time.time() - start

    # Second query (should hit cache, significantly faster)
    start = time.time()
    query_engine.latest_close(parquet_glob)
    second_duration = time.time() - start

    assert second_duration < first_duration

    # Wait for TTL expiration (30s)
    time.sleep(31)

    # Third query (should miss cache)
    start = time.time()
    query_engine.latest_close(parquet_glob)
    third_duration = time.time() - start

    assert third_duration > second_duration
