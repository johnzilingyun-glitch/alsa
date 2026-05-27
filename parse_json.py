import json

try:
    with open('/home/zily/alsa/recent_job.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    discussion = data.get('discussion', [])
    print("Expert content lengths:")
    for x in discussion:
        print(f"Role: {x.get('role')}, Length: {len(x.get('content', ''))}")
    
    print("\n--- Sector Stock Screener Content ---")
    screener = [x for x in discussion if x.get('role') == 'Sector Stock Screener']
    if screener:
        print(screener[0].get('content', ''))
    else:
        print("NOT FOUND")
except Exception as e:
    print(f"Error: {e}")
