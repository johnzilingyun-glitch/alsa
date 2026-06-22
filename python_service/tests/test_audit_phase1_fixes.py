import sys
import os
import pytest
from unittest.mock import patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.vector.lancedb_store import LanceResearchStore
from app.services.expert_tools import ToolExecutor
from app.services.computation_tools import dcf_calculate

def test_lancedb_symbol_sanitization(tmp_path):
    # Setup tmp lancedb
    db_root = tmp_path / "lancedb"
    store = LanceResearchStore(str(db_root))
    
    # Check that search performs symbol sanitization and executes without crashing
    results = store.search(symbol="AAPL'; DROP TABLE research_chunks; --", query_vector=[0.1]*768, limit=1)
    assert isinstance(results, list)

def test_deep_scrape_url_validation():
    executor = ToolExecutor()
    
    # Valid whitelisted domains
    assert executor._validate_scrape_url("https://seekingalpha.com/article/123") is True
    assert executor._validate_scrape_url("https://finance.yahoo.com/quote/AAPL") is True
    assert executor._validate_scrape_url("https://eastmoney.com/news") is True
    
    # Invalid/unauthorized domains
    assert executor._validate_scrape_url("https://malicious-site.com/hack") is False
    
    # SSRF / local/private networks
    assert executor._validate_scrape_url("http://localhost:8000/admin") is False
    assert executor._validate_scrape_url("http://127.0.0.1:8000/admin") is False
    assert executor._validate_scrape_url("http://192.168.1.1/admin") is False
    assert executor._validate_scrape_url("http://10.0.0.1/admin") is False
    assert executor._validate_scrape_url("http://169.254.169.254/metadata") is False
    assert executor._validate_scrape_url("ftp://seekingalpha.com/article/123") is False

@patch('yfinance.Ticker', side_effect=Exception("Mock network failure"))
def test_dcf_calculator_sanity_checks(mock_yf):
    # Valid DCF params
    valid_params = {
        "fcf_base": 100.0,
        "growth_rates": [0.10, 0.08, 0.07, 0.06, 0.05],
        "terminal_growth": 0.03,
        "wacc": 0.09,
        "shares_outstanding": 10.0,
        "net_debt": 50.0
    }
    
    res = dcf_calculate(valid_params)
    assert "DCF ERROR" not in res
    
    # Invalid beta
    params = valid_params.copy()
    params["beta"] = 4.0 # > 3
    res = dcf_calculate(params)
    assert "DCF ERROR: Unreasonable beta" in res

    # Invalid terminal growth rate
    params = valid_params.copy()
    params["terminal_growth"] = 0.10 # > 8%
    res = dcf_calculate(params)
    assert "DCF ERROR: Unreasonable terminal growth rate" in res
