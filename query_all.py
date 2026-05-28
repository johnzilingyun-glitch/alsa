import sqlite3
import traceback

try:
    conn = sqlite3.connect('/home/zily/alsa/data/app.db')
    cur = conn.cursor()
    cur.execute("SELECT job_id, symbol, market, status, snapshot_id, created_at FROM analysisjob WHERE market='sector'")
    rows = cur.fetchall()
    for row in rows:
        print(row)
except Exception as e:
    traceback.print_exc()
