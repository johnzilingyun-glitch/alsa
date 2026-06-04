import os
import glob
import re

d = r'd:\zily\alsa\alsa\python_service\app\prompting\templates'
files = glob.glob(os.path.join(d, '*.txt'))

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    new_lines = []
    current_expected = 1
    changed = False
    
    for line in lines:
        # Match lines like "8. **Text**:" or "5. Text"
        match = re.match(r'^(\d+)\.\s+(.*)', line)
        if match:
            num = int(match.group(1))
            # If the current number is not what we expect (e.g. it's 8 but we want 1)
            # or if it's just the next in sequence, we renumber it to current_expected
            new_line = f"{current_expected}. {match.group(2)}\n"
            if new_line != line:
                changed = True
            new_lines.append(new_line)
            current_expected += 1
        else:
            new_lines.append(line)
            # We don't reset current_expected because some lists have empty lines or paragraphs in between.
            # We assume each prompt file only has ONE main numbered task list.

    if changed:
        with open(f, 'w', encoding='utf-8') as file:
            file.writelines(new_lines)
        print(f"Fixed numbering in {os.path.basename(f)}")

print("Numbering fix complete.")
