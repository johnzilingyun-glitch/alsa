import sqlite3

conn = sqlite3.connect('d:/zily/alsa/alsa/data/app.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", cur.fetchall())

try:
    cur.execute("SELECT job_id, symbol, status FROM analysisjob ORDER BY created_at DESC LIMIT 5")
    print("Jobs:", cur.fetchall())
except Exception as e:
    print("Error querying analysisjob:", e)
