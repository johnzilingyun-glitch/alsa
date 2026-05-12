import sqlite3
import json

db_path = 'data/alsa.db'
analysis_id = 'ana_1778498694902_j5cbr'
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT config FROM analysis_runs WHERE analysis_id=?", (analysis_id,))
    row = cursor.fetchone()
    if row:
        print(row[0])
    conn.close()
except Exception as e:
    print(f"Error: {e}")
