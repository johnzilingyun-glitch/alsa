import os
import polars as pl
import pandas as pd
from datetime import datetime
from typing import Dict, Any

SNAPSHOT_DIR = os.path.join(os.getcwd(), "data", "snapshots")

if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

def save_market_snapshot(analysis_id: str, data: Dict[str, Any]) -> str:
    """
    Saves a market data snapshot to a Parquet file.
    'data' can contain dataframes or dictionaries.
    """
    snapshot_path = os.path.join(SNAPSHOT_DIR, f"{analysis_id}.parquet")
    
    # In a real institutional setup, we'd flatten the data into a schema.
    # For now, we'll store the core numerical data as columns.
    
    # Extract historical data if present
    if "history" in data and isinstance(data["history"], list):
        df = pl.from_dicts(data["history"])
        # Add metadata columns
        df = df.with_columns([
            pl.lit(analysis_id).alias("analysis_id"),
            pl.lit(datetime.now().isoformat()).alias("snapshot_at")
        ])
        df.write_parquet(snapshot_path)
        return snapshot_path
    
    # Fallback to a simple storage if no standard history list is found
    # (Just to ensure we always have a file)
    df = pl.from_dicts([{"analysis_id": analysis_id, "snapshot_at": datetime.now().isoformat()}])
    df.write_parquet(snapshot_path)
    return snapshot_path

def query_snapshot(analysis_id: str) -> pl.DataFrame:
    snapshot_path = os.path.join(SNAPSHOT_DIR, f"{analysis_id}.parquet")
    if os.path.exists(snapshot_path):
        return pl.read_parquet(snapshot_path)
    return pl.DataFrame()
