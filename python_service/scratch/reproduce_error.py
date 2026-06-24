import sys
import os

project_root = "/home/ubuntu/work/alsa"
sys.path.insert(0, os.path.join(project_root, "python_service"))
sys.path.insert(0, project_root)

print("Importing discussion_service...")
try:
    print("Successfully imported DiscussionService!")
except Exception:
    import traceback
    traceback.print_exc()
