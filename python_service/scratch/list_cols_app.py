import sqlite3
import os

db_path = "python_service/data/app.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(analysisjob);")
    cols = cursor.fetchall()
    print("Columns:", [c[1] for c in cols])
    conn.close()
else:
    print(f"DB not found at {db_path}")
