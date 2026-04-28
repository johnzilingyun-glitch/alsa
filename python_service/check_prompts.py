
import sys
import os
# Add project root to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from python_service.app.db.sqlite import session_factory
from python_service.app.db.models import PromptVersion
from sqlmodel import select

with session_factory() as session:
    statement = select(PromptVersion)
    results = session.exec(statement).all()
    for pv in results:
        print(f"Name: {pv.prompt_name}, Version: {pv.version}, Path: {pv.template_path}")
