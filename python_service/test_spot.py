import akshare as ak

def test():
    try:
        df_a = ak.stock_zh_a_spot_em()
        df_a['量比'] = df_a['量比'].replace("-", 0).astype(float)
        df_a = df_a.sort_values("量比", ascending=False).head(5)
        print("A-Share Spots (Top Vol Ratio):", df_a[["代码", "名称", "量比", "涨跌幅"]])
    except Exception as e:
        print("A-Share failed:", e)

    try:
        df_hk = ak.stock_hk_spot_em()
        df_hk['量比'] = df_hk['量比'].replace("-", 0).astype(float)
        df_hk = df_hk.sort_values("量比", ascending=False).head(5)
        print("HK-Share Spots (Top Vol Ratio):", df_hk[["代码", "名称", "量比", "涨跌幅"]])
    except Exception as e:
        print("HK-Share failed:", e)

    try:
        df_us = ak.stock_us_spot_em()
        df_us = df_us.sort_values("成交量", ascending=False).head(5) # US spot might not have 量比?
        print("US-Share Spots (Top Volume):", df_us.columns)
    except Exception as e:
        print("US-Share failed:", e)

test()
