import sys
import os
from dotenv import load_dotenv

# Add the project root to sys.path
sys.path.append(os.getcwd())

# Load .env
load_dotenv(".env", override=True)

from python_service.app.db.sqlite import init_db
from python_service.app.db.models import *

try:
    print(f"SQLITE_PATH: {os.getenv('SQLITE_PATH')}")
    print("Initializing database...")
    init_db()
    print("Database initialized successfully.")
except Exception as e:
    print(f"Error initializing database: {e}")
