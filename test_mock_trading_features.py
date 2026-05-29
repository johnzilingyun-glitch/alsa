import urllib.request
import json
import time

def api_post(path, data):
    url = f"http://127.0.0.1:8001/api{path}"
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        print(e.read().decode("utf-8"))
        return None

def api_get(path):
    url = f"http://127.0.0.1:8001/api{path}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        print(e.read().decode("utf-8"))
        return None

# 1. Create Account with Custom Balance
print("Creating global account...")
acc_data = api_post("/mock-trading/accounts", {"name": "Test Global", "market": "Global", "initial_balance": 500000})
print(acc_data)
acc_id = acc_data["data"]["account_id"]

# 2. Manual Trade (AAPL in US-Share, bought with CNY)
print("Trading AAPL...")
trade = api_post("/mock-trading/trades", {
    "account_id": acc_id,
    "symbol": "AAPL",
    "market": "US-Share",
    "action": "BUY",
    "shares": 100,
    "execution_price": 200.0,
    "trigger_source": "MANUAL"
})
print(trade)

# 3. Portfolio PnL update (Mocking live price)
print("Fetching portfolio with simulated live prices...")
pf = api_post(f"/mock-trading/portfolio/{acc_id}", {"AAPL": 210.0})
print(pf)

# 4. Create another account and merge
acc2 = api_post("/mock-trading/accounts", {"name": "Test US", "market": "US-Share", "initial_balance": 10000})
acc2_id = acc2["data"]["account_id"]

print("Merging...")
merge_res = api_post("/mock-trading/accounts/merge", {
    "source_account_ids": [acc2_id],
    "target_account_id": acc_id
})
print(merge_res)

# 5. Check final portfolio
pf_final = api_post(f"/mock-trading/portfolio/{acc_id}", {"AAPL": 210.0})
print(pf_final)
