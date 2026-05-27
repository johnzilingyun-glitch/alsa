import sqlite3
import json

conn = sqlite3.connect('/home/zily/alsa/data/app.db')
cur = conn.cursor()
cur.execute("SELECT job_id, result_payload FROM analysisjob WHERE result_payload IS NOT NULL ORDER BY created_at DESC LIMIT 10;")
rows = cur.fetchall()
for job_id, payload in rows:
    try:
        data = json.loads(payload)
        discussion = data.get('discussion', [])
        screener = [x for x in discussion if x.get('role') == 'Sector Stock Screener']
        if screener:
            content = screener[0].get('content', '')
            print(f"Job {job_id} has Screener content len: {len(content)}")
            if 0 < len(content) < 500:
                print("Content:", repr(content))
        else:
            print(f"Job {job_id} has NO Screener role")
    except Exception as e:
        print(f"Job {job_id} error: {e}")
