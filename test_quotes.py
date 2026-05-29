import asyncio
import sys
import os

# add parent dir so we can import python_service
sys.path.insert(0, '/home/zily/alsa')
from python_service.app.services.market_data_service import market_data_service

async def main():
    quotes = await market_data_service.get_quotes(["000792", "00700", "AAPL"])
    for q in quotes:
        print(f"Symbol: {q.get('symbol')}, Price: {q.get('price')}, Error: {q.get('error')}")

if __name__ == "__main__":
    asyncio.run(main())
