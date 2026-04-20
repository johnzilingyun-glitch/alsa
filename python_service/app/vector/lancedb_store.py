import lancedb
import polars as pl
from typing import List, Dict, Any

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
        self.table.add(rows)

    def search(self, symbol: str, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Perform semantic search filtered by stock symbol.
        """
        return self.table.search(query_vector).where(f"symbol = '{symbol}'").limit(limit).to_list()
