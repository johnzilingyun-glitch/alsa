import sqlite3, json

db = sqlite3.connect('python_service/data/alsa.db')
cur = db.cursor()

# List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur.fetchall()])

# Find snapshot-related tables
for table in ['snapshots', 'snapshot', 'market_snapshots', 'analysis_jobs']:
    try:
        cur.execute(f"SELECT count(*) FROM {table}")
        print(f"{table}: {cur.fetchone()[0]} rows")
    except:
        pass

db.close()
