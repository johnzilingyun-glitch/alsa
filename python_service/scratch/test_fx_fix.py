import asyncio
from app.services.macro_service import macro_service

async def test():
    print("Testing updated macro_service.get_latest_fx()...")
    data = await macro_service.get_latest_fx()
    print("Result:", data)

if __name__ == "__main__":
    asyncio.run(test())
