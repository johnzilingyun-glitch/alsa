import polars as pl
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timezone
import hashlib
import json
import uuid

class ParquetMarketStore:
    def __init__(self, root_path: str = "python_service/data/lake"):
        self.root = Path(root_path)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_ohlc(
        self,
        dataset: str,
        market: str,
        symbol: str,
        rows: List[Dict[str, Any]],
        vendor: str = "unknown",
        observed_at: str | None = None,
        ingested_at: str | None = None,
        published_at: str | None = None,
        effective_from: str | None = None,
    ):
        if not rows:
            return None
            
        ingested_at = ingested_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        observed_at = observed_at or ingested_at
        published_at = published_at or observed_at
        effective_from = effective_from or ingested_at
        content_hash = self._content_hash(rows)

        frame = pl.DataFrame(rows)
        frame = frame.with_columns(
            pl.lit(vendor).alias("_vendor"),
            pl.lit(observed_at).alias("_observed_at"),
            pl.lit(ingested_at).alias("_ingested_at"),
            pl.lit(published_at).alias("_published_at"),
            pl.lit(effective_from).alias("_effective_from"),
            pl.lit(content_hash).alias("_content_hash"),
        )

        # Partitioning: dataset / market=X / year=Y / symbol=Z / part-<timestamp>-<uuid>.parquet
        year = self._partition_year(rows, effective_from)
        target = self.root / dataset / f"market={market}" / f"year={year}" / f"symbol={symbol}"
        target.mkdir(parents=True, exist_ok=True)
        file_name = f"part-{self._safe_timestamp(ingested_at)}-{uuid.uuid4().hex[:12]}.parquet"
        storage_path = target / file_name

        frame.write_parquet(storage_path)

        return {
            "dataset": dataset,
            "market": market,
            "symbol": symbol,
            "vendor": vendor,
            "observed_at": observed_at,
            "ingested_at": ingested_at,
            "published_at": published_at,
            "effective_from": effective_from,
            "content_hash": content_hash,
            "row_count": len(rows),
            "storage_path": str(storage_path),
        }

    def glob_path(self, dataset: str, market: str, symbol: str) -> str:
        return str(self.root / dataset / f"market={market}" / "*" / f"symbol={symbol}" / "*.parquet")

    @staticmethod
    def _content_hash(rows: List[Dict[str, Any]]) -> str:
        payload = json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _partition_year(rows: List[Dict[str, Any]], fallback_timestamp: str) -> int:
        trade_date = rows[0].get("trade_date")
        if trade_date:
            try:
                return datetime.fromisoformat(str(trade_date)[:10]).year
            except ValueError:
                pass
        return int(fallback_timestamp[:4])

    @staticmethod
    def _safe_timestamp(value: str) -> str:
        return (
            value.replace(":", "")
            .replace("-", "")
            .replace(".", "")
            .replace("+", "")
            .replace("Z", "Z")
        )
