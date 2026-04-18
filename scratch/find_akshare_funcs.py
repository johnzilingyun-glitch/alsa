import akshare as ak
import pandas as pd

def find_functions():
    all_funcs = dir(ak)
    
    # 1. HK
    hk_funcs = [f for f in all_funcs if 'hk' in f and 'spot' in f]
    print(f"HK spot candidates: {hk_funcs}")
    
    # 2. LHB
    lhb_funcs = [f for f in all_funcs if 'lhb' in f]
    print(f"LHB candidates: {lhb_funcs}")
    
    # 3. Margin (两融)
    margin_funcs = [f for f in all_funcs if 'margin' in f]
    print(f"Margin candidates: {margin_funcs}")
    
    # 4. Announcements
    ann_funcs = [f for f in all_funcs if 'announcement' in f]
    print(f"Announcement candidates: {ann_funcs}")

    # 5. Trends / Social
    news_funcs = [f for f in all_funcs if 'news' in f]
    print(f"News/Social candidates: {news_funcs}")

if __name__ == "__main__":
    find_functions()
