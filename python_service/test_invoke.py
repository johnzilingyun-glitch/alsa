import asyncio
from app.services.backtest_engine_service import BacktestEngine

async def main():
    engine = BacktestEngine(init_cash=100000.0)
    try:
        # About 486 trading days
        res = await engine.run("2021-01-01", "2023-01-01", "custom_rule", "CN", params={"target_symbol": "SH600519"})
        print("Success:", res["final_account"])
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
