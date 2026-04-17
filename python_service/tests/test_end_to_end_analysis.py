import sys
import os
import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.services.analysis_job_service import AnalysisJobService
from python_service.app.db.repositories.job_repo import JobRepository
from python_service.app.services.market_snapshot_service import MarketSnapshotService
from python_service.app.lake.parquet_store import ParquetMarketStore

@pytest.fixture
def mock_db(tmp_path):
    from python_service.app.db.sqlite import build_session_factory
    db_path = tmp_path / "test.db"
    return build_session_factory(str(db_path))

@pytest.mark.asyncio
async def test_full_analysis_job_lifecycle(mock_db, tmp_path):
    # Setup
    store = ParquetMarketStore(str(tmp_path / "lake"))
    snapshot_service = MarketSnapshotService(store)
    job_repo = JobRepository(mock_db)
    service = AnalysisJobService(job_repo, snapshot_service)
    
    symbol = "600519"
    market = "A-Share"
    
    # Mock akshare data fetching
    with patch("akshare.stock_zh_a_hist") as mock_hist, \
         patch("akshare.stock_individual_info_em") as mock_info:
        
        import pandas as pd
        # Mock 120 days of data
        dates = pd.date_range(end="2026-04-17", periods=120)
        mock_hist.return_value = pd.DataFrame({
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": [1600] * 120,
            "最高": [1700] * 120,
            "最低": [1500] * 120,
            "收盘": [1650] * 120,
            "成交量": [10000] * 120
        })
        
        mock_info.return_value = pd.DataFrame({
            "item": ["总市值", "市盈率", "市净率"],
            "value": [2.1e12, 30.5, 8.2]
        })
        
        # Start Job
        job_id = await service.start_job(symbol, market)
        assert job_id.startswith("job_")
        
        # Since _run_job is an async task, we need to wait for it or call it directly for the test
        # In this test we use a small sleep to let the task progress or await the internal method
        await service._run_job(job_id, symbol, market)
        
        # Verify result in DB
        job = job_repo.get_by_id(job_id)
        assert job.status == "completed"
        
        result = json.loads(job.result_payload)
        assert result["symbol"] == symbol
        assert "indicators" in result
        assert result["indicators"]["ma_5"] == 1650.0 # Standard for our mock data
        
        # Verify Parquet file exists
        parquet_path = store.glob_path("ohlc", market, symbol)
        import glob
        assert len(glob.glob(parquet_path)) > 0
