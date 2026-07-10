"""ContextBuilder 测试 — §4.5 上下文构建.

覆盖: build_core 核心接口 / build 扩展接口 / recall / 市场摘要 / 新闻 Top-N / 预算分级.
"""
import pytest

from app.services.context_builder import ContextBuilder, _extractive_summary
from app.schemas.contracts import Snapshot


@pytest.fixture
def builder():
    return ContextBuilder()


@pytest.fixture
def kline_rows():
    """模拟 K线数据 (compute_indicator_frame 需要 close/high/low/volume/trade_date)."""
    rows = []
    price = 100.0
    for i in range(80):
        price += (i % 7 - 3) * 0.5
        rows.append({
            "trade_date": f"2026-01-{i+1:02d}",
            "open": price - 0.3,
            "close": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "volume": 1000000 + i * 1000,
        })
    return rows


def test_build_core_returns_required_keys(builder, kline_rows):
    """build_core 返回核心字段, 不依赖 evidence/memory."""
    snap = Snapshot(symbol="AAPL", market="美股", history=kline_rows)
    ctx = builder.build_core("分析 AAPL 趋势", snap, budget_tokens=12000)
    assert "question" in ctx
    assert "market_summary" in ctx
    assert ctx["question"] == "分析 AAPL 趋势"


def test_build_core_market_summary(builder, kline_rows):
    """市场摘要应包含 price / MA / 趋势标签."""
    snap = Snapshot(history=kline_rows)
    ctx = builder.build_core("q", snap, budget_tokens=12000)
    ms = ctx["market_summary"]
    assert "price=" in ms
    assert "MA" in ms
    assert "trend=" in ms


def test_build_core_budget_tiers(builder, kline_rows):
    """预算分级: 大预算带 news=5, 小预算 news=3, 无 fundamentals."""
    snap = Snapshot(history=kline_rows, news=[{"title": f"news {i}", "date": "2026-01-01"} for i in range(10)])
    # 大预算
    ctx_large = builder.build_core("q", snap, budget_tokens=12000)
    assert len(ctx_large["news"]) == 5
    assert "fundamentals" in ctx_large
    # 中预算
    ctx_mid = builder.build_core("q", snap, budget_tokens=7000)
    assert len(ctx_mid["news"]) == 3
    assert "fundamentals" in ctx_mid
    # 小预算: 无 fundamentals
    ctx_small = builder.build_core("q", snap, budget_tokens=4000)
    assert "fundamentals" not in ctx_small


def test_build_injects_evidence(builder, kline_rows):
    """build 扩展接口注入 evidence."""
    snap = Snapshot(history=kline_rows)
    evidence = [{"claim": "bullish", "stance": "bullish"}]
    ctx = builder.build("q", snap, evidence=evidence, budget_tokens=12000)
    assert ctx["evidence"] == evidence


def test_recall_roundtrip(builder):
    """recall 按需召回原始数据."""
    snap = Snapshot()
    snap.put("ref_001", "full original text " * 100)
    # 先 build 让 builder 持有 store 引用
    builder.build_core("q", snap, budget_tokens=8000)
    assert builder.recall("ref_001").startswith("full original text")


def test_recall_empty(builder):
    """未设 store 时 recall 返回空."""
    b = ContextBuilder()
    assert b.recall("any") == ""


def test_top_n_news(builder):
    snap = Snapshot(news=[
        {"title": "first", "date": "2026-01-01"},
        {"title": "second", "date": "2026-01-02"},
        {"title": "third", "date": "2026-01-03"},
    ])
    news = builder._top_n_news(snap, n=2)
    assert len(news) == 2
    assert "first" in news[0]


def test_key_tables_compact(builder):
    """财报 KeyTables 取核心字段, 丢弃长文本."""
    snap = Snapshot(financials={
        "revenue": 1234567890.123,
        "net_profit": 500000000,
        "long_text": "x" * 5000,  # 应被忽略
        "income_statement": [{"item": "营收", "value": 100}, {"item": "成本", "value": 60}],
    })
    out = builder._key_tables(snap, budget_tokens=10000)
    assert "revenue" in out
    assert "net_profit" in out
    assert "income_statement" in out or "营收" in out
    assert "x" * 100 not in out  # 长文本未进入


def test_extractive_summary_keeps_signal():
    """抽取式摘要保留表头+数值行, 丢弃填充."""
    text = "header line\nquery: test\n" + ("filler " * 200) + "\n| col1 | col2 |\n| 1 | 2 |"
    s = _extractive_summary(text, max_chars=200)
    assert len(s) <= 200
    assert "header" in s or "query" in s


def test_trend_label():
    assert ContextBuilder._trend_label(110, 105, 100, 95) == "强势多头"
    assert ContextBuilder._trend_label(90, 95, 100, 105) == "弱势空头"
    assert ContextBuilder._trend_label(None, None, None, None) == "unknown"


def test_render_compact(builder, kline_rows):
    """render 输出紧凑 prompt 片段."""
    snap = Snapshot(symbol="AAPL", history=kline_rows, news=[{"title": "n1", "date": "d1"}])
    ctx = builder.build_core("分析", snap, budget_tokens=12000)
    out = builder.render(ctx, max_chars=2000)
    assert "Question" in out
    assert "Market Summary" in out
    assert len(out) <= 2000
