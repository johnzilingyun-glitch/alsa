import sqlite3, json, os

conn = sqlite3.connect('data/app.db')
cur = conn.cursor()

# List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur.fetchall()])

# Try prompt table variations
for tbl in ['prompttemplate', 'prompt_template', 'prompts', 'prompt']:
    try:
        cur.execute(f"SELECT * FROM {tbl} LIMIT 1")
        print(f"Found table: {tbl}, cols: {[d[0] for d in cur.description]}")
    except:
        pass

# Also check if result_payload is stored in analysisjob for the most recent sector job
cur.execute("SELECT job_id, symbol, result_payload FROM analysisjob WHERE symbol LIKE '%板块%' OR symbol LIKE '%行业%' OR symbol LIKE '%芯片%' OR symbol LIKE '%铝%' OR symbol LIKE '%券商%' OR symbol LIKE '%金融%' ORDER BY created_at DESC LIMIT 1")
jobs = cur.fetchall()
if jobs:
    j = jobs[0]
    print(f"\n=== Latest sector job: {j[0]} / {j[1]} ===")
    if j[2]:
        payload = json.loads(j[2])
        discussion = payload.get("discussion", [])
        print(f"Discussion messages: {len(discussion)}")
        for msg in discussion:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            print(f"\n--- [{role}] (len={len(content)}) ---")
            print(content[:600])
            print("...")

conn.close()
