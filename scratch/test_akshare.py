import akshare as ak
import pandas as pd
import sys

def test_hk():
    try:
        print("Testing HK Spot (EastMoney)...")
        df = ak.stock_hk_spot_em()
        print(f"HK Columns: {df.columns.tolist()}")
        print(df.head(2))
    except Exception as e:
        print(f"HK Test Failed: {e}")

def test_lhb():
    try:
        print("\nTesting LHB Detail (EastMoney)...")
        df = ak.stock_lhb_detail_em(date="20260417")
        print(f"LHB Columns: {df.columns.tolist()}")
        print(df.head(2))
    except Exception as e:
        print(f"LHB Test Failed: {e}")

def test_margin():
    try:
        print("\nTesting Margin (EastMoney)...")
        df = ak.stock_margin_detail_sz_gao(date="20260417")
        print(f"Margin Columns: {df.columns.tolist()}")
        print(df.head(2))
    except Exception as e:
        print(f"Margin Test Failed: {e}")

def test_announcements():
    try:
        print("\nTesting Announcements (EastMoney)...")
        df = ak.stock_zh_a_announcement_em(symbol="000700") # Just a test sym
        print(f"Announce Columns: {df.columns.tolist()}")
        print(df.head(2))
    except Exception as e:
        print(f"Announce Test Failed: {e}")

if __name__ == "__main__":
    test_hk()
    test_lhb()
    test_margin()
    # test_announcements() # Might be slow
