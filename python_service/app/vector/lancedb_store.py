import lancedb
import polars as pl
from typing import List, Dict, Any, Optional

class LanceResearchStore:
    def __init__(self, db_path: str = "python_service/data/lancedb"):
        self.db = lancedb.connect(db_path)
        # Check if table exists, otherwise create it
        if "research_chunks" not in self.db.list_tables():
            # Initial schema: doc_id, symbol, text, embedding
            # Note: embeddings usually have a fixed dimension (e.g. 768 or 1536)
            # For bootstrap, we use a small dimension
            self.table = self.db.create_table("research_chunks", data=[
                {
                    "doc_id": "bootstrap", 
                    "symbol": "BOOT", 
                    "text": "Initial document",
                    "source_type": "bootstrap",
                    "published_at": "1970-01-01T00:00:00Z",
                    "observed_at": "1970-01-01T00:00:00Z",
                    "ingested_at": "1970-01-01T00:00:00Z",
                    "effective_from": "1970-01-01T00:00:00Z",
                    "effective_to": None,
                    "credibility_score": 0.0,
                    "vector": [0.0] * 384 # Standard small embedding size
                }
            ], mode="overwrite")
        else:
            self.table = self.db.open_table("research_chunks")

    def upsert_documents(self, rows: List[Dict[str, Any]]):
        """
        Expects rows with 'doc_id', 'symbol', 'text', and 'vector'
        """
        if not rows:
            return
        self.table.add([self._normalize_row(row) for row in rows])

    def search(self, symbol: str, query_vector: List[float], limit: int = 5, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform semantic search filtered by stock symbol and optional Point-in-Time boundary.
        """
        fetch_limit = max(limit * 10, limit)
        rows = self.table.search(query_vector).where(f"symbol = '{symbol}'").limit(fetch_limit).to_list()
        if as_of_date:
            rows = [row for row in rows if self._is_effective(row, as_of_date)]
        return rows[:limit]

    @staticmethod
    def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        default_time = "1970-01-01T00:00:00Z"
        normalized = dict(row)
        normalized.setdefault("source_type", "unknown")
        normalized.setdefault("published_at", normalized.get("effective_from", default_time))
        normalized.setdefault("observed_at", normalized.get("published_at", default_time))
        normalized.setdefault("ingested_at", normalized.get("observed_at", default_time))
        normalized.setdefault("effective_from", normalized.get("ingested_at", default_time))
        normalized.setdefault("effective_to", None)
        normalized.setdefault("credibility_score", 0.0)
        return normalized

    @staticmethod
    def _is_effective(row: Dict[str, Any], as_of_date: str) -> bool:
        effective_from = row.get("effective_from") or "1970-01-01T00:00:00Z"
        effective_to = row.get("effective_to")
        return effective_from <= as_of_date and (not effective_to or effective_to > as_of_date)
