import pytest
from unittest.mock import patch, MagicMock
from app.vector.lancedb_store import LanceResearchStore, get_fallback_embedding, get_embedding

def test_get_fallback_embedding():
    text = "Artificial Intelligence in Quantitative Finance"
    v1 = get_fallback_embedding(text, dimension=768)
    v2 = get_fallback_embedding(text, dimension=768)
    
    assert len(v1) == 768
    assert len(v2) == 768
    # Test determinism
    assert v1 == v2
    
    # Test different text produces different vector
    v3 = get_fallback_embedding("Different text", dimension=768)
    assert v1 != v3

@patch("app.services.llm_gateway.llm_gateway.get_gemini_api_key")
def test_get_embedding_fallback(mock_get_key):
    # Set API key to None/empty to trigger fallback
    mock_get_key.return_value = None
    
    v = get_embedding("Hello world", dimension=768)
    assert len(v) == 768
    
    # Confirm it matches fallback exactly
    assert v == get_fallback_embedding("Hello world", dimension=768)

def test_lancedb_auto_vectorization(tmp_path):
    db_root = tmp_path / "lancedb"
    store = LanceResearchStore(str(db_root))
    
    # Insert document without 'vector'
    store.upsert_documents([
        {
            "doc_id": "auto_doc_1",
            "symbol": "NVDA",
            "text": "GPU demand is skyrocketing due to AI models",
            "source_type": "filing"
        }
    ])
    
    # Verify that the vector was automatically generated and has 768 dimensions
    results = store.search(symbol="NVDA", query="GPU demand", limit=1)
    
    assert len(results) >= 1
    assert results[0]["doc_id"] == "auto_doc_1"
    assert "vector" in results[0]
    assert len(results[0]["vector"]) == 768
