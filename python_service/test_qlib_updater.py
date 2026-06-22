import asyncio
from app.services.qlib_data_updater import download_and_update_qlib_data
async def main():
    await asyncio.get_event_loop().run_in_executor(None, download_and_update_qlib_data, "600519", "2023-01-01", "2023-03-31")
asyncio.run(main())
