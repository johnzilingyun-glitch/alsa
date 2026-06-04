import os
import glob
import re

d = r'd:\zily\alsa\alsa\python_service\app\prompting\templates'
files = glob.glob(os.path.join(d, '*.txt'))

# Patterns to remove
# 1. Any block starting with **输出纪律 (OUTPUT DISCIPLINE... down to ...删除中间草稿和过渡句。 or similar lines
# 2. **STRICT OUTPUT FORMAT (MANDATORY)** blocks
# We will use regex to aggressively match these blocks.

patterns = [
    re.compile(r'\*\*输出纪律\s*\(OUTPUT DISCIPLINE[^\)]*\)\*\*.*?(?:过渡句。|专业分析内容。|文本。|过渡句|过渡句\n)', re.DOTALL),
    re.compile(r'\*\*STRICT OUTPUT FORMAT\s*\(MANDATORY\)\*\*.*?(?:面向读者的文本\n\s*-\s*[^\n]*|institutional\.|presentation\.)\n?', re.DOTALL),
    # Also English variations
    re.compile(r'\*\*OUTPUT DISCIPLINE[^\*]*\*\*.*?(?:intermediate drafts and transitions\.|unprofessional\.)', re.DOTALL),
    re.compile(r'1\.\s*START DIRECTLY with the report content[^\n]*\n2\.\s*Use[^\n]*\n(?:3\.\s*[^\n]*\n)?(?:4\.\s*[^\n]*\n)?(?:5\.\s*[^\n]*\n)?', re.DOTALL),
]

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        original_content = file.read()
    
    content = original_content
    for p in patterns:
        content = p.sub('', content)
    
    # manual cleanup of any remaining specific rules like:
    content = re.sub(r'最终输出中\*\*严禁\*\*包含以下内容：.*?(?:过渡句\n|文本\n)', '', content, flags=re.DOTALL)
    content = re.sub(r'\n{3,}', '\n\n', content) # clean up extra newlines
    
    if content != original_content:
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content.strip() + '\n')
        print(f"Cleaned {os.path.basename(f)}")
print("Cleanup complete.")
