import akshare as ak
import json

try:
    print("Testing stock_financial_abstract_ths:")
    df1 = ak.stock_financial_abstract_ths(symbol="002156")
    print(df1.head(2).to_json(orient='records', force_ascii=False))
except Exception as e:
    print(f"Error 1: {e}")

try:
    print("\nTesting stock_lrb_em:")
    df2 = ak.stock_lrb_em(symbol="SZ002156") # usually em uses SH/SZ prefix
    print(df2.head(2).to_json(orient='records', force_ascii=False))
except Exception as e:
    print(f"Error 2: {e}")
    
try:
    print("\nTesting stock_financial_abstract:")
    df3 = ak.stock_financial_abstract(symbol="002156") 
    print(df3.head(2).to_json(orient='records', force_ascii=False))
except Exception as e:
    print(f"Error 3: {e}")
