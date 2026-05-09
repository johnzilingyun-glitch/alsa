import asyncio
import os
import sys

# Add the project root to the python path so imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.market_data_service import market_data_service

async def main():
    res = await market_data_service._fetch_financial_summary("002156", "A-Share")
    print("Search Context:", res.get('financials', {}).get('searchContext'))
    print("Net Profit:", res.get('netProfit'))

asyncio.run(main())
