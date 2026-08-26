import asyncio
import os
import sys
import httpx
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("TAVILY_API_KEY", "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")
os.environ.setdefault("SERPER_API_KEY", "ce54c5b01ef640bc086f96b4c511aef7fcb56c66")
os.environ.setdefault("JINA_API_KEY", "jina_536c44d451074d0f82a5dcd1967f01banpUgiyNUWAaFEoEaNoIJpxj_OJw_")

from app.services.search_service import search_service

async def test_apis():
    query = "Nvidia AI chips"
    print(f"=== Testing FAOS Search APIs ===")
    
    # 1. Tavily
    print("\n--- 1. Testing Tavily ---")
    try:
        results = await search_service._search_tavily(query, max_results=3)
        print(f"Success! Found {len(results)} results.")
        for r in results[:1]:
            print(f"   [1] {r['title']} - {r['url']}")
    except Exception as e:
        print(f"Tavily Error: {e}")
        if hasattr(e, "response"):
            print(f"Response: {e.response.status_code}")
            try:
                print(e.response.json())
            except:
                print(e.response.text)

    # 2. Serper
    print("\n--- 2. Testing Serper ---")
    try:
        results = await search_service._search_serper(query, max_results=3)
        print(f"Success! Found {len(results)} results.")
        for r in results[:1]:
            print(f"   [1] {r['title']} - {r['url']}")
    except Exception as e:
        print(f"Serper Error: {e}")
        if hasattr(e, "response"):
            print(f"Response: {e.response.status_code}")
            try:
                print(e.response.json())
            except:
                print(e.response.text)

    # 3. Jina
    print("\n--- 3. Testing Jina ---")
    try:
        results = await search_service._search_jina(query, max_results=3)
        print(f"Success! Found {len(results)} results.")
        for r in results[:1]:
            print(f"   [1] {r['title']} - {r['url']}")
    except Exception as e:
        print(f"Jina Error: {e}")
        if hasattr(e, "response"):
            print(f"Response: {e.response.status_code}")
            try:
                print(e.response.json())
            except:
                print(e.response.text)
                
if __name__ == "__main__":
    asyncio.run(test_apis())
