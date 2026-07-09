"""
Automated integration tests for all expert tool call functions.

Tests:
  - Each tool can be called without crashing
  - Returns valid <tool_observation> format
  - Latency is within acceptable bounds
  - Graceful degradation on failure (no error markers that trigger retries)

Usage:
    cd /home/ubuntu/work/alsa
    python_service/.venv/bin/python -m pytest python_service/tests/test_tool_calls.py -v --timeout=120
"""
import asyncio
import time
import pytest
import sys
import os

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SQLITE_PATH", "/tmp/test_tools.db")
os.environ.setdefault("API_TOKEN", "mock-token")


# ─── Fixtures ───

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def tool_executor():
    from app.services.expert_tools import ToolExecutor
    return ToolExecutor()


# ─── Helpers ───

LATENCY_THRESHOLDS = {
    "web_search": 20.0,
    "news_search": 20.0,
    "announcement_search": 20.0,
    "report_search": 20.0,
    "knowledge_search": 2.0,
    "deep_scrape": 20.0,
    "financial_data": 35.0,
    "macro_query": 20.0,
    "business_query": 20.0,
    "finance_query": 20.0,
    "management_query": 20.0,
    "commodity_price_query": 20.0,
    "futures_query": 20.0,
    "valuation_query": 20.0,
    "industry_query": 20.0,
    "policy_query": 20.0,
    # Computation tools (first call has import overhead)
    "dcf_calculator": 5.0,
    "position_sizer": 5.0,
    "kelly_calculator": 5.0,
    "pillar_scorer": 5.0,
    "risk_reward": 5.0,
    "cagr_calculator": 5.0,
}

# Error markers that should NOT appear in tool output (they trigger model retries)
FORBIDDEN_MARKERS = [
    "Error executing",
    "⚠ quarterly failed",
    "⚠ balance sheet failed",
    "⚠ cash flow failed",
    "⚠ income statement failed",
    "⚠ dividend failed",
    "⚠ peer comparison failed",
    "⚠ Financial data query failed",
]


def assert_valid_observation(result: str, tool_name: str):
    """Validate tool output format and content."""
    assert result is not None, f"{tool_name}: returned None"
    assert len(result) > 0, f"{tool_name}: returned empty string"
    assert "<tool_observation>" in result, f"{tool_name}: missing <tool_observation> tag"
    assert "</tool_observation>" in result, f"{tool_name}: missing </tool_observation> tag"
    
    # Check no forbidden error markers
    for marker in FORBIDDEN_MARKERS:
        assert marker not in result, f"{tool_name}: contains forbidden error marker '{marker}'"


def assert_latency_ok(elapsed: float, tool_name: str):
    """Check tool latency is within threshold."""
    threshold = LATENCY_THRESHOLDS.get(tool_name, 30.0)
    assert elapsed < threshold, f"{tool_name}: latency {elapsed:.1f}s exceeds threshold {threshold}s"


# ─── Test Cases: Search Tools ───

class TestSearchTools:
    """Test web_search, news_search, and related search tools."""

    @pytest.mark.asyncio
    async def test_web_search(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "web_search",
            "reason": "test",
            "query": "贵州茅台 最新财报"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "web_search")
        assert_latency_ok(elapsed, "web_search")
        print(f"  web_search: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_news_search(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "news_search",
            "reason": "test",
            "query": "人工智能 芯片 最新动态"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "news_search")
        assert_latency_ok(elapsed, "news_search")
        print(f"  news_search: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_announcement_search(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "announcement_search",
            "reason": "test",
            "query": "贵州茅台 分红公告"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "announcement_search")
        assert_latency_ok(elapsed, "announcement_search")
        print(f"  announcement_search: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_report_search(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "report_search",
            "reason": "test",
            "query": "宁德时代 研报 目标价"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "report_search")
        assert_latency_ok(elapsed, "report_search")
        print(f"  report_search: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_knowledge_search(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "knowledge_search",
            "reason": "test",
            "query": "NVO valuation concerns"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "knowledge_search")
        assert_latency_ok(elapsed, "knowledge_search")
        print(f"  knowledge_search: {elapsed:.1f}s, {len(result)} chars")


# ─── Test Cases: Iwencai Query Tools ───

class TestIwencaiTools:
    """Test all Iwencai-based query tools."""

    @pytest.mark.asyncio
    async def test_macro_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "macro_query",
            "reason": "test",
            "query": "中国最新GDP同比增速"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "macro_query")
        assert_latency_ok(elapsed, "macro_query")
        print(f"  macro_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_business_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "business_query",
            "reason": "test",
            "query": "贵州茅台 主营业务构成"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "business_query")
        assert_latency_ok(elapsed, "business_query")
        print(f"  business_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_finance_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "finance_query",
            "reason": "test",
            "query": "贵州茅台 ROE 净利润 营收"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "finance_query")
        assert_latency_ok(elapsed, "finance_query")
        print(f"  finance_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_management_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "management_query",
            "reason": "test",
            "query": "贵州茅台 前十大股东"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "management_query")
        assert_latency_ok(elapsed, "management_query")
        print(f"  management_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_commodity_price_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "commodity_price_query",
            "reason": "test",
            "query": "碳酸锂 最新价格"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "commodity_price_query")
        assert_latency_ok(elapsed, "commodity_price_query")
        print(f"  commodity_price_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_futures_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "futures_query",
            "reason": "test",
            "query": "螺纹钢现货价格"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "futures_query")
        assert_latency_ok(elapsed, "futures_query")
        print(f"  futures_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_valuation_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "valuation_query",
            "reason": "test",
            "query": "贵州茅台 市盈率 市净率"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "valuation_query")
        assert_latency_ok(elapsed, "valuation_query")
        print(f"  valuation_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_industry_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "industry_query",
            "reason": "test",
            "query": "低空经济 概念股"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "industry_query")
        assert_latency_ok(elapsed, "industry_query")
        print(f"  industry_query: {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_policy_query(self, tool_executor):
        start = time.time()
        result = await tool_executor.execute({
            "tool": "policy_query",
            "reason": "test",
            "query": "半导体产业政策利好"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "policy_query")
        assert_latency_ok(elapsed, "policy_query")
        print(f"  policy_query: {elapsed:.1f}s, {len(result)} chars")


# ─── Test Cases: Financial Data Tool ───

class TestFinancialDataTool:
    """Test financial_data with different markets and query types."""

    @pytest.mark.asyncio
    async def test_a_share_basic(self, tool_executor):
        """A-Share: DataRouter primary path."""
        start = time.time()
        result = await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "600519",
            "query": "quarterly earnings revenue profit"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "financial_data")
        assert_latency_ok(elapsed, "financial_data")
        # Should have DataRouter section
        assert "DataRouter" in result or "财务概览" in result, "Missing DataRouter financial summary"
        print(f"  financial_data(A-share): {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_a_share_balance_sheet(self, tool_executor):
        """A-Share: Balance sheet via yfinance."""
        start = time.time()
        result = await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "000333",
            "query": "balance sheet cash debt assets"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "financial_data")
        assert_latency_ok(elapsed, "financial_data")
        print(f"  financial_data(balance): {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_a_share_dividend(self, tool_executor):
        """A-Share: Dividend history with AkShare fallback."""
        start = time.time()
        result = await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "600519",
            "query": "dividend 分红历史"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "financial_data")
        assert_latency_ok(elapsed, "financial_data")
        print(f"  financial_data(dividend): {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_us_stock(self, tool_executor):
        """US Stock: yfinance path."""
        start = time.time()
        result = await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "AAPL",
            "query": "quarterly earnings revenue valuation PE"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "financial_data")
        assert_latency_ok(elapsed, "financial_data")
        print(f"  financial_data(US): {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_cache_hit(self, tool_executor):
        """Second call should hit cache and be fast."""
        # First call (populates cache)
        await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "600519",
            "query": "quarterly earnings revenue profit"
        })
        
        # Second call (should hit cache)
        start = time.time()
        result = await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "600519",
            "query": "quarterly earnings revenue profit"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "financial_data")
        assert elapsed < 0.5, f"Cache hit should be < 0.5s, got {elapsed:.2f}s"
        print(f"  financial_data(cache): {elapsed:.3f}s")


# ─── Test Cases: Deep Scrape ───

class TestDeepScrape:
    """Test deep_scrape with fallback behavior."""

    @pytest.mark.asyncio
    async def test_blocked_domain_fallback(self, tool_executor):
        """Blocked domain should auto-fallback to web_search."""
        start = time.time()
        result = await tool_executor.execute({
            "tool": "deep_scrape",
            "reason": "test",
            "url": "https://finance.yahoo.com/quote/AAPL",
            "query": "AAPL stock price"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "deep_scrape")
        assert "Auto-fallback" in result or "web_search" in result, "Should show fallback message"
        assert_latency_ok(elapsed, "deep_scrape")
        print(f"  deep_scrape(blocked): {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_invalid_url_rejected(self, tool_executor):
        """SSRF prevention: localhost should be rejected."""
        result = await tool_executor.execute({
            "tool": "deep_scrape",
            "reason": "test",
            "url": "http://localhost:8080/admin",
            "query": "test"
        })
        assert "not whitelisted" in result or "invalid" in result

    @pytest.mark.asyncio
    async def test_valid_url(self, tool_executor):
        """Valid whitelisted URL should work or fallback gracefully."""
        start = time.time()
        result = await tool_executor.execute({
            "tool": "deep_scrape",
            "reason": "test",
            "url": "https://xueqiu.com/S/SH600519",
            "query": "贵州茅台 股票信息"
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "deep_scrape")
        assert_latency_ok(elapsed, "deep_scrape")
        print(f"  deep_scrape(valid): {elapsed:.1f}s, {len(result)} chars")


# ─── Test Cases: Computation Tools ───

class TestComputationTools:
    """Test deterministic computation tools (no network needed)."""

    @pytest.mark.asyncio
    async def test_dcf_calculator(self, tool_executor):
        import json
        start = time.time()
        result = await tool_executor.execute({
            "tool": "dcf_calculator",
            "reason": "test",
            "params_json": json.dumps({
                "fcf_base": 85000,
                "growth_rates": [0.15, 0.12, 0.10, 0.08, 0.06],
                "terminal_growth": 0.03,
                "wacc": 0.09,
                "shares_outstanding": 7440,
                "net_debt": -45000,
                "currency": "USD"
            })
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "dcf_calculator")
        assert_latency_ok(elapsed, "dcf_calculator")
        assert "intrinsic" in result.lower() or "fair value" in result.lower() or "per share" in result.lower()
        print(f"  dcf_calculator: {elapsed:.3f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_position_sizer(self, tool_executor):
        import json
        start = time.time()
        result = await tool_executor.execute({
            "tool": "position_sizer",
            "reason": "test",
            "params_json": json.dumps({
                "account_size": 100000,
                "entry_price": 410,
                "stop_price": 385,
                "risk_pct": 1.0,
                "currency": "USD"
            })
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "position_sizer")
        assert_latency_ok(elapsed, "position_sizer")
        assert "shares" in result.lower() or "position" in result.lower()
        print(f"  position_sizer: {elapsed:.3f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_kelly_calculator(self, tool_executor):
        import json
        start = time.time()
        result = await tool_executor.execute({
            "tool": "kelly_calculator",
            "reason": "test",
            "params_json": json.dumps({
                "win_rate": 0.55,
                "avg_win": 2.0,
                "avg_loss": 1.0,
                "fraction": 0.5
            })
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "kelly_calculator")
        assert_latency_ok(elapsed, "kelly_calculator")
        print(f"  kelly_calculator: {elapsed:.3f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_pillar_scorer(self, tool_executor):
        import json
        start = time.time()
        result = await tool_executor.execute({
            "tool": "pillar_scorer",
            "reason": "test",
            "params_json": json.dumps({
                "pillars": [
                    {"name": "Revenue growth", "status": "on_track", "weight": 30, "evidence": "+22% YoY"},
                    {"name": "Margin expansion", "status": "mixed", "weight": 25, "evidence": "Flat QoQ"},
                    {"name": "Market share", "status": "on_track", "weight": 20, "evidence": "Gaining"},
                ],
                "kill_switches": ["Revenue growth"]
            })
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "pillar_scorer")
        assert_latency_ok(elapsed, "pillar_scorer")
        print(f"  pillar_scorer: {elapsed:.3f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_risk_reward(self, tool_executor):
        import json
        start = time.time()
        result = await tool_executor.execute({
            "tool": "risk_reward",
            "reason": "test",
            "params_json": json.dumps({
                "entry": 410,
                "target": 460,
                "stop": 385,
                "win_probability": 0.55
            })
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "risk_reward")
        assert_latency_ok(elapsed, "risk_reward")
        print(f"  risk_reward: {elapsed:.3f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_cagr_calculator(self, tool_executor):
        import json
        start = time.time()
        result = await tool_executor.execute({
            "tool": "cagr_calculator",
            "reason": "test",
            "params_json": json.dumps({
                "start_value": 168000,
                "end_value": 245000,
                "years": 3
            })
        })
        elapsed = time.time() - start
        
        assert_valid_observation(result, "cagr_calculator")
        assert_latency_ok(elapsed, "cagr_calculator")
        print(f"  cagr_calculator: {elapsed:.3f}s, {len(result)} chars")


# ─── Test Cases: Error Handling & Graceful Degradation ───

class TestGracefulDegradation:
    """Test that tools fail gracefully without returning error markers."""

    @pytest.mark.asyncio
    async def test_unknown_tool(self, tool_executor):
        """Unknown tool should return clear message."""
        result = await tool_executor.execute({
            "tool": "nonexistent_tool",
            "reason": "test",
            "query": "test"
        })
        assert "Unknown tool" in result or "not found" in result or "unavailable" in result

    @pytest.mark.asyncio
    async def test_empty_query(self, tool_executor):
        """Empty query should return error without crashing."""
        result = await tool_executor.execute({
            "tool": "web_search",
            "reason": "test",
            "query": ""
        })
        assert result is not None
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_financial_data_invalid_symbol(self, tool_executor):
        """Invalid symbol should return gracefully."""
        start = time.time()
        result = await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "INVALID999",
            "query": "quarterly earnings"
        })
        elapsed = time.time() - start
        
        assert result is not None
        # Should NOT contain forbidden error markers
        for marker in FORBIDDEN_MARKERS:
            assert marker not in result, f"Contains forbidden marker: {marker}"
        print(f"  financial_data(invalid): {elapsed:.1f}s, {len(result)} chars")

    @pytest.mark.asyncio
    async def test_financial_data_missing_symbol(self, tool_executor):
        """Missing symbol param should return clear error."""
        result = await tool_executor.execute({
            "tool": "financial_data",
            "reason": "test",
            "symbol": "",
            "query": "test"
        })
        assert "requires" in result or "parameter" in result

    @pytest.mark.asyncio
    async def test_deep_scrape_missing_url(self, tool_executor):
        """Missing URL should return clear error."""
        result = await tool_executor.execute({
            "tool": "deep_scrape",
            "reason": "test",
            "url": "",
            "query": "test"
        })
        assert "requires" in result or "parameter" in result


# ─── Test Cases: Parallel Execution ───

class TestParallelExecution:
    """Test execute_all for parallel tool execution."""

    @pytest.mark.asyncio
    async def test_parallel_3_tools(self, tool_executor):
        """3 tools in parallel should complete within combined single-tool time."""
        tool_calls = [
            {"tool": "web_search", "reason": "test", "query": "NVIDIA stock 2026"},
            {"tool": "news_search", "reason": "test", "query": "AI chip latest news"},
            {"tool": "knowledge_search", "reason": "test", "query": "tech sector analysis"},
        ]
        
        start = time.time()
        results = await tool_executor.execute_all(tool_calls)
        elapsed = time.time() - start
        
        assert len(results) == 3
        for i, result in enumerate(results):
            assert "<tool_observation>" in result, f"Tool {i} missing observation tag"
            assert "</tool_observation>" in result, f"Tool {i} missing closing tag"
        
        # Parallel should be faster than sequential (< sum of individual thresholds)
        assert elapsed < 40.0, f"Parallel execution too slow: {elapsed:.1f}s"
        print(f"  parallel(3 tools): {elapsed:.1f}s")

    @pytest.mark.asyncio
    async def test_parallel_with_failure(self, tool_executor):
        """One failing tool should not crash others."""
        tool_calls = [
            {"tool": "web_search", "reason": "test", "query": "Apple stock"},
            {"tool": "financial_data", "reason": "test", "symbol": "INVALID", "query": "test"},
            {"tool": "knowledge_search", "reason": "test", "query": "test"},
        ]
        
        results = await tool_executor.execute_all(tool_calls)
        assert len(results) == 3
        # All should return something (no crashes)
        for result in results:
            assert result is not None
            assert len(result) > 0


# ─── Latency Summary Report ───

class TestLatencySummary:
    """Run all tools and produce a latency summary report."""

    @pytest.mark.asyncio
    async def test_full_latency_report(self, tool_executor):
        """Run representative tools and report latencies."""
        import json
        
        test_cases = [
            ("web_search", {"tool": "web_search", "reason": "test", "query": "stock market today"}),
            ("news_search", {"tool": "news_search", "reason": "test", "query": "A股 今日行情"}),
            ("financial_data(A)", {"tool": "financial_data", "reason": "test", "symbol": "000792", "query": "quarterly earnings"}),
            ("financial_data(US)", {"tool": "financial_data", "reason": "test", "symbol": "MSFT", "query": "valuation PE PB"}),
            ("macro_query", {"tool": "macro_query", "reason": "test", "query": "中国CPI同比"}),
            ("knowledge_search", {"tool": "knowledge_search", "reason": "test", "query": "risk analysis"}),
            ("position_sizer", {"tool": "position_sizer", "reason": "test", "params_json": json.dumps({"account_size": 100000, "entry_price": 100, "stop_price": 95, "risk_pct": 1.0})}),
        ]
        
        print("\n" + "=" * 60)
        print("  TOOL LATENCY REPORT")
        print("=" * 60)
        
        total_time = 0
        results_summary = []
        
        for name, call in test_cases:
            start = time.time()
            result = await tool_executor.execute(call)
            elapsed = time.time() - start
            total_time += elapsed
            
            status = "✅" if elapsed < LATENCY_THRESHOLDS.get(call["tool"], 30.0) else "⚠️"
            has_data = "No results" not in result and len(result) > 100
            data_status = "✓" if has_data else "✗"
            
            results_summary.append((name, elapsed, status, data_status, len(result)))
            print(f"  {status} {name:25s} {elapsed:6.1f}s  data:{data_status}  {len(result):5d} chars")
        
        print("-" * 60)
        print(f"  Total: {total_time:.1f}s for {len(test_cases)} tools")
        print(f"  Average: {total_time/len(test_cases):.1f}s per tool")
        print("=" * 60)
        
        # Overall assertion: average tool latency should be reasonable
        avg = total_time / len(test_cases)
        assert avg < 15.0, f"Average tool latency {avg:.1f}s exceeds 15s threshold"
