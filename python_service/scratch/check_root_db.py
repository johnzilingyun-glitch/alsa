import sqlite3
import os

db_path = "data/app.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT job_id, symbol, status, created_at FROM analysisjob WHERE symbol='300527' ORDER BY created_at DESC LIMIT 5;")
    rows = cursor.fetchall()
    print("Job ID | Symbol | Status | Created At")
    print("-" * 50)
    for row in rows:
        print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]}")
    conn.close()
else:
    print(f"DB not found at {db_path}")
