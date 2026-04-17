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
    
    # Insert mock document (using 384-dim vector as per store implementation)
    mock_vector = [0.1] * 384
    store.upsert_documents([{
        "doc_id": "r1", 
        "symbol": "600519", 
        "text": "Direct sales ratio increasing", 
        "vector": mock_vector
    }])
    
    # Search
    # Slightly perturbed vector should still match
    query_vector = [0.11] * 384
    results = store.search(symbol="600519", query_vector=query_vector, limit=1)
    
    assert len(results) >= 1
    assert results[0]["doc_id"] == "r1"
    assert "Direct sales" in results[0]["text"]
