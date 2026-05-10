import akshare as ak
from datetime import datetime, timedelta

# Get last 10 days of lithium carbonate data to check freshness
for d in range(0, 10):
    dt = (datetime.now() - timedelta(days=d)).strftime('%Y%m%d')
    try:
        df = ak.futures_spot_price(date=dt, vars_list=['LC'])
        if df is not None and not df.empty:
            row = df[df['symbol']=='LC']
            if not row.empty:
                spot = row.iloc[0]["spot_price"]
                date_val = row.iloc[0].get("date", dt)
                print(f"{dt}: spot_price={spot}, date={date_val}")
    except Exception as e:
        err_str = str(e)
        if '非交易日' in err_str:
            print(f"{dt}: (non-trading day)")
        else:
            print(f"{dt}: Error - {err_str[:80]}")
