import sqlite3
import json
import traceback

try:
    conn = sqlite3.connect('/home/zily/alsa/data/app.db')
    cur = conn.cursor()
    cur.execute("SELECT job_id, status FROM analysisjob WHERE symbol='有色金属' AND market='sector' AND status='completed'")
    print("有色金属 jobs:", cur.fetchall())
except Exception as e:
    traceback.print_exc()
