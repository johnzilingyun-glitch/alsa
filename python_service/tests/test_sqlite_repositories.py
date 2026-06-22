import sys
import os
import pytest
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.db.database import build_session_factory
from python_service.app.db.repositories.watchlist_repo import WatchlistRepository

def test_build_session_factory_registers_core_tables_without_model_side_effects(tmp_path):
    db_path = tmp_path / "test_app.db"
    session_factory = build_session_factory(str(db_path))

    with session_factory() as session:
        table_names = {
            row[0]
            for row in session.exec(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).all()
        }

    assert "searchalert" in table_names
    assert "analysisjob" in table_names
    assert "promptrun" in table_names

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
