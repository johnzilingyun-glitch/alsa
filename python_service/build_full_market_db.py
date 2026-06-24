import sqlite3
import akshare as ak
import pandas as pd
import time

DB_PATH = "fundamentals.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS valuation (
            symbol TEXT,
            date TEXT,
            pe_ttm REAL,
            market_cap REAL,
            UNIQUE(symbol, date)
        )
    ''')
    conn.commit()
    return conn

def get_all_symbols():
    try:
        # Get all A-share names and codes
        df = ak.stock_info_a_code_name()
        return df['code'].tolist()
    except Exception as e:
        print(f"Failed to get full list: {e}")
        # fallback to a small list if network is totally broken
        return ["600519", "000333", "601398"]

def get_yf_symbol(code):
    if code.startswith('6'):
        return f"{code}.SS"
    else:
        return f"{code}.SZ"

def build_db():
    conn = init_db()
    cursor = conn.cursor()
    
    symbols = get_all_symbols()
    print(f"Found {len(symbols)} stocks. Starting download for full market...")
    
    for i, pure_symbol in enumerate(symbols):
        yf_symbol = get_yf_symbol(pure_symbol)
        
        # skip B shares or very weird codes if any
        if not pure_symbol.startswith(('60', '00', '30', '68')):
            continue
            
        print(f"[{i+1}/{len(symbols)}] Fetching data for {pure_symbol} ({yf_symbol})...")
        try:
            pe_df = ak.stock_zh_valuation_baidu(symbol=pure_symbol, indicator='市盈率(TTM)', period='全部')
            pe_df.rename(columns={'value': 'pe_ttm'}, inplace=True)
            
            mc_df = ak.stock_zh_valuation_baidu(symbol=pure_symbol, indicator='总市值', period='全部')
            mc_df.rename(columns={'value': 'market_cap'}, inplace=True)
            
            merged = pd.merge(pe_df, mc_df, on='date', how='inner')
            merged['symbol'] = yf_symbol
            
            merged['date'] = pd.to_datetime(merged['date'])
            merged = merged[merged['date'] >= '2019-01-01']
            merged['date'] = merged['date'].dt.strftime('%Y-%m-%d')
            
            if not merged.empty:
                records = merged[['symbol', 'date', 'pe_ttm', 'market_cap']].values.tolist()
                cursor.executemany('''
                    INSERT OR REPLACE INTO valuation (symbol, date, pe_ttm, market_cap)
                    VALUES (?, ?, ?, ?)
                ''', records)
                conn.commit()
                print(f"  -> Inserted {len(records)} records.")
        except Exception as e:
            print(f"  -> Failed to fetch {pure_symbol}: {e}")
            
        time.sleep(0.2) # Rate limit avoidance

    conn.close()
    print("Full Market Database build complete.")

if __name__ == "__main__":
    build_db()
