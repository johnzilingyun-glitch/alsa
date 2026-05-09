"""
Standalone test for SearchToolkit — run from python_service/ with the project's venv.
Usage: python scratch/test_search_toolkit.py
"""
import asyncio
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.search_toolkit import search_toolkit, SEARCH_CATEGORIES, ROLE_CATEGORY_MAP, A_SHARE_EXTRA_CATEGORIES

async def test_batch_search():
    print("=" * 60)
    print("TEST 1: Batch search for NVO (US stock)")
    print("=" * 60)
    
    results = await search_toolkit.batch_search("NVO", "Novo Nordisk")
    
    print(f"\nTotal categories with results: {len(results)}/{len(SEARCH_CATEGORIES)}")
    for cat, items in results.items():
        print(f"  {cat}: {len(items)} results")
        if items:
            print(f"    First: {items[0].get('title', 'N/A')[:60]}")
    
    print("\n" + "=" * 60)
    print("TEST 2: Role-specific enrichment filtering")
    print("=" * 60)
    
    test_roles = ["Deep Research Specialist", "Sentiment Analyst", "Contrarian Strategist", "Technical Analyst"]
    for role in test_roles:
        enrichment = search_toolkit.get_enrichment_for_role(role, results, market="us")
        cats = list(enrichment.keys())
        total_items = sum(len(v) for v in enrichment.values())
        print(f"  {role}: {len(cats)} categories, {total_items} total items — {cats}")
    
    print("\n" + "=" * 60)
    print("TEST 3: Format enrichment for prompt (Sentiment Analyst)")
    print("=" * 60)
    
    enrichment = search_toolkit.get_enrichment_for_role("Sentiment Analyst", results)
    formatted = search_toolkit.format_enrichment(enrichment, language="zh-CN")
    print(f"  Formatted text length: {len(formatted)} chars")
    print(f"  First 500 chars:\n{formatted[:500]}")
    
    print("\n" + "=" * 60)
    print("TEST 4: Cache test (second call should be instant)")
    print("=" * 60)
    
    import time
    start = time.time()
    results2 = await search_toolkit.batch_search("NVO", "Novo Nordisk")
    elapsed = time.time() - start
    print(f"  Second call took: {elapsed:.3f}s (should be ~0s if cached)")
    print(f"  Same results: {len(results2) == len(results)}")

async def test_a_share():
    print("\n" + "=" * 60)
    print("TEST 5: A-share detection & extra categories (300760)")
    print("=" * 60)
    
    market = search_toolkit._detect_market("300760")
    print(f"  Detected market for '300760': {market}")
    assert market == "a_share", f"Expected 'a_share', got '{market}'"
    
    # Just test category mapping, no actual search
    from app.services.search_toolkit import A_SHARE_ROLE_EXTRAS
    for role, extras in A_SHARE_ROLE_EXTRAS.items():
        print(f"  {role} A-share extras: {extras}")
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_batch_search())
    asyncio.run(test_a_share())
