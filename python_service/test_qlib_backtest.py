import asyncio
from app.services.backtest_engine_service import BacktestEngine
import json

async def test_qlib_backtest():
    engine = BacktestEngine(init_cash=100000, commission=0.0003)
    
    params = {
        "target_symbol": "600519",
        "buy_rules": [
            {"type": "price_above_ma", "ma_period": 5}
        ],
        "sell_rules": [
            {"type": "price_below_ma", "ma_period": 5}
        ],
        "position_mode": "fixed_shares",
        "position_value": 100,
        "stop_loss_pct": 5.0
    }
    
    print("Running test backtest for 600519...")
    try:
        results = await engine.run(
            start_date="2023-01-01",
            end_date="2023-03-31",
            strategy="custom_rule",
            market="CN",
            params=params
        )
        print("Backtest successful!")
        print(f"Final Equity: {results.get('final_account')}")
        print(f"Total Snapshots: {len(results.get('snapshots', []))}")
        metrics = results.get("metrics", {})
        print(f"Ann Return: {metrics.get('annualized_return', {}).get('risk')}")
        print(f"Max DD: {metrics.get('max_drawdown', {}).get('risk')}")
    except Exception as e:
        print(f"Backtest failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_qlib_backtest())
