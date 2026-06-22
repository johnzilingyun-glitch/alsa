import asyncio
from datetime import datetime, timezone
import json
from python_service.app.services.backtest_engine_service import BacktestEngine

async def main():
    engine = BacktestEngine()
    try:
        res = await engine.run(
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="demo",
            market="CN",
            params={"target_symbol": "600519"}
        )
        print("\n=== Backtest Result Summary ===")
        if res:
            print("Keys in response:", res.keys())
            if "metrics" in res:
                print("Metrics:", json.dumps(res["metrics"], indent=2))
            if "trades" in res:
                print("Total Trades:", len(res["trades"]))
        else:
            print("Backtest returned empty result!")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
