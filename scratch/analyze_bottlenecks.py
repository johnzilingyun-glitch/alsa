import json
import re
import os
from datetime import datetime

LOG_FILE = os.path.join(os.getcwd(), 'logs', 'debug_records.log')

def analyze_logs():
    if not os.path.exists(LOG_FILE):
        print(f"Error: Log file not found at {LOG_FILE}")
        return

    print(f"🔍 Analyzing {LOG_FILE}...")
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into entries using the separator
    entries = content.split('-' * 50)
    
    bottlenecks = []
    tool_executions = []
    errors = []

    for entry in entries:
        if not entry.strip():
            continue
        
        # Extract metadata
        meta_match = re.search(r'\[(.*?)\] \[(.*?)\]', entry)
        if not meta_match:
            continue
            
        timestamp = meta_match.group(1)
        log_type = meta_match.group(2).lower()
        
        # Extract data payload (starts after metadata line)
        data_lines = entry.split('\n')[1:]
        data_str = '\n'.join(data_lines).strip()
        
        try:
            data = json.loads(data_str)
        except:
            data = data_str

        if log_type == 'tool_execution':
            tool_executions.append({
                'tool': data.get('tool'),
                'elapsed': data.get('elapsed', 0),
                'query': data.get('args', {}).get('query'),
                'timestamp': timestamp
            })
        elif 'error' in log_type:
            errors.append({
                'type': log_type,
                'message': data if isinstance(data, str) else data.get('error', 'unknown'),
                'timestamp': timestamp
            })

    # Report tool latency
    if tool_executions:
        print("\n⏳ --- Tool Latency ---")
        sorted_tools = sorted(tool_executions, key=lambda x: x['elapsed'], reverse=True)
        for t in sorted_tools[:10]:
            print(f"[{t['timestamp']}] {t['tool']} took {t['elapsed']}ms | Query: {t['query']}")

    # Report errors
    if errors:
        print("\n❌ --- Errors ---")
        for e in errors[:5]:
            print(f"[{e['timestamp']}] {e['type']}: {e['message'][:200]}...")

    if not tool_executions and not errors:
        print("\nNo significant bottlenecks or errors found in logs.")

if __name__ == "__main__":
    analyze_logs()
