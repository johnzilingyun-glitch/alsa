#!/usr/bin/env python3
"""诊断脚本：逐步排查回测数据为何缺失"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone, timedelta
import pandas as pd

print("=" * 60)
print("Step 1: 检查 vn.py 配置和数据库路径")
print("=" * 60)

try:
    from vnpy.trader.setting import SETTINGS
    print(f"  vn.py database driver: {SETTINGS.get('database.driver', 'N/A')}")
    print(f"  vn.py database name: {SETTINGS.get('database.database', 'N/A')}")
    print(f"  vn.py database host: {SETTINGS.get('database.host', 'N/A')}")
except Exception as e:
    print(f"  ERROR loading vn.py settings: {e}")

# Check the .vntrader directory
vntrader_dir = os.path.expanduser("~/.vntrader")
print(f"\n  ~/.vntrader 目录存在: {os.path.exists(vntrader_dir)}")
if os.path.exists(vntrader_dir):
    for f in os.listdir(vntrader_dir):
        fp = os.path.join(vntrader_dir, f)
        size = os.path.getsize(fp) if os.path.isfile(fp) else "DIR"
        print(f"    {f}: {size}")

print("\n" + "=" * 60)
print("Step 2: 检查 vn.py 数据库中已有的数据")
print("=" * 60)

try:
    from vnpy.trader.database import get_database
    db = get_database()
    overviews = db.get_bar_overview()
    if overviews:
        print(f"  数据库中有 {len(overviews)} 个数据系列:")
        for ov in overviews:
            print(f"    {ov.symbol}.{ov.exchange.value} | {ov.interval.value} | {ov.start} ~ {ov.end} | {ov.count} bars")
    else:
        print("  数据库为空！没有任何K线数据。")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("Step 3: 测试 yfinance 下载能力")
print("=" * 60)

import yfinance as yf

test_symbols = ["600519.SS", "000858.SZ", "AAPL"]
for sym in test_symbols:
    try:
        df = yf.download(sym, start="2024-01-01", end="2024-01-31", progress=False)
        if df.empty:
            print(f"  {sym}: 下载结果为空！")
        else:
            print(f"  {sym}: 成功下载 {len(df)} 根K线, 列名={list(df.columns)[:5]}")
            if isinstance(df.columns, pd.MultiIndex):
                print(f"    MultiIndex levels: {df.columns.names}, first col: {df.columns[0]}")
    except Exception as e:
        print(f"  {sym}: 下载失败 - {e}")

print("\n" + "=" * 60)
print("Step 4: 测试 data_sync_service 全流程")
print("=" * 60)

import asyncio
from vnpy.trader.constant import Exchange, Interval

try:
    from python_service.app.services.data_sync_service import data_sync_service
    
    test_symbol = "600519"
    test_exchange = Exchange.SSE
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    
    print(f"  测试: ensure_local_data({test_symbol}, {test_exchange}, {start.date()}, {end.date()})")
    
    result = asyncio.run(data_sync_service.ensure_local_data(test_symbol, test_exchange, start, end))
    print(f"  结果: {result}")
    
    # Now check if data actually exists in the database
    overviews2 = data_sync_service.database.get_bar_overview()
    match = next((o for o in overviews2 if o.symbol == test_symbol and o.exchange == test_exchange), None)
    if match:
        print(f"  数据库确认: {match.symbol}.{match.exchange.value} | {match.start} ~ {match.end} | {match.count} bars")
    else:
        print(f"  数据库中仍然没有 {test_symbol}.{test_exchange.value} 的数据！")
        
except Exception as e:
    import traceback
    print(f"  ERROR: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("Step 5: 测试 vn.py load_bar_data (和 BacktestingEngine 一样的方式)")
print("=" * 60)

try:
    from vnpy.trader.database import get_database
    db = get_database()
    
    # Try loading bars the same way vn.py backtesting engine does
    from vnpy.trader.datafeed import get_datafeed
    from vnpy_ctastrategy.backtesting import BacktestingEngine
    
    # Check if load_bar_data function works
    from vnpy.trader.utility import load_bar_data
    
    bars = load_bar_data(
        symbol="600519",
        exchange=Exchange.SSE,
        interval=Interval.DAILY,
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 6, 30, tzinfo=timezone.utc)
    )
    print(f"  load_bar_data 返回 {len(bars)} 根K线")
    if bars:
        print(f"    首根: {bars[0].datetime} | O={bars[0].open_price} H={bars[0].high_price} L={bars[0].low_price} C={bars[0].close_price}")
        print(f"    末根: {bars[-1].datetime} | O={bars[-1].open_price} H={bars[-1].high_price} L={bars[-1].low_price} C={bars[-1].close_price}")
    else:
        print("  没有加载到任何K线！")
        
        # Double-check by directly querying the database
        print("\n  尝试直接从数据库查询...")
        bars_direct = db.load_bar_data(
            symbol="600519",
            exchange=Exchange.SSE,
            interval=Interval.DAILY,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 6, 30, tzinfo=timezone.utc)
        )
        print(f"  db.load_bar_data 直接查询返回 {len(bars_direct)} 根K线")
        if bars_direct:
            print(f"    首根: {bars_direct[0].datetime}")
            
except Exception as e:
    import traceback
    print(f"  ERROR: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
