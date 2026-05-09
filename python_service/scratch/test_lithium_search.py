import asyncio
import os
from app.services.macro_service import macro_service
from app.services.search_service import search_service

async def test_search():
    print("Testing search for Lithium Carbonate...")
    # Mock the date
    query = "Lithium Carbonate price 2026-05-06 CNY/ton"
    res = await search_service.quick_search(query)
    print(f"Search Results:\n{res}")

if __name__ == "__main__":
    asyncio.run(test_search())
