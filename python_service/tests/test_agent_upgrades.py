import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import pandas as pd

from main import app
from app.services.discussion_service import DiscussionService

client = TestClient(app)

def test_extract_confidence():
    ds = DiscussionService()
    
    # Test JSON with confidence field
    analysis_json_1 = '{"core_thesis": "Thesis...", "confidence": 0.55}'
    assert ds._extract_confidence(analysis_json_1) == 0.55
    
    # Test JSON with confidence percentage representation (e.g. 80.0)
    analysis_json_pct = '{"core_thesis": "Thesis...", "confidence": 80.0}'
    assert ds._extract_confidence(analysis_json_pct) == 0.8
    
    # Test JSON with confidence_score field
    analysis_json_score = '{"recommendation": "BUY", "confidence_score": 0.35, "reasons": []}'
    assert ds._extract_confidence(analysis_json_score) == 0.35
    
    # Test JSON with markdown wrapper
    analysis_markdown = '```json\n{"core_thesis": "Thesis...", "confidence": 0.45}\n```'
    assert ds._extract_confidence(analysis_markdown) == 0.45
    
    # Test default
    assert ds._extract_confidence("No mention of confidence") == 0.75

@pytest.mark.asyncio
async def test_self_reflection_triggered():
    # Test that self-reflection is triggered when confidence is low (< 0.6)
    ds = DiscussionService()
    
    mock_msg = {
        "role": "Technical Analyst",
        "content": '{"confidence": 0.50, "core_thesis": "I am not very confident in this trend.", "key_metrics_extracted": [], "risks": [], "rating": "Hold"}',
        "model": "test-model",
        "timestamp": "now"
    }
    
    mock_reflection_result = {
        "expert_role": "Technical Analyst",
        "round_num": 1,
        "reflection": {
            "logic_gaps": ["No volume confirmation"],
            "confidence_score": 0.5,
            "improved_analysis": "Revised Technical analysis"
        }
    }
    
    # We mock _call_expert to return our low-confidence message
    # NOTE: snapshot must carry a resolvable company name — otherwise the
    # unidentifiable-stock early abort (commit f0a5573) fires before
    # _call_expert and the self-reflection logic under test never runs.
    with patch.object(ds, "_call_expert", AsyncMock(return_value=mock_msg)), \
         patch("app.services.self_reflection_agent.self_reflection_agent.reflect", AsyncMock(return_value=mock_reflection_result)):
        
        topology = [{"round": 1, "experts": ["Technical Analyst"], "parallel": False}]
        with patch.object(ds, "build_topology", return_value=topology), \
             patch("app.services.search_toolkit.search_toolkit.batch_search", AsyncMock(return_value={})):
             
             results = await ds.run_discussion(
                 symbol="AAPL",
                 name="Apple",
                 snapshot={"market": "US", "name": "Apple Inc."},
                 level="standard"
             )
             
             # Assert Technical Analyst message was returned and has reflection attached
             assert len(results) == 1
             assert results[0]["role"] == "Technical Analyst"
             assert "reflection" in results[0]
             assert results[0]["reflection"]["logic_gaps"] == ["No volume confirmation"]

@pytest.mark.asyncio
async def test_self_reflection_skipped_for_high_confidence():
    # Test that self-reflection is skipped when confidence is high (>= 0.6)
    ds = DiscussionService()
    
    mock_msg = {
        "role": "Technical Analyst",
        "content": '{"confidence": 0.85, "core_thesis": "Extremely confident in this breakout.", "key_metrics_extracted": [], "risks": [], "rating": "Buy"}',
        "model": "test-model",
        "timestamp": "now"
    }
    
    # Mock reflect to track if it got called
    mock_reflect = AsyncMock()
    
    with patch.object(ds, "_call_expert", AsyncMock(return_value=mock_msg)), \
         patch("app.services.self_reflection_agent.self_reflection_agent.reflect", mock_reflect):
        
        topology = [{"round": 1, "experts": ["Technical Analyst"], "parallel": False}]
        with patch.object(ds, "build_topology", return_value=topology), \
             patch("app.services.search_toolkit.search_toolkit.batch_search", AsyncMock(return_value={})):
             
             results = await ds.run_discussion(
                 symbol="AAPL",
                 name="Apple",
                 snapshot={"market": "US"},
                 level="standard"
             )
             
             assert len(results) == 1
             assert "reflection" not in results[0]
             mock_reflect.assert_not_called()

def test_monte_carlo_endpoint():
    # Mock portfolio backtest closes and execution
    mock_closes = pd.DataFrame({
        "AAPL": [150.0, 152.0, 151.0, 153.0]
    }, index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]))
    
    mock_backtest_res = {
        "metrics": {
            "annualized_return": {"risk": 0.15},
            "sharpe_ratio": 1.5,
            "max_drawdown": {"risk": -0.05}
        }
    }
    
    with patch("yfinance.download", return_value=mock_closes), \
         patch("app.services.portfolio_real_backtest.PortfolioBacktester.run_pandas_portfolio_backtest", return_value=mock_backtest_res):
         
         response = client.post("/api/backtest/monte-carlo", json={
             "start_date": "2026-01-01",
             "end_date": "2026-01-04",
             "model": "portfolio_cross_sectional",
             "market": "US",
             "config": {"custom_symbols": ["AAPL"]},
             "n_simulations": 10
         }, headers={"Authorization": "Bearer mock-token"})
         
         assert response.status_code == 200
         data = response.json()
         assert data["status"] == "completed"
         assert "results" in data
         assert "report" in data
         assert data["results"]["n_successful"] == 10
         assert "return_stats" in data["results"]
         assert "risk_metrics" in data["results"]

@pytest.mark.asyncio
async def test_backtest_agent_runs_sector_backtest():
    ds = DiscussionService()
    
    mock_closes = pd.DataFrame({
        "600519.SS": [150.0, 152.0, 151.0, 153.0],
        "601398.SS": [5.0, 5.1, 5.05, 5.2]
    }, index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]))
    
    mock_pe = pd.DataFrame(10.0, index=mock_closes.index, columns=["600519.SS", "601398.SS"])
    mock_mc = pd.DataFrame(2000.0, index=mock_closes.index, columns=["600519.SS", "601398.SS"])
    
    mock_msg = {
        "role": "Sector Stock Screener",
        "content": '{"confidence": 0.8, "core_thesis": "Recommended list: 600519, 601398", "key_metrics_extracted": [], "risks": [], "rating": "Buy"}',
        "model": "test-model",
        "timestamp": "now"
    }
    
    original_call_expert = ds._call_expert
    async def mock_call_expert_side_effect(role, *args, **kwargs):
        if role == "Backtest Agent":
            return await original_call_expert(role, *args, **kwargs)
        return mock_msg

    with patch("yfinance.download", return_value=mock_closes), \
         patch("app.services.portfolio_real_backtest.PortfolioBacktester.load_fundamentals", return_value=(mock_pe, mock_mc)), \
         patch.object(ds, "_call_expert", side_effect=mock_call_expert_side_effect), \
         patch("app.services.search_toolkit.search_toolkit.batch_search", AsyncMock(return_value={})):
         
         results = await ds.run_discussion(
             symbol="CNY",
             name="消费",
             snapshot={"market": "A-Share"},
             level="sector"
         )
         
         backtest_msg = next((r for r in results if r["role"] == "Backtest Agent"), None)
         assert backtest_msg is not None
         assert backtest_msg["model"] == "quant_engine"
         
         import json
         data = json.loads(backtest_msg["content"])
         assert "core_thesis" in data
         assert "key_metrics_extracted" in data
         assert "risks" in data
         assert "confidence" in data
