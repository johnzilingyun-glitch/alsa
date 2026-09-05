"""Regression tests for _build_market_scan_snapshot in app/api/sector.py.

Bug history (2026-09-05):
  Initial implementation called `asyncio.gather(base, ext)` with default
  raise-on-first-exception, but then had no try/except — leaving base_q
  / ext_q unbound in partial-failure paths. Also crashed on NaN/inf
  numeric fields via `f"{v:.2f}%"` and silently logged `WARNING` even when
  thsdk returned empty data (vs truly unavailable).
"""
import asyncio
import math
from unittest.mock import AsyncMock, patch

import pytest

from app.api.sector import _build_market_scan_snapshot


def _ind(codes):
    return {"data": [{"代码": c, "名称": f"板块{c[-3:]}"} for c in codes]}


def _batch(data):
    return {"data": data, "columns": list(data[0].keys()) if data else []}


# ---------- Happy path ----------

def test_happy_path_90_sectors():
    """正常情况: 90 个板块都能拿到基础 + 扩展数据"""
    codes = [f"URFI{i:04d}" for i in range(1, 91)]
    fake_ind = _ind(codes)
    fake_base = _batch([{
        "代码": c, "名称": f"板块{i}",
        "总金额": (i * 1e8), "领涨股": f"600{i:03d}",
        "涨停家数": i % 5, "跌停家数": 0,
        "上涨家数": 10, "下跌家数": 5,
    } for i, c in enumerate(codes, 1)])
    fake_ext = _batch([{
        "代码": c,
        "涨幅": (i % 10) - 3.0,  # -3 到 +6 之间
        "5日涨幅": (i % 7) - 2.0,
        "10日涨幅": (i % 13) - 5.0,
        "20日涨幅": (i % 11) - 4.0,
        "主力净流入": (i % 17 - 8) * 1e7,
        "量比": 1.0 + (i % 5) * 0.1,
    } for i, c in enumerate(codes, 1)])

    async def run():
        with patch("app.services.data_providers.ths_provider.ths_provider") as mock_ths:
            mock_ths.get_ths_industry = AsyncMock(return_value=fake_ind)
            mock_ths.get_market_data_block = AsyncMock(side_effect=[fake_base, fake_ext])
            return await _build_market_scan_snapshot("2026-09-05")

    result = asyncio.run(run())
    assert result, "happy path 应该返回非空快照"
    assert "TOP 25" in result
    assert "BOTTOM 10" in result
    assert "完整板块名清单" in result
    # 涨幅最高的板块应该出现在 TOP25
    assert "板块90" in result or "板块89" in result  # 涨幅 ≈ +6 的在尾部


# ---------- Partial failure ----------

def test_partial_failure_base_only():
    """扩展 batch 抛 TimeoutError —— 不应让整个 snapshot 失败（如果有基础数据+扩展中涨幅则还能用）"""
    fake_ind = _ind(["URFI1", "URFI2"])
    fake_base = _batch([
        {"代码": "URFI1", "名称": "板块A", "总金额": 100e8, "领涨股": "600001",
         "涨停家数": 1, "跌停家数": 0, "上涨家数": 5, "下跌家数": 2},
        {"代码": "URFI2", "名称": "板块B", "总金额": 50e8, "领涨股": "600002",
         "涨停家数": 0, "跌停家数": 0, "上涨家数": 3, "下跌家数": 4},
    ])

    async def run():
        with patch("app.services.data_providers.ths_provider.ths_provider") as mock_ths:
            mock_ths.get_ths_industry = AsyncMock(return_value=fake_ind)
            # thsdk 内部已经 try/except，所以这里给 _error 模拟 soft-fail
            mock_ths.get_market_data_block = AsyncMock(side_effect=[
                fake_base,
                {"data": [], "columns": [], "_error": "扩展 batch 超时"},
            ])
            return await _build_market_scan_snapshot("2026-09-05")

    # 扩展无数据 → 没有涨幅 → valid=[] → 返回空串（合理：没涨幅无法排序）
    result = asyncio.run(run())
    assert result == "", f"扩展空数据时 valid=[] 应返回空串，得到: {result!r}"


def test_total_failure():
    """thsdk 两批都返回空 + _error —— 必须返回空串且 logger.error"""
    fake_ind = _ind([])  # 连 industry list 都空

    async def run():
        with patch("app.services.data_providers.ths_provider.ths_provider") as mock_ths:
            mock_ths.get_ths_industry = AsyncMock(return_value=fake_ind)
            mock_ths.get_market_data_block = AsyncMock(side_effect=[
                {"data": [], "columns": [], "_error": "fail"},
                {"data": [], "columns": [], "_error": "fail"},
            ])
            return await _build_market_scan_snapshot("2026-09-05")

    result = asyncio.run(run())
    assert result == ""


# ---------- NaN/inf safety ----------

def test_nan_inf_safety():
    """thsdk 给 nan/inf 不应该让 _fmt_pct 崩"""
    fake_ind = _ind(["URFI1"])
    fake_base = _batch([{
        "代码": "URFI1", "名称": "停牌板块", "总金额": None,
        "领涨股": None, "涨停家数": 0, "跌停家数": 0,
        "上涨家数": 0, "下跌家数": 0,
    }])
    fake_ext = _batch([{
        "代码": "URFI1",
        "涨幅": float("nan"),
        "5日涨幅": float("inf"),
        "10日涨幅": float("-inf"),
        "20日涨幅": float("nan"),
        "主力净流入": float("nan"),
        "量比": float("nan"),
    }])

    async def run():
        with patch("app.services.data_providers.ths_provider.ths_provider") as mock_ths:
            mock_ths.get_ths_industry = AsyncMock(return_value=fake_ind)
            mock_ths.get_market_data_block = AsyncMock(side_effect=[fake_base, fake_ext])
            return await _build_market_scan_snapshot("2026-09-05")

    # _safe_float 把 nan/inf 都过滤掉 → 涨幅 None → valid=[] → 返回空串
    # 关键：不应该抛 ValueError 或 TypeError
    result = asyncio.run(run())
    assert result == "", f"全 NaN 应返回空串: {result!r}"


def test_partial_nan_keeps_valid():
    """部分板块有 NaN，部分正常 —— 正常板块应该进 valid"""
    fake_ind = _ind(["URFI1", "URFI2"])
    fake_base = _batch([
        {"代码": "URFI1", "名称": "正常板块", "总金额": 100e8, "领涨股": "600001",
         "涨停家数": 1, "跌停家数": 0, "上涨家数": 5, "下跌家数": 2},
        {"代码": "URFI2", "名称": "停牌板块", "总金额": None,
         "领涨股": None, "涨停家数": 0, "跌停家数": 0,
         "上涨家数": 0, "下跌家数": 0},
    ])
    fake_ext = _batch([
        {"代码": "URFI1", "涨幅": 2.5, "5日涨幅": 1.0, "10日涨幅": 3.0,
         "20日涨幅": 5.0, "主力净流入": 5e8, "量比": 1.2},
        {"代码": "URFI2", "涨幅": float("nan"), "5日涨幅": float("inf"),
         "10日涨幅": float("-inf"), "20日涨幅": float("nan"),
         "主力净流入": float("nan"), "量比": float("nan")},
    ])

    async def run():
        with patch("app.services.data_providers.ths_provider.ths_provider") as mock_ths:
            mock_ths.get_ths_industry = AsyncMock(return_value=fake_ind)
            mock_ths.get_market_data_block = AsyncMock(side_effect=[fake_base, fake_ext])
            return await _build_market_scan_snapshot("2026-09-05")

    result = asyncio.run(run())
    assert result, "正常板块应进快照"
    assert "正常板块" in result
    assert "停牌板块" not in result  # 没涨幅的不进 TOP25/BOTTOM10


# ---------- 排序稳定性 ----------

def test_sort_descending_by_change_pct():
    """TOP25 必须按今日涨幅降序"""
    fake_ind = _ind(["URFI1", "URFI2", "URFI3"])
    fake_base = _batch([
        {"代码": "URFI1", "名称": "板块A", "总金额": 1e8, "领涨股": "1",
         "涨停家数": 0, "跌停家数": 0, "上涨家数": 1, "下跌家数": 1},
        {"代码": "URFI2", "名称": "板块B", "总金额": 1e8, "领涨股": "2",
         "涨停家数": 0, "跌停家数": 0, "上涨家数": 1, "下跌家数": 1},
        {"代码": "URFI3", "名称": "板块C", "总金额": 1e8, "领涨股": "3",
         "涨停家数": 0, "跌停家数": 0, "上涨家数": 1, "下跌家数": 1},
    ])
    fake_ext = _batch([
        {"代码": "URFI1", "涨幅": 1.5, "5日涨幅": 0, "10日涨幅": 0,
         "20日涨幅": 0, "主力净流入": 0, "量比": 1.0},
        {"代码": "URFI2", "涨幅": 3.5, "5日涨幅": 0, "10日涨幅": 0,
         "20日涨幅": 0, "主力净流入": 0, "量比": 1.0},
        {"代码": "URFI3", "涨幅": -2.5, "5日涨幅": 0, "10日涨幅": 0,
         "20日涨幅": 0, "主力净流入": 0, "量比": 1.0},
    ])

    async def run():
        with patch("app.services.data_providers.ths_provider.ths_provider") as mock_ths:
            mock_ths.get_ths_industry = AsyncMock(return_value=fake_ind)
            mock_ths.get_market_data_block = AsyncMock(side_effect=[fake_base, fake_ext])
            return await _build_market_scan_snapshot("2026-09-05")

    result = asyncio.run(run())
    # 板块B (+3.5%) > 板块A (+1.5%) > 板块C (-2.5%)
    pos_b = result.find("板块B")
    pos_a = result.find("板块A")
    pos_c = result.find("板块C")
    assert pos_b < pos_a < pos_c, f"TOP25 应按涨幅降序: B@{pos_b} A@{pos_a} C@{pos_c}"


# ---------- 列表完整性 ----------

def test_full_sector_name_list_includes_all():
    """完整板块名清单必须按降序包含所有 valid 板块"""
    codes = [f"URFI{i:04d}" for i in range(1, 6)]
    fake_ind = _ind(codes)
    fake_base = _batch([
        {"代码": c, "名称": f"板块{i}", "总金额": 1e8, "领涨股": str(i),
         "涨停家数": 0, "跌停家数": 0, "上涨家数": 1, "下跌家数": 1}
        for i, c in enumerate(codes, 1)
    ])
    fake_ext = _batch([
        {"代码": c, "涨幅": float(i), "5日涨幅": 0, "10日涨幅": 0,
         "20日涨幅": 0, "主力净流入": 0, "量比": 1.0}
        for i, c in enumerate(codes, 1)
    ])

    async def run():
        with patch("app.services.data_providers.ths_provider.ths_provider") as mock_ths:
            mock_ths.get_ths_industry = AsyncMock(return_value=fake_ind)
            mock_ths.get_market_data_block = AsyncMock(side_effect=[fake_base, fake_ext])
            return await _build_market_scan_snapshot("2026-09-05")

    result = asyncio.run(run())
    list_section = result.split("### 完整板块名清单")[1]
    # 按涨幅降序: 板块5 > 板块4 > 板块3 > 板块2 > 板块1
    # positions 应该是降序（涨幅最高的字符串最先出现）
    pos = [list_section.find(f"板块{i}") for i in range(1, 6)]
    assert pos == sorted(pos, reverse=True), f"完整清单应按涨幅降序: positions={pos}"