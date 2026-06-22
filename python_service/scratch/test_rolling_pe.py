import pandas as pd
import numpy as np
import yfinance as yf
import traceback

def compute_rolling_pe(symbol):
    print(f"Testing rolling PE computation for {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # 1. Get price history
    hist = ticker.history(period="2y")
    if hist.empty:
        print("Error: No price history")
        return
        
    info = ticker.info
    trailing_pe = info.get("trailingPE")
    trailing_eps = info.get("trailingEps")
    
    print(f"yfinance info - trailingPE: {trailing_pe}, trailingEps: {trailing_eps}")
    
    # 2. Try to calculate historical TTM EPS using earnings_dates
    rolling_pe = None
    try:
        dates = ticker.earnings_dates
        if dates is not None and not dates.empty and 'Reported EPS' in dates.columns:
            eps_series = dates['Reported EPS'].dropna().sort_index()
            if len(eps_series) >= 4:
                # Rolling 4 quarters sum
                ttm_eps = eps_series.rolling(4).sum().dropna()
                if not ttm_eps.empty:
                    # Align timezones
                    # hist.index is datetime64[ns, tz]
                    # ttm_eps.index is datetime64[ns, tz] or object, convert both to tz-naive or keep same tz
                    hist_idx = hist.index
                    ttm_idx = ttm_eps.index
                    
                    # Convert to same datetime type
                    hist_df = pd.DataFrame({'Close': hist['Close']})
                    # Sort indices
                    hist_df = hist_df.sort_index()
                    
                    ttm_df = pd.DataFrame({'TTM_EPS': ttm_eps}).sort_index()
                    
                    # Convert index to same dtype, e.g. tz-naive datetime64[ns] or matching dtype
                    hist_df.index = hist_df.index.tz_localize(None).astype('datetime64[ns]')
                    ttm_df.index = ttm_df.index.tz_localize(None).astype('datetime64[ns]')
                    
                    merged = pd.merge_asof(hist_df, ttm_df, left_index=True, right_index=True, direction='backward')
                    
                    # Check if we have valid TTM_EPS
                    if not merged['TTM_EPS'].isna().all():
                        hist_pe = merged['Close'] / merged['TTM_EPS']
                        hist_pe = hist_pe[(hist_pe > 0) & (hist_pe < 1000)]
                        if len(hist_pe) > 30:
                            rolling_pe = hist_pe
                            print("Successfully calculated PE using earnings_dates!")
                            print(f"Sample PE values (first 5):\n{rolling_pe.head(5)}")
                            print(f"Sample PE values (last 5):\n{rolling_pe.tail(5)}")
    except Exception as e:
        print("Failed to calculate PE using earnings_dates:")
        traceback.print_exc()
        
    if rolling_pe is None:
        # Fallback to static PE
        if trailing_eps and trailing_eps > 0:
            hist_pe = hist['Close'] / trailing_eps
            hist_pe = hist_pe[(hist_pe > 0) & (hist_pe < 1000)]
            if len(hist_pe) > 30:
                rolling_pe = hist_pe
                print("Fallback: calculated PE using static trailingEps")
        else:
            print("Fallback Failed: No valid trailingEps")

if __name__ == '__main__':
    compute_rolling_pe("MSFT")
    print("-" * 50)
    compute_rolling_pe("AAPL")
