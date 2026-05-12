import sqlite3
import os

db_path = "data/app.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(watchlistitem);")
    cols = cursor.fetchall()
    print("Columns in watchlistitem:", [c[1] for c in cols])
    conn.close()
else:
    print(f"DB not found at {db_path}")
