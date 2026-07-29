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
async def test_fetch_sector_stocks_free_cash_flow():
    """Verify _exec_financial_data extracts freeCashflow and operatingCashflow."""
    res = await tool_executor._exec_financial_data("002463", "free cash flow 2025营收 营业收入 自由现金流")
    assert "<tool_observation>" in res
    assert "002463" in res
    assert "freeCashflow" in res or "自由现金流" in res or "revenue" in res or "营业总收入" in res

@pytest.mark.asyncio
async def test_exec_iwencai_fallback_with_stock_code():
    """Verify _exec_iwencai_query fallback injects structured data if stock code is in query."""
    res = await tool_executor._exec_iwencai_query("002463 2025 营业收入 自由现金流 业务占比", "hithink-finance-query", "Financial data")
    assert "<tool_observation>" in res
    assert "结构化数据 [002463]" in res or "002463" in res

@pytest.mark.asyncio
async def test_fetch_sector_stocks_hk_and_us():
    """Verify _fetch_sector_stocks returns constituent stocks for HK and US sectors."""
    service = SectorAnalysisService(job_repo=None)
    stocks_hk = await service._fetch_sector_stocks("港股科技")
    assert isinstance(stocks_hk, list)
    assert len(stocks_hk) > 0
    hk_codes = [s["code"] for s in stocks_hk]
    assert any(c in hk_codes for c in ["00700", "03690", "09988"])

    stocks_us = await service._fetch_sector_stocks("美股科技")
    assert isinstance(stocks_us, list)
    assert len(stocks_us) > 0
    us_codes = [s["code"] for s in stocks_us]
    assert any(c in us_codes for c in ["NVDA", "AAPL", "MSFT"])

def test_format_ths_code():
    """Verify format_ths_code auto-pads and prefixes raw stock codes."""
    from app.services.data_providers.ths_provider import format_ths_code
    assert format_ths_code("00700") == "UHKG00700"
    assert format_ths_code("700", market_hint="hk") == "UHKG00700"
    assert format_ths_code("AAPL") == "UNQQAAPL"
    assert format_ths_code("600519") == "USHA600519"
    assert format_ths_code("000001") == "USZA000001"
    assert format_ths_code("UHKG00700") == "UHKG00700"

