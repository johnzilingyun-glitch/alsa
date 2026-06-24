import asyncio
import os
import sys

# Add project root to path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from python_service.app.services.macro_service import macro_service

async def test_macro():
    print("Testing FX with search fallback...")
    fx = await macro_service.get_latest_fx()
    print(f"FX Result: {fx}")
    
    print("\nTesting Commodities with search...")
    commodities = await macro_service.get_commodity_prices(["Lithium Carbonate"])
    print(f"Commodities Result: {commodities}")

if __name__ == "__main__":
    asyncio.run(test_macro())
