from ddgs import DDGS
import json
import time
import sys

# Ensure UTF-8 output if possible, but emojis are safer removed for GBK terminals
def test_ddgs():
    print("[DDGS TEST] Starting DuckDuckGo Search (DDGS) Test")
    print("------------------------------------------")
    
    queries = [
        "Tencent stock price analysis 2026",
        "Nvidia H200 chip release news",
        "S&P 500 forecast Q3 2026"
    ]
    
    with DDGS() as ddgs:
        for query in queries:
            print(f"\n[SEARCH] Query: {query}")
            try:
                start_time = time.time()
                # max_results=20 as requested by user
                results = list(ddgs.text(query, max_results=20))
                latency = (time.time() - start_time) * 1000
                
                print(f"[SUCCESS] Latency: {latency:.2f}ms")
                print(f"[DATA] Results found: {len(results)}")
                
                if results:
                    for i, r in enumerate(results[:3]):
                        title = r.get('title', 'No Title').encode('gbk', 'ignore').decode('gbk')
                        print(f"  {i+1}. {title[:60]}... ({r.get('href')})")
                else:
                    print("  [WARNING] No results found.")
                    
            except Exception as e:
                print(f"[ERROR] {str(e)}")
                
    print("\n------------------------------------------")
    print("[DDGS TEST] DDGS Testing Finished")

if __name__ == "__main__":
    test_ddgs()
