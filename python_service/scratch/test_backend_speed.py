import time
import requests

def test_speed():
    symbol = "600519"
    start = time.time()
    try:
        res = requests.get(f"http://127.0.0.1:8001/api/stock/a_spot?symbol={symbol}", timeout=10)
        print(f"a_spot latency: {time.time() - start:.4f}s")
    except Exception as e:
        print(f"a_spot failed: {e}")

    start = time.time()
    try:
        res = requests.get(f"http://127.0.0.1:8001/api/stock/a_history?symbol={symbol}", timeout=10)
        print(f"a_history latency: {time.time() - start:.4f}s")
    except Exception as e:
        print(f"a_history failed: {e}")

if __name__ == "__main__":
    test_speed()
