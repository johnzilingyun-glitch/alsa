from fastapi.testclient import TestClient
from fastapi import FastAPI
import sys
import os
import types
from unittest.mock import AsyncMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

if "thsdk" not in sys.modules:
    thsdk_stub = types.ModuleType("thsdk")

    class THS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    thsdk_stub.THS = THS
    sys.modules["thsdk"] = thsdk_stub

from python_service.app.api.stock import router as stock_router

app = FastAPI()
app.include_router(stock_router, prefix="/api")

client = TestClient(app)

def test_get_comprehensive_financials_ashare():
    # Mock market_data_service.get_financial_summary
    with patch("python_service.app.api.stock.market_data_service.get_financial_summary", new_callable=AsyncMock) as mock_summary:
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
    with patch("python_service.app.api.stock.market_data_service.get_financial_summary", new_callable=AsyncMock) as mock_summary:
        mock_summary.return_value = {"error": "Symbol not found"}
        
        resp = client.get("/api/stock/comprehensive_financials?symbol=INVALID&market=A-Share")
        assert resp.status_code == 200 # App returns 200 with success: false for errors
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "FINANCIALS_FETCH_FAILED"
        assert data["error"]["message"] == "Symbol not found"
        assert data["error"]["details"] == {"error": "Symbol not found"}
        assert data["meta"]["schema_version"]
