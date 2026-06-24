import sys
import os

project_root = "/home/ubuntu/work/alsa"
sys.path.insert(0, os.path.join(project_root, "python_service"))
sys.path.insert(0, project_root)

print("Importing discussion_service...")
from app.services.discussion_service import DiscussionService
ds = DiscussionService()

print("Calling _assemble_prompt...")
try:
    ds._assemble_prompt(
        role="Sentiment Analyst",
        symbol="AAPL",
        name="Apple",
        snapshot={},
        history={},
        template="test",
        brain_ctx={},
        language="zh-CN",
        search_enrichment={"latest_news": []}
    )
    print("Successfully called _assemble_prompt without errors!")
except Exception:
    import traceback
    traceback.print_exc()
