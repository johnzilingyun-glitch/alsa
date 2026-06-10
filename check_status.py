import sqlite3
import json

def check():
    try:
        conn = sqlite3.connect('data/alsa.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, symbol, status, current_round, analysis_level, created_at, error_message FROM analysis_jobs ORDER BY created_at DESC LIMIT 1;")
        row = cursor.fetchone()
        if row:
            data = dict(row)
            # Find total_rounds dynamically since we aren't sure if it's in the schema
            cursor.execute("PRAGMA table_info(analysis_jobs);")
            columns = [c['name'] for c in cursor.fetchall()]
            total_rounds = data.get('total_rounds', '?') if 'total_rounds' in columns else '?'
            
            print(f"[{data['symbol']}] Status: {data['status']} | Round: {data['current_round']}/{total_rounds} | Error: {data['error_message']}")
            
            # return status for external use if needed
            with open("job_status.json", "w") as f:
                json.dump(data, f)
        else:
            print("No jobs found in database.")
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

check()
