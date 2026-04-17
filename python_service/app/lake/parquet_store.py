import polars as pl
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

class ParquetMarketStore:
    def __init__(self, root_path: str = "python_service/data/lake"):
        self.root = Path(root_path)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_ohlc(self, dataset: str, market: str, symbol: str, rows: List[Dict[str, Any]]):
        if not rows:
            return
            
        frame = pl.DataFrame(rows)
        # Partitioning: dataset / market=X / year=Y / symbol=Z / part-000.parquet
        year = datetime.now().year
        target = self.root / dataset / f"market={market}" / f"year={year}" / f"symbol={symbol}"
        target.mkdir(parents=True, exist_ok=True)
        
        frame.write_parquet(target / "part-000.parquet")

    def glob_path(self, dataset: str, market: str, symbol: str) -> str:
        return str(self.root / dataset / f"market={market}" / "*" / f"symbol={symbol}" / "*.parquet")
