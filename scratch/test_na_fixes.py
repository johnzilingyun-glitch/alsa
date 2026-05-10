import asyncio, sys
sys.path.insert(0, '.')
from python_service.app.services.market_data_service import MarketDataService

async def test():
    svc = MarketDataService()
    data = await svc.get_financial_summary('LI', 'US-Share')
    
    print('=== Key N/A fields check ===')
    keys = ['enterpriseValue', 'capitalExpenditure', 'pePercentile', 
            'dividendYield', 'payoutRatio', 'heldPercentInsiders', 'heldPercentInstitutions']
    for k in keys:
        print(f"  {k}: {data.get(k)}")
    
    ev = data.get('enterpriseValue')
    if ev:
        print(f"\nEV (亿CNY): {ev/1e8:.1f}")
        print(f"EV (亿USD): {ev/6.8/1e8:.1f}")
    else:
        print("\nEV: still None!")
    
    capex = data.get('capitalExpenditure')
    if capex:
        print(f"CAPEX (亿CNY): {capex/1e8:.1f}")
    else:
        print("CAPEX: still None!")
    
    pe_pct = data.get('pePercentile')
    if pe_pct is not None:
        print(f"PE Percentile: {pe_pct*100:.1f}%")
    else:
        print("PE Percentile: still None!")

    # Test get_quotes EV too
    quotes = await svc.get_quotes(['LI'])
    if quotes:
        q = quotes[0]
        qev = q.get('enterpriseValue')
        print(f"\nQuotes EV: {qev}")
        if qev:
            print(f"Quotes EV (亿CNY): {qev/1e8:.1f}")

asyncio.run(test())
