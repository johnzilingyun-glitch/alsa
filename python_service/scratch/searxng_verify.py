import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")

def verify_searxng():
    print("🐍 Starting Python-based SearXNG Verification")
    print(f"📡 Instance URL: {SEARXNG_URL}")
    print("------------------------------------------")

    try:
        start_time = time.time()
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={"q": "financial technology", "format": "json"},
            timeout=10
        )
        latency = (time.time() - start_time) * 1000
        
        if response.status_code == 200:
            data = response.json()
            results_count = len(data.get("results", []))
            print(f"✅ Success! Latency: {latency:.2f}ms")
            print(f"✅ Found {results_count} results")
            
            if results_count > 0:
                first = data["results"][0]
                print(f"  First Result: {first.get('title')}")
                print(f"  Source: {first.get('engines')}")
        else:
            print(f"❌ Failed with status code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

    print("------------------------------------------")
    print("🐍 Python Verification Finished")

if __name__ == "__main__":
    verify_searxng()
