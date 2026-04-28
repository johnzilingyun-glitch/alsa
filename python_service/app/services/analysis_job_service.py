import json
import asyncio
import uuid
from datetime import datetime, date
from ..db.repositories.job_repo import JobRepository
from .market_snapshot_service import MarketSnapshotService
from ..quant.polars_indicators import compute_indicator_frame

class AnalysisJobService:
    def __init__(self, job_repo: JobRepository, snapshot_service: MarketSnapshotService):
        self.job_repo = job_repo
        self.snapshot_service = snapshot_service

    async def start_job(self, symbol: str, market: str, level: str = "standard") -> str:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        with self.job_repo.session_factory() as session:
            from ..db.models import AnalysisJob
            job = AnalysisJob(
                job_id=job_id,
                symbol=symbol,
                market=market,
                analysis_level=level,
                status="queued"
            )
            session.add(job)
            session.commit()
        
        # Fire and forget the background task
        asyncio.create_task(self._run_job(job_id, symbol, market))
        return job_id

    async def _run_job(self, job_id: str, symbol: str, market: str):
        from .discussion_service import discussion_service
        from ..db.models import AnalysisRun
        
        self.job_repo.update_status(job_id, "running")
        try:
            # 1. Create snapshot (saves to Parquet)
            snapshot = await self.snapshot_service.create_snapshot(market, symbol)
            if not snapshot:
                raise ValueError("Failed to fetch market data")
            
            # 2. Compute quantitative factors using Polars
            indicator_df = compute_indicator_frame(snapshot["history"])
            indicators = indicator_df.tail(1).to_dicts()[0]
            snapshot["indicators"] = indicators
            
            # 3. Run Expert Discussion
            job = self.job_repo.get_by_id(job_id)
            level = job.analysis_level if job else "standard"
            discussion_messages = await discussion_service.run_discussion(symbol, snapshot.get("name", symbol), snapshot, level=level)
            
            # 4. Final Payload
            result = {
                "symbol": symbol,
                "market": market,
                "indicators": indicators,
                "valuation": snapshot.get("valuation"),
                "financials": snapshot.get("financials"),
                "snapshot": snapshot,
                "discussion": discussion_messages
            }
            
            # 5. Create Analysis Run and Update Job
            with self.job_repo.session_factory() as session:
                # Basic verdict logic (can be more complex)
                last_msg = discussion_messages[-1]["content"] if discussion_messages else ""
                verdict = "watch"
                if "买入" in last_msg or "BUY" in last_msg.upper(): verdict = "buy"
                elif "卖出" in last_msg or "SELL" in last_msg.upper(): verdict = "sell"
                
                analysis_run = AnalysisRun(
                    job_id=job_id,
                    symbol=symbol,
                    market=market,
                    summary_verdict=verdict,
                    score=70.0, # Placeholder
                    risk_level="medium"
                )
                session.add(analysis_run)
                session.commit()
                session.refresh(analysis_run)
                
                # Update job
                from ..db.models import AnalysisJob
                db_job = session.get(AnalysisJob, job_id)
                if db_job:
                    db_job.status = "completed"
                    db_job.analysis_id = analysis_run.analysis_id
                    
                    # Fix JSON serialization for date/datetime objects
                    def json_serial(obj):
                        if isinstance(obj, (datetime, date)):
                            return obj.isoformat()
                        raise TypeError(f"Type {type(obj)} not serializable")
                    
                    db_job.result_payload = json.dumps(result, default=json_serial)
                    db_job.finished_at = datetime.utcnow()
                    session.add(db_job)
                    session.commit()

        except Exception as e:
            print(f"Analysis job {job_id} failed: {e}")
            import traceback
            traceback.print_exc()
            self.job_repo.update_status(job_id, "failed", json.dumps({"error": str(e)}))

    def get_status(self, job_id: str):
        return self.job_repo.get_by_id(job_id)
