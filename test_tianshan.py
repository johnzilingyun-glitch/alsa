import asyncio
from datetime import datetime, timezone
import pandas as pd
from vnpy.trader.constant import Exchange, Interval

async def main():
    try:
        from python_service.app.services.data_sync_service import data_sync_service
        
        symbol = "002532"
        exchange = Exchange.SZSE
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        end = datetime(2026, 6, 10, tzinfo=timezone.utc)
        
        print(f"Testing sync for {symbol}.{exchange.value} from {start.date()} to {end.date()}...")
        success = await data_sync_service.ensure_local_data(symbol, exchange, start, end)
        print(f"Sync success: {success}")
        
        db = data_sync_service.database
        bars = db.load_bar_data(symbol, exchange, Interval.DAILY, start, end)
        print(f"Loaded {len(bars)} bars from local DB:")
        if bars:
            df = pd.DataFrame([
                {"date": b.datetime.strftime('%Y-%m-%d'), "open": b.open_price, "high": b.high_price, "low": b.low_price, "close": b.close_price, "volume": b.volume}
                for b in bars
            ])
            print(df)
        else:
            print("No bars found in DB!")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
