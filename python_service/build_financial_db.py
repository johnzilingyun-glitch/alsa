import sqlite3
import akshare as ak
import pandas as pd
import datetime

# 对应 yfinance 的后缀
SYMBOLS_MAP = {
    "600519": "600519.SS",
    "601398": "601398.SS",
    "600036": "600036.SS",
    "601318": "601318.SS",
    "000858": "000858.SZ",
    "000333": "000333.SZ",
    "600900": "600900.SS",
    "601012": "601012.SS",
    "600276": "600276.SS",
    "002594": "002594.SZ",
    "601888": "601888.SS",
    "603288": "603288.SS",
    "601166": "601166.SS",
    "600030": "600030.SS",
    "600104": "600104.SS",
}

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

def build_db():
    conn = init_db()
    cursor = conn.cursor()
    
    for pure_symbol, yf_symbol in SYMBOLS_MAP.items():
        print(f"Fetching data for {pure_symbol} ({yf_symbol})...")
        try:
            # 获取市盈率
            pe_df = ak.stock_zh_valuation_baidu(symbol=pure_symbol, indicator='市盈率(TTM)', period='全部')
            pe_df.rename(columns={'value': 'pe_ttm'}, inplace=True)
            
            # 获取总市值 (单位：亿元)
            mc_df = ak.stock_zh_valuation_baidu(symbol=pure_symbol, indicator='总市值', period='全部')
            mc_df.rename(columns={'value': 'market_cap'}, inplace=True)
            
            # 合并
            merged = pd.merge(pe_df, mc_df, on='date', how='inner')
            merged['symbol'] = yf_symbol
            
            # 过滤掉 2020 年之前的数据，减小数据库体积
            merged['date'] = pd.to_datetime(merged['date'])
            merged = merged[merged['date'] >= '2019-01-01']
            merged['date'] = merged['date'].dt.strftime('%Y-%m-%d')
            
            # 插入数据库
            records = merged[['symbol', 'date', 'pe_ttm', 'market_cap']].values.tolist()
            cursor.executemany('''
                INSERT OR REPLACE INTO valuation (symbol, date, pe_ttm, market_cap)
                VALUES (?, ?, ?, ?)
            ''', records)
            conn.commit()
            print(f"  -> Inserted {len(records)} records for {yf_symbol}")
        except Exception as e:
            print(f"  -> Failed to fetch {pure_symbol}: {e}")

    conn.close()
    print("Database build complete.")

if __name__ == "__main__":
    build_db()
