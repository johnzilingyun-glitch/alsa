"""Quick integration test for OpenBB service."""
import asyncio
import sys
sys.path.insert(0, "python_service")

async def test():
    from app.services.openbb_service import openbb_service

    print("=== Test 1: Analyst Consensus (MSFT) ===")
    r = await openbb_service.get_analyst_consensus("MSFT")
    print(r[:500] if r else "EMPTY")
    print()

    print("=== Test 2: Key Metrics (MSFT) ===")
    r = await openbb_service.get_key_metrics("MSFT")
    print(r[:500] if r else "EMPTY")
    print()

    print("=== Test 3: SEC Filings (MSFT) ===")
    r = await openbb_service.get_sec_filings("MSFT", limit=3)
    print(r[:500] if r else "EMPTY")
    print()

    print("=== Test 4: Insider Trading (MSFT) ===")
    r = await openbb_service.get_insider_trading("MSFT", limit=5)
    print(r[:500] if r else "EMPTY")
    print()

    print("=== Test 5: Combined query (MSFT) ===")
    r = await openbb_service.query("MSFT", "analyst consensus target price valuation metrics")
    print(r[:800] if r else "EMPTY")
    print()

    print("=== Test 6: A-Share should return empty ===")
    r = await openbb_service.query("002532", "quarterly earnings")
    print(f"Result: '{r}' (expected empty)")
    print()

    print("ALL TESTS DONE")

asyncio.run(test())
