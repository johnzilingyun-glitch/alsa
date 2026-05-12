import json
import asyncio
import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from ..db.repositories.job_repo import JobRepository
from .market_snapshot_service import MarketSnapshotService
from ..quant.polars_indicators import compute_indicator_frame

class AnalysisJobService:
    def __init__(self, job_repo: JobRepository, snapshot_service: MarketSnapshotService):
        self.job_repo = job_repo
        self.snapshot_service = snapshot_service
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._progress: Dict[str, Dict[str, Any]] = {}

    async def start_job(self, symbol: str, market: str, level: str = "standard", model: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> str:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        self.job_repo.create(job_id, symbol, market, level=level, model=model)
        
        # Fire and forget the background task
        task = asyncio.create_task(self._run_job(job_id, symbol, market, config=config))
        self._running_tasks[job_id] = task
        # Clean up task reference when done
        task.add_done_callback(lambda t: self._running_tasks.pop(job_id, None))
        
        return job_id

    async def _run_job(self, job_id: str, symbol: str, market: str, config: Optional[Dict[str, Any]] = None):
        from .discussion_service import discussion_service
        from ..db.models import AnalysisRun, AnalysisJob
        
        # Mark job as running in the database immediately
        self.job_repo.update_status(job_id, "running")
        self.update_job_progress(job_id, "snapshot", 10)
        try:
            # 1. Create snapshot (saves to Parquet)
            snapshot = await self.snapshot_service.create_snapshot(market, symbol)
            if not snapshot:
                raise ValueError("Failed to fetch market data")
            
            self.update_job_progress(job_id, "quant", 30)
            # 2. Compute quantitative factors using Polars
            indicator_df = compute_indicator_frame(snapshot["history"])
            indicators = indicator_df.tail(1).to_dicts()[0]
            snapshot["indicators"] = indicators
            
            self.update_job_progress(job_id, "discussion", 50)
            # 3. Run Expert Discussion
            job = self.job_repo.get_by_id(job_id)
            level = job.analysis_level if job else "standard"
            # Priority: job.requested_model > config.model > env default
            requested_model = job.requested_model if job else None
            if not requested_model and config:
                requested_model = config.get("model")
            
            def report_discussion_progress(round, total, msg, count=None, error_type=None):
                self.update_job_progress(job_id, "discussion", 50 + int((round/total) * 40), round=round, total_rounds=total, message=msg, count=count, error_type=error_type)

            discussion_messages = await discussion_service.run_discussion(
                symbol, 
                snapshot.get("name", symbol), 
                snapshot, 
                level=level,
                model=requested_model,
                on_progress=report_discussion_progress,
                job_id=job_id,
                config=config
            )
            
            self.update_job_progress(job_id, "finalizing", 90)
            # 4. Final Payload
            result = {
                "stockInfo": {
                    "symbol": symbol,
                    "market": market,
                    "name": snapshot.get("name", symbol),
                },
                "technicals": indicators,
                "valuation": snapshot.get("valuation"),
                "financials": snapshot.get("financials"),
                "snapshot": snapshot,
                "discussion": discussion_messages
            }
            
            # 5. Create Analysis Run and Update Job
            with self.job_repo.session_factory() as session:
                # Basic verdict logic
                last_msg = discussion_messages[-1]["content"] if discussion_messages else ""
                verdict = "watch"
                if "买入" in last_msg or "BUY" in last_msg.upper(): verdict = "buy"
                elif "卖出" in last_msg or "SELL" in last_msg.upper(): verdict = "sell"
                
                analysis_run = AnalysisRun(
                    job_id=job_id,
                    symbol=symbol,
                    market=market,
                    summary_verdict=verdict,
                    score=70.0,
                    risk_level="medium"
                )
                session.add(analysis_run)
                session.commit()
                session.refresh(analysis_run)
                
                # Update job
                db_job = session.get(AnalysisJob, job_id)
                if db_job:
                    db_job.status = "completed"
                    db_job.analysis_id = analysis_run.analysis_id
                    
                    def json_serial(obj):
                        if isinstance(obj, (datetime, date)):
                            return obj.isoformat()
                        raise TypeError(f"Type {type(obj)} not serializable")
                    
                    db_job.result_payload = json.dumps(result, default=json_serial)
                    db_job.finished_at = datetime.utcnow()
                    session.add(db_job)
                    session.commit()

        except asyncio.CancelledError:
            self.job_repo.update_status(job_id, "cancelled")
            raise
        except Exception as e:
            error_msg = str(e)
            # Check if this is a user-initiated stop — still save partial results
            if "stopped by user" in error_msg:
                print(f"Analysis job {job_id} stopped by user, saving partial results")
                try:
                    _msgs = locals().get("discussion_messages", [])
                    _snap = locals().get("snapshot", {})
                    _inds = locals().get("indicators", {})
                    if _snap:
                        await self._save_partial_results(job_id, symbol, market, _snap, _inds, _msgs)
                    else:
                        self.job_repo.update_status(job_id, "failed", json.dumps({"error": "Stopped before data was ready"}))
                except Exception as save_err:
                    print(f"Failed to save partial results: {save_err}")
                    self.job_repo.update_status(job_id, "failed", json.dumps({"error": error_msg}))
            else:
                print(f"Analysis job {job_id} failed: {e}")
                import traceback
                traceback.print_exc()
                self.job_repo.update_status(job_id, "failed", json.dumps({"error": error_msg}))

    async def _save_partial_results(self, job_id: str, symbol: str, market: str, snapshot: Dict[str, Any], indicators: Dict[str, Any], discussion_messages: List[Dict[str, Any]]):
        """Save partial results when analysis is interrupted (user abort or 402)."""
        from ..db.models import AnalysisRun, AnalysisJob
        
        # Filter out empty messages
        valid_messages = [m for m in discussion_messages if m.get("content")]
        
        self.update_job_progress(job_id, "finalizing", 90, message="正在保存已获取的部分内容...")
        
        result = {
            "stockInfo": {
                "symbol": symbol,
                "market": market,
                "name": snapshot.get("name", symbol),
            },
            "technicals": indicators,
            "valuation": snapshot.get("valuation"),
            "financials": snapshot.get("financials"),
            "snapshot": snapshot,
            "discussion": valid_messages,
            "partial": True  # Flag indicating partial results
        }
        
        with self.job_repo.session_factory() as session:
            last_msg = valid_messages[-1]["content"] if valid_messages else ""
            verdict = "watch"
            if "买入" in last_msg or "BUY" in last_msg.upper(): verdict = "buy"
            elif "卖出" in last_msg or "SELL" in last_msg.upper(): verdict = "sell"
            
            analysis_run = AnalysisRun(
                job_id=job_id,
                symbol=symbol,
                market=market,
                summary_verdict=verdict,
                score=50.0,  # Lower score for partial
                risk_level="medium"
            )
            session.add(analysis_run)
            session.commit()
            session.refresh(analysis_run)
            
            db_job = session.get(AnalysisJob, job_id)
            if db_job:
                db_job.status = "completed"
                db_job.analysis_id = analysis_run.analysis_id
                
                def json_serial(obj):
                    if isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")
                
                db_job.result_payload = json.dumps(result, default=json_serial)
                db_job.finished_at = datetime.utcnow()
                session.add(db_job)
                session.commit()
        
        print(f"Partial results saved for job {job_id}: {len(valid_messages)} expert messages")

    def update_job_progress(self, job_id: str, stage: str, percent: int, round: Optional[int] = None, total_rounds: Optional[int] = None, message: Optional[str] = None, count: Optional[int] = None, error_type: Optional[str] = None):
        prev = self._progress.get(job_id, {})
        self._progress[job_id] = {
            "stage": stage, 
            "percent": percent,
            "round": round,
            "total_rounds": total_rounds,
            "message": message,
            "count": count if count is not None else prev.get("count"),
            "error_type": error_type or prev.get("error_type")
        }

    def get_status(self, job_id: str):
        job = self.job_repo.get_by_id(job_id)
        return job

    def get_analysis_run(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        run = self.job_repo.get_analysis_run(analysis_id)
        if not run:
            return None
        
        job = self.job_repo.get_by_id(run.job_id)
        if not job or not job.result_payload:
            return run.dict()
            
        result = json.loads(job.result_payload)
        result["analysis_id"] = run.analysis_id
        result["summary_verdict"] = run.summary_verdict
        result["score"] = run.score
        result["risk_level"] = run.risk_level
        return result

    async def cancel_job(self, job_id: str) -> bool:
        task = self._running_tasks.get(job_id)
        if task:
            task.cancel()
            return True
        
        job = self.job_repo.get_by_id(job_id)
        if job and job.status in ["queued", "running"]:
            self.job_repo.update_status(job_id, "cancelled")
            return True
        return False

    def recover_orphaned_jobs(self) -> int:
        """On startup, mark any queued/running jobs as failed.
        
        These jobs lost their in-memory asyncio tasks due to a process restart.
        Returns the count of recovered jobs.
        """
        count = self.job_repo.recover_orphaned_jobs()
        if count > 0:
            print(f"[Startup Recovery] Marked {count} orphaned job(s) as failed.")
        return count

    async def retry_job(self, job_id: str, config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Re-submit a failed/cancelled job with the same parameters.
        
        Returns the new job_id, or None if the original job was not found
        or is not in a retryable state.
        """
        job = self.job_repo.get_by_id(job_id)
        if not job or job.status not in ["failed", "cancelled"]:
            return None
        
        return await self.start_job(
            symbol=job.symbol,
            market=job.market,
            level=job.analysis_level,
            model=job.requested_model,
            config=config
        )
