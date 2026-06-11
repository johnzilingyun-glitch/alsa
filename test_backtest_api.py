import asyncio
from datetime import datetime, timezone
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
            for k in ["total_return", "annual_return", "max_drawdown", "sharpe_ratio", "total_trade_count"]:
                print(f"  {k}: {res.get(k)}")
        else:
            print("Backtest returned empty result!")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
