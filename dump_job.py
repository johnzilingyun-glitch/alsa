import sqlite3
import json
import sys

conn = sqlite3.connect('/home/zily/alsa/data/app.db')
cur = conn.cursor()
cur.execute("SELECT result_payload FROM analysisjob WHERE result_payload IS NOT NULL ORDER BY created_at DESC LIMIT 1;")
row = cur.fetchone()
if row and row[0]:
    with open('/home/zily/alsa/recent_job.json', 'w', encoding='utf-8') as f:
        f.write(row[0])
    print('Saved to recent_job.json')
else:
    print('No data found')
