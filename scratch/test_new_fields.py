import asyncio, sys
sys.path.insert(0, '.')
from python_service.app.services.market_data_service import MarketDataService

async def main():
    svc = MarketDataService()
    d = await svc.get_financial_summary('LI', 'US-Share')
    print('=== NEW FIELDS ===')
    print(f"totalCash: {d.get('totalCash')}")
    print(f"totalDebt: {d.get('totalDebt')}")
    print(f"netCash: {d.get('netCash')}")
    print(f"netCashPerShare: {d.get('netCashPerShare')}")
    print(f"sharesOutstanding: {d.get('sharesOutstanding')}")
    print(f"revenueYoY_annual: {d.get('revenueYoY_annual')}")
    print(f"enterpriseValue: {d.get('enterpriseValue')}")
    print(f"currency: {d.get('currency')}")
    print(f"financialCurrency: {d.get('financialCurrency')}")

    # Validate
    tc = d.get('totalCash') or 0
    td = d.get('totalDebt') or 0
    nc = d.get('netCash') or 0
    print(f"\n=== VALIDATION ===")
    print(f"totalCash: {tc/1e8:.1f}亿 CNY")
    print(f"totalDebt: {td/1e8:.1f}亿 CNY")
    print(f"netCash: {nc/1e8:.1f}亿 CNY")
    print(f"netCashPerShare: {d.get('netCashPerShare'):.2f} CNY")
    print(f"revenueYoY_annual: {d.get('revenueYoY_annual'):.2%}" if d.get('revenueYoY_annual') else "revenueYoY_annual: N/A")
    print(f"EV: {d.get('enterpriseValue')}")
    print(f"EV is None (mixed currency): {d.get('enterpriseValue') is None}")

asyncio.run(main())
