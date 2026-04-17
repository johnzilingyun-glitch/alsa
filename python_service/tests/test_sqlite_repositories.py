import sys
import os
import pytest
from sqlmodel import SQLModel, Session, create_engine

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.db.sqlite import build_session_factory
from python_service.app.db.repositories.watchlist_repo import WatchlistRepository

def test_watchlist_repo_persists_item(tmp_path):
    db_path = tmp_path / "test_app.db"
    session_factory = build_session_factory(str(db_path))
    repo = WatchlistRepository(session_factory)
    
    # Create
    repo.create(symbol="600519", name="贵州茅台", market="A-Share")
    
    # Verify
    items = repo.list_items()
    assert len(items) == 1
    assert items[0].symbol == "600519"
    assert items[0].name == "贵州茅台"
