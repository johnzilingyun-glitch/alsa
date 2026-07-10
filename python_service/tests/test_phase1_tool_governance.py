"""Phase 1 工具治理层测试 — 能力矩阵 / 前置校验 / 共享缓存 / fallback / metrics.

对应开发指南 §4.6 ToolRegistry + 调用治理.
覆盖: ToolRegistry 升级后的治理特性, 同时保证向后兼容 API.
"""
import pytest

from app.services.tools.registry import ToolRegistry, tool_registry
from app.services.tools.shared_cache import SharedToolCache, make_cache_key
from app.services.tools.preconditions import (
    validate_precondition, is_valid_result, normalize_market,
)
from app.services.tools.metrics import ToolMetrics
from app.schemas.contracts import ToolCall, ToolResult


# ── 向后兼容 ────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_registry():
    """提供独立 ToolRegistry 实例, 不污染全局单例."""
    return ToolRegistry()


def test_backward_compat_register(clean_registry):
    """原 register 装饰器 + get_tool + get_all_schemas 仍工作."""
    schema = {"name": "test_search", "description": "A test search tool"}

    @clean_registry.register(schema)
    async def mock_search(params):
        return f"Searched for {params.get('query')}"

    assert "test_search" in clean_registry.get_registered_names()
    assert len(clean_registry.get_all_schemas()) == 1
    assert clean_registry.get_all_schemas()[0] == schema
    assert not clean_registry.is_computation_tool("test_search")


def test_backward_compat_computation(clean_registry):
    schema = {"name": "test_calc", "description": "A test calc tool"}

    @clean_registry.register(schema, is_computation=True)
    def mock_calc(params):
        return "Calculated"

    assert clean_registry.is_computation_tool("test_calc")


# ── 能力矩阵 ────────────────────────────────────────────────────────────────

def test_capability_matrix_resolve():
    """resolve(data_type) 返回按优先级排序的候选工具."""
    news_tools = tool_registry.resolve("news")
    assert news_tools[0]["tool_id"] == "news_search"
    assert news_tools[1]["tool_id"] == "web_search"
    assert news_tools[0]["priority"] < news_tools[1]["priority"]


def test_register_capability(clean_registry):
    """显式登记能力后能 resolve 到."""
    clean_registry.register_capability("realtime_quote", "my_quote", 1)
    clean_registry.register_capability("realtime_quote", "my_quote", 2)  # 更低优先级不覆盖
    resolved = clean_registry.resolve("realtime_quote")
    ids = [t["tool_id"] for t in resolved]
    assert "my_quote" in ids


# ── 前置校验 (§4.6.3 无效调用拦截) ──────────────────────────────────────────

def test_precondition_market_block():
    """港股 symbol 调 financial_data 应被市场校验拦截."""
    ok, reason = validate_precondition("financial_data", {"symbol": "0700.HK"}, "HK-Share")
    assert not ok
    assert "港股" in reason or "HK" in reason


def test_precondition_market_allow():
    """A股/美股调 financial_data 应放行."""
    ok, _ = validate_precondition("financial_data", {"symbol": "600519.SH"}, "A股")
    assert ok
    ok, _ = validate_precondition("financial_data", {"symbol": "AAPL"}, "美股")
    assert ok


def test_precondition_missing_param():
    """缺 symbol 调 macro_query 应被参数校验拦截."""
    ok, reason = validate_precondition("macro_query", {}, "美股")
    assert not ok
    assert "symbol" in reason


def test_precondition_requires_any():
    """requires_any: 任一参数即可."""
    ok, _ = validate_precondition("finance_query", {"query": "营收"}, "A股")
    assert ok
    ok, reason = validate_precondition("finance_query", {}, "A股")
    assert not ok


def test_precondition_approval_gate():
    """deep_scrape 需审批, 未授权应拦截."""
    ok, _ = validate_precondition("deep_scrape", {"url": "http://x"}, "", approval_granted=False)
    assert not ok
    ok, _ = validate_precondition("deep_scrape", {"url": "http://x"}, "", approval_granted=True)
    assert ok


def test_precondition_passthrough():
    """无前置条件定义的工具放行."""
    ok, _ = validate_precondition("unknown_tool", {"x": 1}, "A股")
    assert ok


# ── 结果有效性校验 (§4.6.3 garbage 拦截) ────────────────────────────────────

@pytest.mark.parametrize("data,expected", [
    ("valid data", True),
    ("", False),
    ("error", False),
    ("Error: timeout", False),
    ("null", False),
    ([], False),
    ({}, False),
    ([1, 2], True),
    ({"k": "v"}, True),
    (None, False),
])
def test_is_valid_result(data, expected):
    assert is_valid_result(data) is expected


# ── 共享缓存 (§4.6.2 L2 跨 Agent) ───────────────────────────────────────────

def test_shared_cache_hit_miss():
    """同 cache_key 二次 get 命中."""
    cache = SharedToolCache()
    key = make_cache_key("news_search", {"symbol": "AAPL", "query": "earnings"})
    assert cache.get(key) is None  # 未命中
    cache.set(key, "result text", data_type="news")
    assert cache.get(key) == "result text"  # 命中


def test_shared_cache_key_normalization():
    """参数顺序与空格不影响命中."""
    k1 = make_cache_key("t", {"a": "x y", "b": "z"})
    k2 = make_cache_key("t", {"b": "z", "a": "X  Y"})
    assert k1 == k2


def test_shared_cache_invalidate_prefix():
    cache = SharedToolCache()
    cache.set("t|a=1", "r1", data_type="news")
    cache.set("t|a=2", "r2", data_type="news")
    cache.set("other|a=1", "r3", data_type="news")
    n = cache.invalidate_prefix("t")
    assert n == 2
    assert cache.get("t|a=1") is None
    assert cache.get("other|a=1") == "r3"


def test_shared_cache_ttl_expiry():
    """过期条目应失效."""
    cache = SharedToolCache()
    cache.set("k", "v", ttl=0)  # 0 秒 TTL
    import time
    time.sleep(0.01)
    assert cache.get("k") is None


# ── execute 治理流程 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_cache_hit(clean_registry):
    """首次执行 ok, 二次命中 cached."""
    @clean_registry.register({"name": "q", "description": "q"})
    async def q(params):
        return "data:" + params.get("symbol", "")

    clean_registry.register_capability("realtime_quote", "q", 1)
    call = ToolCall(tool_id="q", params={"symbol": "AAPL"}, market="美股")
    r1 = await clean_registry.execute(call)
    assert r1.status == "ok"
    assert r1.from_cache is False
    r2 = await clean_registry.execute(call)
    assert r2.status == "cached"
    assert r2.from_cache is True
    assert r2.data == r1.data


@pytest.mark.asyncio
async def test_execute_invalid_blocked(clean_registry):
    """前置校验失败返回 invalid."""
    @clean_registry.register({"name": "fin", "description": "fin"})
    async def fin(params):
        return "should not be called"

    clean_registry.register_capability("financial_stmt", "fin", 1)
    # 港股调 financial_data 类工具应被拦
    call = ToolCall(tool_id="financial_data", params={"symbol": "0700.HK"}, market="HK-Share")
    r = await clean_registry.execute(call)
    assert r.status == "invalid"


@pytest.mark.asyncio
async def test_execute_fallback(clean_registry):
    """首选工具返回无效结果时, 降级到 fallback 候选工具."""
    @clean_registry.register({"name": "primary", "description": "p"})
    async def primary(params):
        return ""  # 无效结果

    @clean_registry.register({"name": "backup", "description": "b"})
    async def backup(params):
        return "backup data"

    clean_registry.register_capability("realtime_quote", "primary", 1)
    clean_registry.register_capability("realtime_quote", "backup", 2)
    call = ToolCall(tool_id="primary", params={"symbol": "AAPL"}, market="美股")
    r = await clean_registry.execute(call)
    assert r.status == "degraded"
    assert r.tool_id == "backup"
    assert r.data == "backup data"


# ── metrics (§4.6.4) ────────────────────────────────────────────────────────

def test_metrics_never_called():
    """已注册但从未调用的工具应出现在 never_called."""
    m = ToolMetrics()
    m.register_tool("unused_tool")
    summ = m.summary()
    assert "unused_tool" in summ["never_called"]


@pytest.mark.asyncio
async def test_metrics_records_cache_hit(clean_registry):
    @clean_registry.register({"name": "m1", "description": "m"})
    async def m1(params):
        return "x"

    clean_registry.register_capability("realtime_quote", "m1", 1)
    call = ToolCall(tool_id="m1", params={"symbol": "T"}, market="美股")
    await clean_registry.execute(call)
    await clean_registry.execute(call)  # cache hit
    summ = clean_registry.metrics_summary()
    pq = summ["per_tool"]["m1"]
    assert pq["call_count"] == 2
    assert pq["cache_hit"] == 1
