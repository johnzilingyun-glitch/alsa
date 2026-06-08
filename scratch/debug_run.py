import json
import sys
import os
import asyncio

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from python_service.app.services.report_generator_service import ReportGeneratorService

async def main():
    service = ReportGeneratorService()
    
    # Load raw job JSON
    with open('/home/ubuntu/work/alsa/scratch/job_0fa38353.json', 'r', encoding='utf-8') as f:
        job_data = json.load(f)
        
    stock_info = job_data.get("stockInfo", {})
    symbol = job_data.get("symbol") or stock_info.get("symbol", "UNKNOWN")
    market = job_data.get("market") or stock_info.get("market", "US-Share")
    discussion_msgs = job_data.get("discussion", [])
    snapshot = job_data.get("snapshot") or {}
    
    cleaned_msgs = [{"role": m["role"], "content": service._strip_thinking_prefix(m["content"])} for m in discussion_msgs]
    full_discussion = "\n".join([f"[{m['role']}]: {m['content']}" for m in cleaned_msgs])
    
    # Run UI data expert (without keys, so it falls back)
    print("--- 1. Running _run_ui_data_expert (expecting fail/fallback) ---")
    ui_data = await service._run_ui_data_expert(symbol, market, snapshot, full_discussion)
    print("ui_data returned:", ui_data)
    
    # Run complete generate_html_report_async pipeline
    print("\n--- 2. Running generate_html_report_async ---")
    out_path = '/home/ubuntu/work/alsa/scratch/debug_report.html'
    res_path = await service.generate_html_report_async(job_data, out_path)
    print("Report generated at:", res_path)

if __name__ == '__main__':
    asyncio.run(main())
