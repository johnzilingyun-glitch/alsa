import sqlite3, json, os

db_path = os.path.join('data', 'app.db')
print(f'DB exists: {os.path.exists(db_path)}')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check all recent analysis runs
cur.execute("SELECT analysis_id, symbol, market, created_at FROM analysisrun ORDER BY created_at DESC LIMIT 15")
rows = cur.fetchall()
print(f'\nRecent runs: {len(rows)}')
for r in rows:
    print(r)

# Check discussion log artifacts
cur.execute("SELECT a.artifact_id, a.analysis_id, a.artifact_type, a.storage_path FROM analysisartifact a WHERE a.artifact_type = 'discussion_log' ORDER BY a.created_at DESC LIMIT 5")
arts = cur.fetchall()
print(f'\nDiscussion log artifacts: {len(arts)}')
for a in arts:
    print(a)
    # Try reading the file
    if os.path.exists(a[3]):
        with open(a[3], 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for msg in data[:4]:
                    role = msg.get('role', '?')
                    content = msg.get('content', '')[:300]
                    print(f"  [{role}]: {content[:200]}...")
                    print()

conn.close()
