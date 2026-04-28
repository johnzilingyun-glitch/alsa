import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.market_data_service import market_data_service

async def main():
    res = await market_data_service.get_financial_summary("300274", "A-Share")
    print("Financial Summary:")
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
