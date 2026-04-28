import json
import sqlite3
import os
import asyncio
from app.services.report_generator_service import ReportGeneratorService

async def main():
    db_path = "data/app_v3.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get the latest completed MSFT job
    cursor.execute("SELECT result_payload FROM analysisjob WHERE symbol='MSFT' AND status='completed' ORDER BY finished_at DESC LIMIT 1")
    row = cursor.fetchone()
    
    if not row or not row[0]:
        print("No completed MSFT job found.")
        return
        
    result = json.loads(row[0])
    
    report_service = ReportGeneratorService()
    # Save to a new file as requested: MSFT_Institutional_Report_v10.html
    new_report_path = os.path.abspath("MSFT_Institutional_Report_v10.html")
    
    # Call the async version directly since we are already in an event loop
    await report_service.generate_html_report_async(result, new_report_path)
    
    print(f"New report generated: {new_report_path}")
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
