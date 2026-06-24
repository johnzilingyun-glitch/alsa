import asyncio
from app.services.sector_analysis_service import SectorAnalysisService
from app.db.database import init_db

class DummyRepo:
    def create(self, *args, **kwargs): pass
    def update_status(self, *args, **kwargs): pass
    def get_by_id(self, *args, **kwargs): return None
    def session_factory(self):
        class DummySession:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def add(self, *args): pass
            def commit(self): pass
            def refresh(self, *args): pass
            def get(self, *args, **kwargs): return None
        return DummySession()

async def main():
    init_db()
    service = SectorAnalysisService(DummyRepo())
    print("Starting job directly...")
    await service._run_sector_job(
        job_id="test_job",
        sector_name="A股市场",
        model="gemini-3.5-flash",
        config={},
        target_date=None,
        level="sector"
    )
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
