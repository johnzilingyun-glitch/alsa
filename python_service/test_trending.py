import akshare as ak

def test():
    # HK-Share trending via turnover
    df_hk = ak.stock_hk_spot_em()
    df_hk = df_hk.sort_values(by="成交额", ascending=False).head(5)
    print("HK-Share:", df_hk[["代码", "名称", "成交额"]])

    # US-Share trending via turnover
    df_us = ak.stock_us_spot_em()
    df_us = df_us.sort_values(by="成交额", ascending=False).head(5)
    print("US-Share:", df_us[["代码", "名称", "成交额"]])

test()
