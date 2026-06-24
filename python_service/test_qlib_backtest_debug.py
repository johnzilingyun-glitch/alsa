import asyncio
from app.services.backtest_engine_service import BacktestEngine
import traceback

async def main():
    engine = BacktestEngine(init_cash=100000, commission=0.0003)
    try:
        results = await engine.run(
            start_date="2023-01-01",
            end_date="2023-03-31",
            strategy="custom_rule",
            market="CN",
            params={"target_symbol": "600519"}
        )
        print("Success:", results)
    except Exception:
        traceback.print_exc()

asyncio.run(main())
