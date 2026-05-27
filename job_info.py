import sqlite3
import json

conn = sqlite3.connect('/home/zily/alsa/data/app.db')
cur = conn.cursor()
cur.execute("SELECT requested_model, result_payload FROM analysisjob WHERE job_id='sector_b5373001'")
row = cur.fetchone()
if row:
    print(f"Model: {row[0]}")
    payload = json.loads(row[1])
    screener = [x for x in payload.get('discussion', []) if x.get('role') == 'Sector Stock Screener']
    if screener:
        print("Screener Content:", repr(screener[0].get('content', '')))
else:
    print("Not found")
