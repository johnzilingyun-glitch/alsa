import os
import re

def replace_in_file(filepath, target, replacement):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if target in content:
        new_content = content.replace(target, replacement)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Successfully updated {filepath}")
    else:
        print(f"Target not found in {filepath}")

def replace_dotenv_in_file(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'^([ \t]*)load_dotenv\(os\.path\.join\(root_dir, "\.env"\), override=True\)'
    
    def repl(match):
        indent = match.group(1)
        return f'{indent}load_dotenv(os.path.join(root_dir, ".env"), override=True)\n{indent}load_dotenv(os.path.join(root_dir, ".env.runtime"), override=True)'
        
    new_content = re.sub(pattern, repl, content, flags=re.MULTILINE)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Successfully updated {filepath} with runtime env loading")
    else:
        print(f"Pattern not found in {filepath}")

# 1. debugRoutes.ts
replace_in_file(
    "/home/zily/alsa/server/debugRoutes.ts",
    "const envPath = path.join(process.cwd(), '.env');",
    "const envPath = path.join(process.cwd(), '.env.runtime');"
)
replace_in_file(
    "/home/zily/alsa/server/debugRoutes.ts",
    "res.status(500).json({ error: 'Failed to update .env' });",
    "res.status(500).json({ error: 'Failed to update .env.runtime' });"
)

# 2. server.ts
replace_in_file(
    "/home/zily/alsa/server.ts",
    "dotenv.config();",
    "dotenv.config();\ndotenv.config({ path: '.env.runtime' });"
)

# 3. Python files
replace_dotenv_in_file("/home/zily/alsa/python_service/app/services/llm_gateway.py")
replace_dotenv_in_file("/home/zily/alsa/python_service/app/services/brain_manager.py")
replace_dotenv_in_file("/home/zily/alsa/python_service/cli.py")
