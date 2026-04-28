import re
import os

source_file = "src/services/discussion/expertPrompts.ts"
output_dir = "python_service/app/prompting/templates"
os.makedirs(output_dir, exist_ok=True)

with open(source_file, "r", encoding="utf-8") as f:
    content = f.read()

# Extract ROLE_INSTRUCTIONS_ZH
zh_match = re.search(r"const ROLE_INSTRUCTIONS_ZH: Record<AgentRole, string> = (\{.*?\});", content, re.DOTALL)
if zh_match:
    zh_content = zh_match.group(1)
    # Extract roles and prompts
    roles = re.findall(r"'([^']+)': `(.*?)`,", zh_content, re.DOTALL)
    for role, prompt in roles:
        role_file = role.replace(" ", "_").lower() + "_zh.txt"
        with open(os.path.join(output_dir, role_file), "w", encoding="utf-8") as f:
            f.write(prompt.strip())
        print(f"Extracted {role} (ZH)")

# Extract ROLE_INSTRUCTIONS_EN
en_match = re.search(r"const ROLE_INSTRUCTIONS_EN: Record<AgentRole, string> = (\{.*?\});", content, re.DOTALL)
if en_match:
    en_content = en_match.group(1)
    roles = re.findall(r"'([^']+)': `(.*?)`,", en_content, re.DOTALL)
    for role, prompt in roles:
        role_file = role.replace(" ", "_").lower() + "_en.txt"
        with open(os.path.join(output_dir, role_file), "w", encoding="utf-8") as f:
            f.write(prompt.strip())
        print(f"Extracted {role} (EN)")
