import json
import asyncio
import uuid
from ..db.repositories.job_repo import JobRepository
from .market_snapshot_service import MarketSnapshotService
from ..quant.polars_indicators import compute_indicator_frame

class AnalysisJobService:
    def __init__(self, job_repo: JobRepository, snapshot_service: MarketSnapshotService):
        self.job_repo = job_repo
        self.snapshot_service = snapshot_service

    async def start_job(self, symbol: str, market: str) -> str:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        self.job_repo.create(job_id, symbol, market)
        
        # Fire and forget the background task
        asyncio.create_task(self._run_job(job_id, symbol, market))
        return job_id

    async def _run_job(self, job_id: str, symbol: str, market: str):
        self.job_repo.update_status(job_id, "running")
        try:
            # 1. Create snapshot (saves to Parquet)
            snapshot = await self.snapshot_service.create_snapshot(market, symbol)
            if not snapshot:
                raise ValueError("Failed to fetch market data")
            
            # 2. Compute quantitative factors using Polars
            indicator_df = compute_indicator_frame(snapshot["history"])
            indicators = indicator_df.tail(1).to_dicts()[0]
            
            # 3. Final Payload
            result = {
                "symbol": symbol,
                "market": market,
                "indicators": indicators,
                "valuation": snapshot["valuation"]
            }
            
            self.job_repo.update_status(job_id, "completed", json.dumps(result))
        except Exception as e:
            print(f"Analysis job {job_id} failed: {e}")
            self.job_repo.update_status(job_id, "failed", json.dumps({"error": str(e)}))

    def get_status(self, job_id: str):
        return self.job_repo.get_by_id(job_id)
