import akshare as ak

def test():
    try:
        # CSI 300
        csi300 = ak.index_stock_cons_weight_csindex(symbol="000300")
        print("CSI300:", csi300['成分券代码'].tolist()[:10])
    except Exception as e:
        print("CSI300 Error:", e)

    try:
        # HSI (Hang Seng)
        # Using Sina API for HK indices usually works, or EM
        # Wait, there's no reliable HSI components in akshare without web scraping EM.
        print("AkShare doesn't have a stable HSI component API that returns pure symbols easily.")
    except Exception as e:
        pass

test()
