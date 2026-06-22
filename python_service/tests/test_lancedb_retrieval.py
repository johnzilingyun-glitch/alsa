import sys
import os
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.vector.lancedb_store import LanceResearchStore

def test_lancedb_returns_best_match(tmp_path):
    # Setup
    db_root = tmp_path / "lancedb"
    store = LanceResearchStore(str(db_root))
    
    # Insert mock document (using 768-dim vector as per store implementation)
    mock_vector = [0.1] * 768
    store.upsert_documents([{
        "doc_id": "r1", 
        "symbol": "600519", 
        "text": "Direct sales ratio increasing", 
        "vector": mock_vector
    }])
    
    # Search
    # Slightly perturbed vector should still match
    query_vector = [0.11] * 768
    results = store.search(symbol="600519", query_vector=query_vector, limit=1)
    
    assert len(results) >= 1
    assert results[0]["doc_id"] == "r1"
    assert "Direct sales" in results[0]["text"]


def test_lancedb_search_filters_documents_by_as_of_date(tmp_path):
    db_root = tmp_path / "lancedb"
    store = LanceResearchStore(str(db_root))

    store.upsert_documents([
        {
            "doc_id": "past_doc",
            "symbol": "MSFT",
            "text": "Past visible filing",
            "vector": [1.0] * 768,
            "source_type": "filing",
            "published_at": "2026-01-01T00:00:00Z",
            "observed_at": "2026-01-01T00:01:00Z",
            "ingested_at": "2026-01-01T00:02:00Z",
            "effective_from": "2026-01-01T00:02:00Z",
            "effective_to": None,
            "credibility_score": 0.95,
        },
        {
            "doc_id": "future_doc",
            "symbol": "MSFT",
            "text": "Future earnings surprise",
            "vector": [1.0] * 768,
            "source_type": "news",
            "published_at": "2026-02-01T00:00:00Z",
            "observed_at": "2026-02-01T00:01:00Z",
            "ingested_at": "2026-02-01T00:02:00Z",
            "effective_from": "2026-02-01T00:02:00Z",
            "effective_to": None,
            "credibility_score": 0.90,
        },
    ])

    results = store.search("MSFT", query_vector=[1.0] * 768, as_of_date="2026-01-15T00:00:00Z", limit=10)

    assert [row["doc_id"] for row in results] == ["past_doc"]
