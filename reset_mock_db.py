import sqlite3

conn = sqlite3.connect("data/app.db")
cursor = conn.cursor()

tables_to_drop = [
    "mockaccount",
    "mockposition",
    "mocktrade",
    "mocksnapshot",
    "mockanomaly"
]

for table in tables_to_drop:
    try:
        cursor.execute(f"DROP TABLE {table};")
        print(f"Dropped {table}")
    except Exception as e:
        print(f"Could not drop {table}: {e}")

conn.commit()
conn.close()
