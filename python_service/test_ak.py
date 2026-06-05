#!/usr/bin/env python3
"""Test if AkShare works for fetching A-share stock data."""
import akshare as ak
try:
    df = ak.stock_zh_a_hist(symbol='002532', period='daily', start_date='20250501', adjust='')
    print(f"AkShare OK, rows: {len(df)}")
    print(df.tail(3))
except Exception as e:
    print(f"AkShare error: {e}")
