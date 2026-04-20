from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app

client = TestClient(app)

def test_get_comprehensive_financials_ashare():
    # Mock market_data_service.get_financial_summary
    with patch("python_service.app.services.market_data_service.market_data_service.get_financial_summary") as mock_summary:
        mock_summary.return_value = {
            "symbol": "600519",
            "market_cap": 2.1e12,
            "pe_ratio": 30.5,
            "dividend_yield": 1.5,
            "net_profit": [100, 110, 125],
            "status": "ok"
        }
        
        resp = client.get("/api/stock/comprehensive_financials?symbol=600519&market=A-Share")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["symbol"] == "600519"
        assert data["data"]["market_cap"] == 2.1e12

def test_get_comprehensive_financials_error():
    with patch("python_service.app.services.market_data_service.market_data_service.get_financial_summary") as mock_summary:
        mock_summary.return_value = {"error": "Symbol not found"}
        
        resp = client.get("/api/stock/comprehensive_financials?symbol=INVALID&market=A-Share")
        assert resp.status_code == 200 # App returns 200 with success: false for errors
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "Symbol not found"
