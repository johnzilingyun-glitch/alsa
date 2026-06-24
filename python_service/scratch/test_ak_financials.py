import akshare as ak

try:
    df = ak.stock_financial_analysis_indicator_em(symbol="002156")
    if not df.empty:
        print(df.head(2).to_json(orient='records', force_ascii=False))
except Exception as e:
    print(f"Error: {e}")
