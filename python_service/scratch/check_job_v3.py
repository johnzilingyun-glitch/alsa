import sqlite3
import os

db_path = "python_service/data/app_v3.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT job_id, symbol, status FROM analysisjob WHERE job_id='job_9b768d56';")
    row = cursor.fetchone()
    if row:
        print(f"{row[0]} | {row[1]} | {row[2]}")
    else:
        print("Job not found in app_v3.db")
    conn.close()
