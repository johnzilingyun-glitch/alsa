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
    from python_service.app.db.database import build_session_factory
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
    
    # Mock data fetching and discussion service
    mock_messages = [
        {"role": "Technical Analyst", "content": "Technical Analysis content snippet", "timestamp": "2026-04-17T12:00:00"},
        {"role": "Fundamental Analyst", "content": "Fundamental Analysis content snippet", "timestamp": "2026-04-17T12:00:00"},
        {
            "role": "Chief Strategist",
            "content": "投资评级 | **Buy**\n核心风险 | **Oversupply**\n核心机会 | **Growth**\n核心策略 | **Standard position**\n期望价格 = 1800 CNY\n价格止损 1500 CNY\n逻辑止损 | Competition escalation",
            "timestamp": "2026-04-17T12:00:00"
        }
    ]
    
    with patch("python_service.app.services.data_providers.data_router.get_history") as mock_hist, \
         patch("python_service.app.services.data_providers.data_router.get_financial_summary") as mock_summary, \
         patch("python_service.app.services.data_providers.data_router.get_quote") as mock_quote, \
         patch("python_service.app.services.discussion_service.discussion_service.run_discussion", new_callable=MagicMock) as mock_discuss:
        
        # run_discussion is an async function, mock it returning mock_messages
        mock_discuss.return_value = asyncio.Future()
        mock_discuss.return_value.set_result(mock_messages)
        
        import pandas as pd
        # Mock 120 days of data
        dates = pd.date_range(end="2026-04-17", periods=120)
        mock_hist.return_value = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": [1600.0] * 120,
            "high": [1700.0] * 120,
            "low": [1500.0] * 120,
            "close": [1650.0] * 120,
            "volume": [10000.0] * 120
        })
        
        mock_summary.return_value = {
            "marketCap": 2.1e12,
            "pe": 30.5,
            "pb": 8.2,
            "industry": "Liquor",
            "totalShares": 1.25e9,
            "floatShares": 1.25e9,
        }
        
        from python_service.app.services.data_providers.base import QuoteData
        mock_quote.return_value = QuoteData(
            symbol=symbol,
            name="贵州茅台",
            price=1650.0,
            open=1600.0,
            high=1700.0,
            low=1500.0,
            last_close=1650.0,
            change=0.0,
            change_pct=0.0,
            volume=10000.0,
            amount=0.0,
            source="mock"
        )
        
        # Start Job
        job_id = await service.start_job(symbol, market)
        assert job_id.startswith("job_")
        
        # Since _run_job is an async task, we need to wait for it or call it directly for the test
        # In this test we use a small sleep to let the task progress or await the internal method
        from unittest.mock import AsyncMock
        service._wait_for_api_key = AsyncMock(return_value="mock_gemini_api_key")
        service._extract_structured_fields = lambda msgs: {"tradingPlan": {"targetPrice": "1800.0"}}
        with patch("app.services.critic_agent.critic_agent.critique", new_callable=AsyncMock) as mock_critique, \
             patch("python_service.app.services.llm_gateway.llm_gateway.validate_api_key", new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = True
            mock_critique.return_value = {"critique": "looks good"}
            await service._run_job(job_id, symbol, market)
        
        # Verify result in DB
        job = job_repo.get_by_id(job_id)
        assert job.status == "completed"
        
        result = job.result_payload if isinstance(job.result_payload, dict) else json.loads(job.result_payload)
        assert result["symbol"] == symbol
        assert "indicators" in result
        assert result["indicators"]["ma_5"] == 1650.0 # Standard for our mock data
        
        # Verify Parquet file exists
        parquet_path = store.glob_path("ohlc", market, symbol)
        import glob
        assert len(glob.glob(parquet_path)) > 0
