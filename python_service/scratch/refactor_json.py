import os
import glob
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Replace json.loads(job.result_payload) with job.result_payload
    content = re.sub(r'json\.loads\(([^.]+\.result_payload)\)', r'\1 if isinstance(\1, dict) else (json.loads(\1) if \1 else None)', content)
    
    # Replace json.dumps(result, default=json_serial) with result (or similar assignments)
    content = re.sub(r'(\w+\.result_payload)\s*=\s*json\.dumps\(([^,)]+)(?:,\s*default=json_serial)?\)', r'\1 = \2', content)

    with open(filepath, 'w') as f:
        f.write(content)

for root, _, files in os.walk('/home/ubuntu/work/alsa/python_service/app'):
    for file in files:
        if file.endswith('.py'):
            process_file(os.path.join(root, file))

print("Done")
