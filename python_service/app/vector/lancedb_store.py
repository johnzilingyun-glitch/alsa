import logging
import hashlib
import numpy as np
import lancedb
from typing import List, Dict, Any, Optional
from google import genai

logger = logging.getLogger(__name__)

def get_fallback_embedding(text: str, dimension: int = 768) -> List[float]:
    """
    Generate a deterministic, normalized vector from text using MD5 hashing of words.
    This acts as a high-quality zero-dependency fallback.
    Uses a local RandomState instance to avoid mutating the global numpy random state.
    """
    if not text:
        return [0.0] * dimension
    
    # Split text into words
    words = text.lower().split()
    if not words:
        words = [text.lower()]
        
    vector = np.zeros(dimension)
    for word in words:
        h = hashlib.md5(word.encode('utf-8')).hexdigest()
        val = int(h, 16)
        rng = np.random.RandomState(val % 2**32)
        vector += rng.normal(0, 1.0, dimension)
        
    for i in range(len(text) - 2):
        ngram = text[i:i+3]
        h = hashlib.md5(ngram.encode('utf-8')).hexdigest()
        val = int(h, 16)
        rng = np.random.RandomState(val % 2**32)
        vector += 0.2 * rng.normal(0, 1.0, dimension)
        
    norm = np.linalg.norm(vector)
    if norm > 1e-8:
        vector = vector / norm
        
    return vector.tolist()

def get_embedding(text: str, dimension: int = 768) -> List[float]:
    """
    Generate embedding vector for the text. Try using Gemini API first,
    fallback to deterministic hashing embedding if keys are not configured or failed.
    """
    api_key = None
    try:
        from app.services.llm_gateway import llm_gateway
        api_key = llm_gateway.get_gemini_api_key()
    except Exception:
        pass
        
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.embed_content(
                model="text-embedding-004",
                contents=text,
            )
            embedding = response.embeddings[0].values
            if len(embedding) == dimension:
                return embedding
            if len(embedding) > dimension:
                return embedding[:dimension]
            else:
                return embedding + [0.0] * (dimension - len(embedding))
        except Exception as e:
            logger.warning(f"Failed to generate Gemini embedding, using fallback: {e}")
            
    return get_fallback_embedding(text, dimension)

class LanceResearchStore:
    def __init__(self, db_path: str = "python_service/data/lancedb"):
        self.db = lancedb.connect(db_path)
        # Check if table exists, otherwise create it
        if "research_chunks" not in self.db.list_tables():
            # Initial schema: doc_id, symbol, text, embedding
            # Note: embeddings usually have a fixed dimension (e.g. 768 or 1536)
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
                    "vector": [0.0] * 768
                }
            ], mode="overwrite")
        else:
            self.table = self.db.open_table("research_chunks")

    def upsert_documents(self, rows: List[Dict[str, Any]]):
        """
        Expects rows with 'doc_id', 'symbol', 'text', and optional 'vector'.
        If 'vector' is missing, it is generated automatically using the embedding pipeline.
        """
        if not rows:
            return
        
        normalized_rows = []
        for row in rows:
            normalized = self._normalize_row(row)
            if "vector" not in normalized or normalized["vector"] is None:
                normalized["vector"] = get_embedding(normalized.get("text", ""), dimension=768)
            normalized_rows.append(normalized)
            
        self.table.add(normalized_rows)

    def search(self, symbol: str, query: Optional[str] = None, query_vector: Optional[List[float]] = None, limit: int = 5, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform semantic search filtered by stock symbol and optional Point-in-Time boundary.
        Accepts either raw text query or precomputed query_vector.
        """
        if query_vector is None:
            if query is not None:
                query_vector = get_embedding(query, dimension=768)
            else:
                query_vector = [0.0] * 768
                
        # Sanitize symbol to prevent SQL injection in where clause
        # Only allow alphanumeric, dot, hyphen, underscore (typical stock symbol chars)
        import re
        sanitized_symbol = re.sub(r'[^a-zA-Z0-9.\-_]', '', symbol)
        fetch_limit = max(limit * 10, limit)
        rows = self.table.search(query_vector).where(f"symbol = '{sanitized_symbol}'").limit(fetch_limit).to_list()
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
