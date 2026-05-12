import sqlite3
import os

db_path = "python_service/data/app.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT job_id, symbol, status FROM analysisjob ORDER BY created_at DESC LIMIT 20;")
    rows = cursor.fetchall()
    for row in rows:
        print(f"{row[0]} | {row[1]} | {row[2]}")
    conn.close()
