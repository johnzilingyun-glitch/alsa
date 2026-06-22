import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
import pandas as pd

from main import app
from app.services.discussion_service import DiscussionService
from app.services.critic_agent import CriticAgent
from app.services.self_reflection_agent import SelfReflectionAgent

client = TestClient(app)

def test_extract_confidence():
    ds = DiscussionService()
    
    # Test Chinese matching
    analysis_zh = "这里有一些分析，投资推荐是买入。推荐置信度: 0.55。原因如下..."
    assert ds._extract_confidence(analysis_zh) == 0.55
    
    # Test percent matching
    analysis_pct = "可信度：80%"
    assert ds._extract_confidence(analysis_pct) == 0.8
    
    # Test English matching
    analysis_en = "My confidence score: 0.45 for this strategy."
    assert ds._extract_confidence(analysis_en) == 0.45
    
    # Test JSON matching
    analysis_json = '{"recommendation": "BUY", "confidence_score": 0.35, "reasons": []}'
    assert ds._extract_confidence(analysis_json) == 0.35
    
    # Test default
    assert ds._extract_confidence("No mention of confidence") == 0.75

@pytest.mark.asyncio
async def test_self_reflection_triggered():
    # Test that self-reflection is triggered when confidence is low (< 0.6)
    ds = DiscussionService()
    
    mock_msg = {
        "role": "Technical Analyst",
        "content": "Confidence score: 0.50. I am not very confident in this trend.",
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
    with patch.object(ds, "_call_expert", AsyncMock(return_value=mock_msg)), \
         patch("app.services.self_reflection_agent.self_reflection_agent.reflect", AsyncMock(return_value=mock_reflection_result)):
        
        topology = [{"round": 1, "experts": ["Technical Analyst"], "parallel": False}]
        with patch.object(ds, "build_topology", return_value=topology), \
             patch("app.services.search_toolkit.search_toolkit.batch_search", AsyncMock(return_value={})):
             
             results = await ds.run_discussion(
                 symbol="AAPL",
                 name="Apple",
                 snapshot={"market": "US"},
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
        "content": "Confidence score: 0.85. Extremely confident in this bullish breakout.",
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
