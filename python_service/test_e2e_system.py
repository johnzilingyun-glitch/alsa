import asyncio
import os
import sys

# Set environment variables for testing
os.environ["DATABASE_URL"] = "sqlite:///alsa_db.sqlite"
# Force local asyncio fallback mode instead of Redis/Celery to test our async handling
os.environ["REDIS_URL"] = ""

sys.path.append(os.path.dirname(__file__))

async def main():
    try:
        from main import get_analysis_job_service
        analysis_job_service = get_analysis_job_service()
        from app.db.database import engine
        from sqlmodel import SQLModel
        
        # Ensure database tables exist
        SQLModel.metadata.create_all(engine)
        
        print("Starting e2e test for Analysis Job...")
        # Start a quick standard job for AAPL
        # Using a fake/small config to bypass heavy LLM tasks if we just want to test pipeline
        job_id = await analysis_job_service.start_job(
            symbol="AAPL", 
            market="us", 
            level="standard", 
            model="gemini-3.1-pro-preview", 
            config={"geminiApiKey": "mock_key_for_test_if_needed"}
        )
        print(f"Job started with ID: {job_id}")
        
        # Wait and poll for completion
        for _ in range(30):
            status = analysis_job_service.get_job_status(job_id)
            print(f"Status: {status.get('status')}")
            if status.get("status") in ["completed", "failed"]:
                print(f"Job finished with status: {status.get('status')}")
                # Print sample of the result
                payload = status.get("result_payload")
                if payload:
                    print("SUCCESS! Got result payload from DB (JSON parsed):")
                    print(str(payload)[:500] + "...")
                else:
                    if status.get("status") == "failed":
                        print(f"Job failed with error: {status.get('error')}")
                    else:
                        print("WARNING: Job completed but no payload found.")
                break
            await asyncio.sleep(2)
        else:
            print("TIMEOUT waiting for job completion.")
            
    except Exception as e:
        print(f"Exception during e2e test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
