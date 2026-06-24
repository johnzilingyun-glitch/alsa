import sys
import os

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


def test_ohlc_writes_are_append_only_and_return_observation_metadata(tmp_path):
    lake_root = tmp_path / "lake"
    store = ParquetMarketStore(str(lake_root))

    rows = [
        {"trade_date": "2026-04-16", "close": 1698, "volume": 15678},
        {"trade_date": "2026-04-15", "close": 1650, "volume": 14000},
    ]

    first = store.write_ohlc(
        "ohlc",
        "A-Share",
        "600519",
        rows,
        vendor="unit-test",
        observed_at="2026-04-16T15:01:00Z",
        ingested_at="2026-04-16T15:02:00Z",
    )
    second = store.write_ohlc(
        "ohlc",
        "A-Share",
        "600519",
        rows,
        vendor="unit-test",
        observed_at="2026-04-16T15:03:00Z",
        ingested_at="2026-04-16T15:04:00Z",
    )

    assert first["storage_path"] != second["storage_path"]
    assert first["content_hash"] == second["content_hash"]
    assert first["row_count"] == 2
    assert first["effective_from"] == "2026-04-16T15:02:00Z"
    assert first["vendor"] == "unit-test"

    parquet_files = list(lake_root.rglob("*.parquet"))
    assert len(parquet_files) == 2
    assert all(path.name.startswith("part-") for path in parquet_files)
    assert all(path.name != "part-000.parquet" for path in parquet_files)

    glob_pattern = store.glob_path("ohlc", "A-Share", "600519")
    assert len(__import__("glob").glob(glob_pattern)) == 2
