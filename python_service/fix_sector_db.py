
file_path = "app/api/sector.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the import
content = content.replace("from ..db.database import build_session_factory, DATABASE_URL", "from ..db.database import session_factory")

# Replace the local assignment.
# We can just delete `session_factory = build_session_factory(DATABASE_URL)`
# But to be safe with indentation, we'll replace it with a comment or just remove it.
# Wait, some places might need `session_factory` if we removed the assignment but the import is inside the function?
# Yes, the import is inside the function, so `session_factory` is available in local scope.
# We'll replace the assignment line with nothing (but keep indentation by replacing just the statement with `pass` or empty string if we replace the whole line)

import re
content = re.sub(r"^[ \t]*session_factory = build_session_factory\(DATABASE_URL\)[ \t]*\n", "", content, flags=re.MULTILINE)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed sector.py")
