import sqlite3
import os

db_path = "python_service/data/app_v3.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM analysisjob;")
    symbols = cursor.fetchall()
    print("Symbols in DB:", [s[0] for s in symbols])
    conn.close()
else:
    print(f"DB not found at {db_path}")
