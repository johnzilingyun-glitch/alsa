import os
import re

root_dir = r"d:\zily\alsa\alsa\PaperTrading_System"
patterns = [
    re.compile(r"mock-trading", re.IGNORECASE),
    re.compile(r"mock_trading", re.IGNORECASE),
    re.compile(r"accounts", re.IGNORECASE),
    re.compile(r"positions", re.IGNORECASE),
    re.compile(r"trades", re.IGNORECASE)
]

results = []

for dirpath, _, filenames in os.walk(root_dir):
    for filename in filenames:
        if filename.endswith(".py") or filename.endswith(".sh"):
            filepath = os.path.join(dirpath, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        for p in patterns:
                            if p.search(line):
                                rel_path = os.path.relpath(filepath, root_dir)
                                results.append(f"{rel_path}:{line_num}: {line.strip()}")
            except Exception as e:
                pass

print(f"Found {len(results)} occurrences:")
for r in results[:100]:
    print(r)
