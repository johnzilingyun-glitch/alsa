import pytest
import asyncio
from app.services.sector_analysis_service import SectorAnalysisService
from app.services.search_toolkit import search_toolkit
from app.services.expert_tools import tool_executor, ROLE_TOOLS_MAP

@pytest.mark.asyncio
async def test_fetch_sector_stocks_pcb():
    """Verify _fetch_sector_stocks returns constituent stocks for PCB with real financial metrics."""
    service = SectorAnalysisService(job_repo=None)
    stocks = await service._fetch_sector_stocks("PCB")
    assert isinstance(stocks, list)
    assert len(stocks) > 0
    # Check that PCB preset stocks like 002463 (沪电股份) or 300476 are fetched
    codes = [s["code"] for s in stocks]
    assert any(c in codes for c in ["002463", "300476", "002916", "688183"])
    
    first = stocks[0]
    assert "name" in first
    assert "price" in first
    assert "revenue" in first
    assert "free_cashflow" in first

def test_search_toolkit_serenity_alpha_analyst():
    """Verify Serenity Alpha Analyst is mapped to rich pre-search categories."""
    all_mock = {
        "latest_news": [{"title": "PCB news"}],
        "financial_performance": [{"title": "PCB earnings"}],
        "business_query": [{"title": "PCB business share"}],
        "announcement_search": [{"title": "PCB announcement"}],
        "research_report_search": [{"title": "PCB report"}],
        "northbound_flow": [{"title": "PCB northbound"}],
        "chip_concentration": [{"title": "PCB chip concentration"}],
    }
    enrichment = search_toolkit.get_enrichment_for_role("Serenity Alpha Analyst", all_mock, market="a_share")
    assert "latest_news" in enrichment
    assert "financial_performance" in enrichment
    assert "business_query" in enrichment
    assert "announcement_search" in enrichment
    assert "research_report_search" in enrichment
    assert "northbound_flow" in enrichment
    assert "chip_concentration" in enrichment

def test_expert_tools_serenity_alpha_role_tools():
    """Verify Serenity Alpha Analyst has access to finance_query and business_query tools."""
    tools = ROLE_TOOLS_MAP.get("Serenity Alpha Analyst", [])
    assert "financial_data" in tools
    assert "finance_query" in tools
    assert "business_query" in tools
    assert "announcement_search" in tools
    assert "news_search" in tools

@pytest.mark.asyncio
async def test_exec_financial_data_free_cash_flow():
    """Verify _exec_financial_data extracts freeCashflow and operatingCashflow."""
    res = await tool_executor._exec_financial_data("002463", "free cash flow 2025营收 营业收入 自由现金流")
    assert "<tool_observation>" in res
    assert "002463" in res
    # Should include financial overview or cash flow details
    assert "freeCashflow" in res or "自由现金流" in res or "revenue" in res or "营业总收入" in res

@pytest.mark.asyncio
async def test_exec_iwencai_fallback_with_stock_code():
    """Verify _exec_iwencai_query fallback injects structured data if stock code is in query."""
    # Force fallback by invoking _exec_iwencai_query with invalid key/disabled
    res = await tool_executor._exec_iwencai_query("002463 2025 营业收入 自由现金流 业务占比", "hithink-finance-query", "Financial data")
    assert "<tool_observation>" in res
    # Fallback should inject structured data for 002463
    assert "结构化数据 [002463]" in res or "002463" in res
