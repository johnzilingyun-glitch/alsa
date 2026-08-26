"""Diagnose data source failures: ths_quote / financial_data / deep_scrape / web_search.

Run: python_service/.venv/bin/python python_service/scratch/diag_data_sources.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def diag_ths():
    print("\n=== [1] ths_quote: thsdk connection ===")
    try:
        import thsdk
        print(f"  thsdk version: {getattr(thsdk, '__version__', 'unknown')}")
        from app.services.data_providers.ths_provider import ths_provider
        t0 = time.perf_counter()
        result = await ths_provider.get_market_data_hk("UHKG01888", "基础数据")
        dt = time.perf_counter() - t0
        data = result.get("data", [])
        if data:
            print(f"  OK: {len(data)} rows in {dt:.1f}s — {str(data[0])[:200]}")
        else:
            print(f"  FAIL: empty result in {dt:.1f}s (THS terminal may not be running)")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

async def diag_yfinance_hk():
    print("\n=== [2] financial_data: yfinance for HK (1888.HK) ===")
    try:
        import yfinance as yf
        t0 = time.perf_counter()
        ticker = yf.Ticker("1888.HK")
        info = await asyncio.to_thread(getattr, ticker, "info")
        dt = time.perf_counter() - t0
        if info and info.get("shortName"):
            print(f"  OK: {info.get('shortName')} price={info.get('currentPrice')} in {dt:.1f}s")
            fin = await asyncio.to_thread(getattr, ticker, "financials")
            if fin is not None and not fin.empty:
                print(f"  financials OK: {list(fin.columns)[:3]}")
            else:
                print("  financials EMPTY")
        else:
            print(f"  FAIL: empty info in {dt:.1f}s")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

async def diag_eastmoney():
    print("\n=== [3] financial_data: EastMoney datacenter (A-share path) ===")
    try:
        from app.services.data_providers.a_stock_direct import fetch_a_share_income_items
        t0 = time.perf_counter()
        items = await fetch_a_share_income_items("600519", periods=4)
        dt = time.perf_counter() - t0
        if items:
            print(f"  OK: {len(items)} periods in {dt:.1f}s — {str(items[0])[:150]}")
        else:
            print(f"  FAIL: empty in {dt:.1f}s")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

async def diag_router():
    print("\n=== [4] financial_data: DataRouter.get_financial_summary ===")
    try:
        from app.services.data_providers import data_router
        t0 = time.perf_counter()
        summary = await data_router.get_financial_summary("600519")
        dt = time.perf_counter() - t0
        if summary and "error" not in summary:
            print(f"  OK in {dt:.1f}s: keys={list(summary.keys())[:12]}")
        else:
            print(f"  FAIL in {dt:.1f}s: {summary}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

async def diag_iwencai():
    print("\n=== [5] web_search: Iwencai (primary for CN) ===")
    key = os.getenv("IWENCAI_API_KEY", "")
    print(f"  IWENCAI_API_KEY set: {bool(key)}")
    if key:
        try:
            from app.services.data_providers.iwencai_news import search_comprehensive
            t0 = time.perf_counter()
            res = await search_comprehensive("建滔积层板 2025年报")
            dt = time.perf_counter() - t0
            print(f"  status={res.get('status_code')} items={len(res.get('data', []))} in {dt:.1f}s")
        except Exception as e:
            print(f"  FAIL: {type(e).__name__}: {e}")
    else:
        print("  SKIP: no API key (web_search will fall through)")

async def diag_searxng():
    print("\n=== [6] web_search: SearXNG relevance check ===")
    try:
        from app.services.search_service import SearchService
        svc = SearchService()
        for q in ["建滔积层板 2025年报 净利润", "铜价 最新报价 LME"]:
            t0 = time.perf_counter()
            results = await svc._searxng_search(q, max_results=5)
            dt = time.perf_counter() - t0
            print(f"  query='{q}' → {len(results)} results in {dt:.1f}s")
            for r in results[:3]:
                print(f"    - [{r['source']}] {r['title'][:70]}")
                print(f"      {r['url'][:90]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

async def diag_full_search():
    print("\n=== [7] web_search: full chain (as agent sees it) ===")
    try:
        from app.services.search_service import search_service
        t0 = time.perf_counter()
        results = await search_service.search("建滔积层板 1888.HK 2025年报 营收 净利润", max_results=5)
        dt = time.perf_counter() - t0
        print(f"  search() → {len(results)} results in {dt:.1f}s")
        for r in results[:5]:
            print(f"    - [{r.get('source')}] {r.get('title','')[:70]}")
            print(f"      {r.get('url','')[:90]}")
            print(f"      {r.get('content','')[:100]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

async def diag_deep_scrape():
    print("\n=== [8] deep_scrape: crawl4ai availability ===")
    try:
        import crawl4ai
        print(f"  OK: crawl4ai {getattr(crawl4ai, '__version__', '?')}")
    except ImportError as e:
        print(f"  FAIL: {e}")

async def main():
    print("Python:", sys.version.split()[0])
    await diag_ths()
    await diag_yfinance_hk()
    await diag_eastmoney()
    await diag_router()
    await diag_iwencai()
    await diag_searxng()
    await diag_full_search()
    await diag_deep_scrape()

if __name__ == "__main__":
    asyncio.run(main())
