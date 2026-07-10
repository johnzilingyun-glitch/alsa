"""Standalone test runner for Phase 1 modules.

绕过项目 conftest (其 import python_service.app 触发原生模块崩溃),
直接加载 Phase 1 模块并运行断言. 用于在本环境验证逻辑正确性.
生产环境 thsdk 齐全时, 同样的测试经 pytest + conftest 也可运行.
"""
import sys, types, importlib.util, asyncio, traceback

ROOT = "python_service"
sys.path.insert(0, ROOT)

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# 建干净的 tools 包占位 (不执行原 __init__ 的子模块导入, 避免重型依赖)
pkg = types.ModuleType("app.services.tools")
pkg.__path__ = [f"{ROOT}/app/services/tools"]
sys.modules["app.services.tools"] = pkg

# 加载 Phase 1 模块
from app.schemas import contracts  # noqa: 正常包导入, 无重型依赖
_load("app.services.tools.shared_cache", f"{ROOT}/app/services/tools/shared_cache.py")
_load("app.services.tools.preconditions", f"{ROOT}/app/services/tools/preconditions.py")
_load("app.services.tools.metrics", f"{ROOT}/app/services/tools/metrics.py")
rg = _load("app.services.tools.registry", f"{ROOT}/app/services/tools/registry.py")
_load("app.services.context_builder", f"{ROOT}/app/services/context_builder.py")

from app.services.tools.registry import ToolRegistry, tool_registry
from app.services.tools.shared_cache import SharedToolCache, make_cache_key
from app.services.tools.preconditions import validate_precondition, is_valid_result
from app.services.tools.metrics import ToolMetrics
from app.services.context_builder import ContextBuilder, _extractive_summary
from app.schemas.contracts import ToolCall, Snapshot

passed = 0
failed = 0

def check(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  PASS  {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        traceback.print_exc()
        failed += 1

def check_async(name, coro_fn):
    global passed, failed
    try:
        asyncio.run(coro_fn())
        print(f"  PASS  {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        failed += 1

# ── 向后兼容 ────────────────────────────────────────────────────────────────
def t_backward_compat():
    tr = ToolRegistry()
    schema = {"name": "test_search", "description": "x"}
    @tr.register(schema)
    async def f(params): return "ok"
    assert "test_search" in tr.get_registered_names()
    assert tr.get_all_schemas()[0] == schema
    assert not tr.is_computation_tool("test_search")

def t_computation():
    tr = ToolRegistry()
    @tr.register({"name": "c", "description": "c"}, is_computation=True)
    def c(params): return "x"
    assert tr.is_computation_tool("c")

# ── 能力矩阵 ────────────────────────────────────────────────────────────────
def t_resolve():
    r = tool_registry.resolve("news")
    assert r[0]["tool_id"] == "news_search"
    assert r[1]["tool_id"] == "web_search"
    assert r[0]["priority"] < r[1]["priority"]

def t_register_capability():
    tr = ToolRegistry()
    tr.register_capability("realtime_quote", "mq", 1)
    tr.register_capability("realtime_quote", "mq", 2)
    assert "mq" in [t["tool_id"] for t in tr.resolve("realtime_quote")]

# ── 前置校验 ────────────────────────────────────────────────────────────────
def t_precond_market_block():
    ok, reason = validate_precondition("financial_data", {"symbol": "0700.HK"}, "HK-Share")
    assert not ok
    assert "港股" in reason or "HK" in reason

def t_precond_market_allow():
    assert validate_precondition("financial_data", {"symbol": "600519.SH"}, "A股")[0]
    assert validate_precondition("financial_data", {"symbol": "AAPL"}, "美股")[0]

def t_precond_missing_param():
    ok, reason = validate_precondition("macro_query", {}, "美股")
    assert not ok and "symbol" in reason

def t_precond_requires_any():
    assert validate_precondition("finance_query", {"query": "营收"}, "A股")[0]
    assert not validate_precondition("finance_query", {}, "A股")[0]

def t_precond_approval():
    assert not validate_precondition("deep_scrape", {"url": "http://x"}, "", approval_granted=False)[0]
    assert validate_precondition("deep_scrape", {"url": "http://x"}, "", approval_granted=True)[0]

def t_precond_passthrough():
    assert validate_precondition("unknown_tool", {"x": 1}, "A股")[0]

# ── 结果有效性 ──────────────────────────────────────────────────────────────
def t_is_valid():
    assert is_valid_result("data")
    assert not is_valid_result("")
    assert not is_valid_result("error")
    assert not is_valid_result("Error: x")
    assert not is_valid_result([])
    assert not is_valid_result({})
    assert is_valid_result([1])
    assert not is_valid_result(None)

# ── 共享缓存 ────────────────────────────────────────────────────────────────
def t_cache_hit():
    c = SharedToolCache()
    k = make_cache_key("news_search", {"symbol": "AAPL", "query": "e"})
    assert c.get(k) is None
    c.set(k, "result", data_type="news")
    assert c.get(k) == "result"

def t_cache_key_norm():
    k1 = make_cache_key("t", {"a": "x y", "b": "z"})
    k2 = make_cache_key("t", {"b": "z", "a": "X  Y"})
    assert k1 == k2

def t_cache_invalidate_prefix():
    c = SharedToolCache()
    c.set("t|a=1", "r1", data_type="news")
    c.set("t|a=2", "r2", data_type="news")
    c.set("o|a=1", "r3", data_type="news")
    assert c.invalidate_prefix("t") == 2
    assert c.get("t|a=1") is None
    assert c.get("o|a=1") == "r3"

def t_cache_ttl():
    import time
    c = SharedToolCache()
    c.set("k", "v", ttl=0)
    time.sleep(0.01)
    assert c.get("k") is None

# ── execute ─────────────────────────────────────────────────────────────────
async def t_execute_cache():
    tr = ToolRegistry()
    @tr.register({"name": "q", "description": "q"})
    async def q(params): return "data:" + params.get("symbol", "")
    tr.register_capability("realtime_quote", "q", 1)
    call = ToolCall(tool_id="q", params={"symbol": "AAPL"}, market="美股")
    r1 = await tr.execute(call)
    assert r1.status == "ok" and not r1.from_cache
    r2 = await tr.execute(call)
    assert r2.status == "cached" and r2.from_cache and r2.data == r1.data

async def t_execute_invalid():
    tr = ToolRegistry()
    @tr.register({"name": "financial_data", "description": "f"})
    async def f(params): return "should not be called"
    tr.register_capability("financial_stmt", "financial_data", 1)
    call = ToolCall(tool_id="financial_data", params={"symbol": "0700.HK"}, market="HK-Share")
    r = await tr.execute(call)
    assert r.status == "invalid"

async def t_execute_fallback():
    tr = ToolRegistry()
    @tr.register({"name": "primary", "description": "p"})
    async def primary(params): return ""  # invalid
    @tr.register({"name": "backup", "description": "b"})
    async def backup(params): return "backup data"
    tr.register_capability("realtime_quote", "primary", 1)
    tr.register_capability("realtime_quote", "backup", 2)
    call = ToolCall(tool_id="primary", params={"symbol": "AAPL"}, market="美股")
    r = await tr.execute(call)
    assert r.status == "degraded" and r.tool_id == "backup" and r.data == "backup data"

# ── metrics ─────────────────────────────────────────────────────────────────
def t_metrics_never():
    m = ToolMetrics()
    m.register_tool("unused")
    assert "unused" in m.summary()["never_called"]

async def t_metrics_cache_hit():
    tr = ToolRegistry()
    @tr.register({"name": "m1", "description": "m"})
    async def m1(params): return "x"
    tr.register_capability("realtime_quote", "m1", 1)
    call = ToolCall(tool_id="m1", params={"symbol": "T"}, market="美股")
    await tr.execute(call)
    await tr.execute(call)
    pq = tr.metrics_summary()["per_tool"]["m1"]
    assert pq["call_count"] == 2 and pq["cache_hit"] == 1

# ── ContextBuilder ──────────────────────────────────────────────────────────
def _klines():
    rows = []
    p = 100.0
    for i in range(80):
        p += (i % 7 - 3) * 0.5
        rows.append({"trade_date": f"2026-01-{i+1:02d}", "open": p-0.3, "close": p,
                     "high": p+0.5, "low": p-0.5, "volume": 1000000+i*1000})
    return rows

def t_cb_core():
    b = ContextBuilder()
    snap = Snapshot(symbol="AAPL", market="美股", history=_klines())
    ctx = b.build_core("分析趋势", snap, budget_tokens=12000)
    assert "question" in ctx and "market_summary" in ctx
    assert "price=" in ctx["market_summary"] and "MA" in ctx["market_summary"]

def t_cb_budget_tiers():
    b = ContextBuilder()
    snap = Snapshot(history=_klines(), news=[{"title": f"n{i}", "date":"d"} for i in range(10)])
    cl = b.build_core("q", snap, budget_tokens=12000)
    assert len(cl["news"]) == 5 and "fundamentals" in cl
    cs = b.build_core("q", snap, budget_tokens=4000)
    assert "fundamentals" not in cs

def t_cb_recall():
    b = ContextBuilder()
    snap = Snapshot()
    snap.put("ref1", "full " * 100)
    b.build_core("q", snap, budget_tokens=8000)
    assert b.recall("ref1").startswith("full")

def t_cb_trend():
    assert ContextBuilder._trend_label(110, 105, 100, 95) == "强势多头"
    assert ContextBuilder._trend_label(90, 95, 100, 105) == "弱势空头"

def t_cb_render():
    b = ContextBuilder()
    snap = Snapshot(symbol="AAPL", history=_klines(), news=[{"title":"n1","date":"d1"}])
    ctx = b.build_core("分析", snap, budget_tokens=12000)
    out = b.render(ctx, max_chars=2000)
    assert "Question" in out and "Market Summary" in out and len(out) <= 2000

def t_cb_key_tables():
    b = ContextBuilder()
    snap = Snapshot(financials={"revenue": 1234.5, "long_text": "x"*5000,
                                "tbl": [{"a":1},{"a":2}]})
    out = b._key_tables(snap, 10000)
    assert "revenue" in out and "x"*100 not in out

if __name__ == "__main__":
    print("=== Phase 1 测试 (standalone, 绕过 conftest 重型导入) ===")
    for name, fn in [
        ("backward_compat", t_backward_compat), ("computation", t_computation),
        ("resolve", t_resolve), ("register_capability", t_register_capability),
        ("precond_market_block", t_precond_market_block), ("precond_market_allow", t_precond_market_allow),
        ("precond_missing_param", t_precond_missing_param), ("precond_requires_any", t_precond_requires_any),
        ("precond_approval", t_precond_approval), ("precond_passthrough", t_precond_passthrough),
        ("is_valid", t_is_valid),
        ("cache_hit", t_cache_hit), ("cache_key_norm", t_cache_key_norm),
        ("cache_invalidate_prefix", t_cache_invalidate_prefix), ("cache_ttl", t_cache_ttl),
        ("metrics_never", t_metrics_never),
        ("cb_core", t_cb_core), ("cb_budget_tiers", t_cb_budget_tiers),
        ("cb_recall", t_cb_recall), ("cb_trend", t_cb_trend),
        ("cb_render", t_cb_render), ("cb_key_tables", t_cb_key_tables),
    ]:
        check(name, fn)
    for name, fn in [
        ("execute_cache", t_execute_cache), ("execute_invalid", t_execute_invalid),
        ("execute_fallback", t_execute_fallback), ("metrics_cache_hit", t_metrics_cache_hit),
    ]:
        check_async(name, fn)
    print(f"\n=== 结果: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed else 0)
