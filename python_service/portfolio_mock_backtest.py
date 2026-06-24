import yfinance as yf
import pandas as pd
import numpy as np

# 模拟的主板股票池 (代表性个股)
SYMBOLS = [
    "600519.SS", # 贵州茅台
    "601398.SS", # 工商银行
    "600036.SS", # 招商银行
    "601318.SS", # 中国平安
    "000858.SZ", # 五粮液
    "000333.SZ", # 美的集团
    "600900.SS", # 长江电力
    "601012.SS", # 隆基绿能
    "600276.SS", # 恒瑞医药
    "002594.SZ", # 比亚迪
    "601888.SS", # 中国中免
    "603288.SS", # 海天味业
    "601166.SS", # 兴业银行
    "600030.SS", # 中信证券
    "600104.SS", # 上汽集团
]

START_DATE = "2020-01-01"
END_DATE = "2026-05-31"

def fetch_data():
    print(f"Fetching historical data for {len(SYMBOLS)} stocks...")
    # download multi-ticker data
    df = yf.download(SYMBOLS, start=START_DATE, end=END_DATE, progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        closes = df['Close']
    else:
        # fallback if single symbol
        closes = pd.DataFrame(df['Close'], columns=[SYMBOLS[0]])
        
    closes = closes.ffill() # forward fill missing values
    return closes

def generate_mock_fundamentals(closes_df):
    """
    Generate mock PE and Market Cap data aligned with the price dataframe index.
    PE ~ Normal(18, 8)
    MC ~ Normal(2000, 1000) billion RMB
    """
    np.random.seed(42) # fixed seed for reproducibility
    dates = closes_df.index
    symbols = closes_df.columns
    
    # Using random walk to make fundamentals somewhat realistic over time
    pe_data = pd.DataFrame(index=dates, columns=symbols)
    mc_data = pd.DataFrame(index=dates, columns=symbols)
    
    for sym in symbols:
        # Base PE between 10 and 30
        base_pe = np.random.uniform(10, 30)
        pe_walk = np.random.normal(0, 0.5, len(dates)).cumsum()
        pe_data[sym] = np.clip(base_pe + pe_walk, 5, 100) # PE > 5
        
        # Base MC between 500 and 3000 (billion)
        base_mc = np.random.uniform(500, 3000)
        mc_walk = np.random.normal(0, 20, len(dates)).cumsum()
        mc_data[sym] = np.clip(base_mc + mc_walk, 100, 5000)
        
    return pe_data, mc_data

def run_portfolio_backtest():
    closes = fetch_data()
    if closes.empty:
        print("Failed to fetch data.")
        return
        
    pe_df, mc_df = generate_mock_fundamentals(closes)
    
    # Portfolio variables
    initial_capital = 1_000_000.0
    cash = initial_capital
    positions = {sym: 0 for sym in SYMBOLS} # holding shares
    
    portfolio_values = []
    rebalance_records = []
    
    # Rebalance every 3 months (approx 63 trading days)
    REBALANCE_INTERVAL = 63 
    days_since_rebalance = 0
    
    print("--- 启动多股截面调仓回测引擎 ---")
    print(f"回测区间: {closes.index[0].date()} 到 {closes.index[-1].date()}")
    print("调仓规则: 间隔3个月 (约63个交易日) | PE < 20 | 市值 > 1000亿 | 按市值排名前5 (股票池较小故取前5)")
    print("-" * 50)
    
    for i in range(len(closes.index)):
        dt = closes.index[i]
        current_prices = closes.iloc[i]
        
        # Calculate current portfolio value BEFORE rebalance
        current_value = cash
        for sym in SYMBOLS:
            if not pd.isna(current_prices[sym]) and positions[sym] > 0:
                current_value += positions[sym] * current_prices[sym]
                
        # Time to rebalance?
        if days_since_rebalance == 0 or days_since_rebalance >= REBALANCE_INTERVAL:
            # 1. Sell all existing positions
            for sym in SYMBOLS:
                if positions[sym] > 0 and not pd.isna(current_prices[sym]):
                    cash += positions[sym] * current_prices[sym]
                    positions[sym] = 0
            
            current_value = cash # all in cash now
            
            # 2. Get cross-sectional data
            pe_cross = pe_df.iloc[i]
            mc_cross = mc_df.iloc[i]
            
            # 3. Filter: PE < 20 and MC > 1000 (billion)
            valid_symbols = []
            for sym in SYMBOLS:
                if not pd.isna(current_prices[sym]) and pe_cross[sym] < 20 and mc_cross[sym] > 1000:
                    valid_symbols.append(sym)
                    
            # 4. Sort by MC descending and take top N
            # Since our pool is only 15 stocks, taking top 20 means taking all valid ones. Let's take top 5 for realism.
            sorted_symbols = sorted(valid_symbols, key=lambda s: mc_cross[s], reverse=True)
            target_symbols = sorted_symbols[:5]
            
            # 5. Buy new positions (Equal Weight)
            if len(target_symbols) > 0:
                allocation_per_stock = cash / len(target_symbols)
                
                print(f"[{dt.date()}] 执行调仓 | 总市值: {current_value:,.2f}")
                print(f"  -> 买入名单 ({len(target_symbols)}只): {', '.join(target_symbols)}")
                
                for sym in target_symbols:
                    price = current_prices[sym]
                    shares = int(allocation_per_stock // price)
                    cost = shares * price
                    cash -= cost
                    positions[sym] = shares
            else:
                print(f"[{dt.date()}] 执行调仓 | 无符合条件的标的，空仓等待。")
                
            days_since_rebalance = 1
        else:
            days_since_rebalance += 1
            
        portfolio_values.append(current_value)

    # Wrap up stats
    final_value = portfolio_values[-1]
    total_return = (final_value / initial_capital) - 1
    
    print("-" * 50)
    print("--- 回测结束 ---")
    print(f"初始资金: {initial_capital:,.2f}")
    print(f"期末资金: {final_value:,.2f}")
    print(f"总收益率: {total_return * 100:.2f}%")
    
if __name__ == "__main__":
    run_portfolio_backtest()
