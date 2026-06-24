import asyncio
import os
import sys

# Add project root to path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from python_service.app.services.market_snapshot_service import MarketSnapshotService
from python_service.app.lake.parquet_store import ParquetMarketStore

async def test_snapshot():
    store = ParquetMarketStore("data/parquet")
    service = MarketSnapshotService(store)
    print("Testing snapshot for 002156...")
    res = await service.create_snapshot("A-Share", "002156")
    print(f"Result: {res.get('name') if res else 'None'}")
    if res:
        print(f"History length: {len(res['history'])}")

if __name__ == "__main__":
    asyncio.run(test_snapshot())
