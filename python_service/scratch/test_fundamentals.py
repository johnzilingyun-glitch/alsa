import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.market_snapshot_service import market_snapshot_service
from app.services.report_generator_service import ReportGeneratorService

async def main():
    snapshot = await market_snapshot_service.create_snapshot("A-Share", "300274")
    
    report_svc = ReportGeneratorService()
    fundamentals = report_svc._compile_fundamentals(snapshot, "CNY")
    
    print("Compiled Fundamentals:")
    print(json.dumps(fundamentals, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
