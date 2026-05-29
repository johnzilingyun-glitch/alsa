import sqlite3

try:
    conn = sqlite3.connect("data/app.db")
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE mockaccount ADD COLUMN market VARCHAR(50) DEFAULT 'A-Share';")
    print("Added market to mockaccount")
except Exception as e:
    print(e)

try:
    cursor.execute("ALTER TABLE mockposition ADD COLUMN market VARCHAR(50) DEFAULT 'A-Share';")
    print("Added market to mockposition")
except Exception as e:
    print(e)

try:
    cursor.execute("ALTER TABLE mocktrade ADD COLUMN market VARCHAR(50) DEFAULT 'A-Share';")
    print("Added market to mocktrade")
except Exception as e:
    print(e)

conn.commit()
conn.close()
