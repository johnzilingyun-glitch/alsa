import asyncio
import uuid
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

from .sector_analysis_service import SectorAnalysisService
from .discussion_service import discussion_service

class SerenityGraphService(SectorAnalysisService):
    """Development AI Pipeline using LangGraph to orchestrate the entire workflow."""

    async def start_sector_job(
        self,
        sector_name: str,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        target_date: Optional[str] = None,
        level: str = "sector",
        verification_mode: str = "quick"
    ) -> str:
        import os
        job_id = f"graph_{uuid.uuid4().hex[:8]}"
        # Create job in DB
        self.job_repo.create(job_id, sector_name, "sector", level=level, model=model, snapshot_id=target_date)

        if os.getenv("ALSA_DISABLE_BACKGROUND_JOBS") == "true" or os.getenv("PYTEST_CURRENT_TEST"):
            return job_id

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from app.worker import run_sector_analysis_task
            print(f"[SerenityGraph] Dispatching development serenity job {job_id} to Celery worker")
            run_sector_analysis_task.delay(
                job_id,
                sector_name,
                model=model,
                config=config,
                target_date=target_date,
                level=level,
                pipeline_version="development",
                verification_mode=verification_mode
            )
        else:
            print(f"[SerenityGraph] Running development serenity job {job_id} in local asyncio pool (Graceful Degradation)")
            task = asyncio.create_task(self._run_sector_job(job_id, sector_name, model=model, config=config, target_date=target_date, level=level, verification_mode=verification_mode))
            self._running_tasks[job_id] = task
            task.add_done_callback(lambda t: self._running_tasks.pop(job_id, None))
        return job_id

    async def _run_sector_job(
        self,
        job_id: str,
        sector_name: str,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        target_date: Optional[str] = None,
        level: str = "sector",
        verification_mode: str = "quick"
    ):
        class GraphState(TypedDict):
            job_id: str
            sector_name: str
            model: Optional[str]
            config: Optional[dict]
            target_date: Optional[str]
            level: str
            snapshot: Optional[dict]
            discussion: Optional[list]
            critique: Optional[dict]
            result: Optional[dict]
            error: Optional[str]

        # Define graph node functions
        async def build_snapshot_node(state: GraphState):
            self.job_repo.update_status(state["job_id"], "running")
            await self.update_progress_async(state["job_id"], "sector_snapshot", 10)
            
            snapshot = await self._build_sector_snapshot(state["sector_name"])
            try:
                sector_stocks = await self._fetch_sector_stocks(state["sector_name"])
                if sector_stocks:
                    snapshot["sector_stocks"] = sector_stocks
                    print(f"[SerenityGraph] Pre-enriched snapshot with {len(sector_stocks)} stocks")
            except Exception as e:
                print(f"[SerenityGraph] Sector stock pre-enrichment failed (non-fatal): {e}")
                
            return {"snapshot": snapshot}

        async def run_discussion_node(state: GraphState):
            await self.update_progress_async(state["job_id"], "discussion", 30, message="正在进行多智能体板块研讨...")
            
            def report_progress(round_num, total, msg, count=None, error_type=None, **kwargs):
                if round_num == 0:
                    self.update_progress(state["job_id"], "discussion", 32,
                                         round=0, total_rounds=total, message=msg,
                                         count=count, error_type=error_type, **kwargs)
                else:
                    self.update_progress(state["job_id"], "discussion", 35 + int((round_num / total) * 40),
                                         round=round_num, total_rounds=total, message=msg,
                                         count=count, error_type=error_type, **kwargs)

            discussion_messages = await discussion_service.run_discussion(
                state["sector_name"],
                state["sector_name"],
                state["snapshot"],
                level=state["level"],
                model=state["model"],
                on_progress=report_progress,
                job_id=state["job_id"],
                config=state["config"],
                verification_mode=verification_mode
            )
            return {"discussion": discussion_messages}

        async def run_critique_node(state: GraphState):
            await self.update_progress_async(state["job_id"], "discussion", 80, message="正在由评审委员会进行报告审计...")
            critique_res = None
            try:
                from app.services.critic_agent import critic_agent
                critique_res = await critic_agent.critique(
                    analyses=state["discussion"],
                    symbol=state["sector_name"],
                    name=f"{state['sector_name']}板块",
                    context=state["snapshot"],
                    gemini_api_key=state["config"].get("geminiApiKey") if state["config"] else None,
                    deepseek_api_key=state["config"].get("deepseekApiKey") if state["config"] else None,
                    model=state["model"]
                )
            except Exception as e:
                print(f"[SerenityGraph] Critic Agent critique failed: {e}")
            return {"critique": critique_res}

        async def save_results_node(state: GraphState):
            await self.update_progress_async(state["job_id"], "finalizing", 90, message="正在生成和保存最终研究报告...")
            
            from ..db.models import AnalysisRun, AnalysisJob
            
            result = {
                "symbol": state["sector_name"],
                "market": "sector",
                "job_type": "sector",
                "stockInfo": {
                    "symbol": state["sector_name"],
                    "market": "sector",
                    "name": f"{state['sector_name']}板块分析",
                    "lastUpdated": datetime.now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
                },
                "snapshot": state["snapshot"],
                "discussion": state["discussion"],
                "critique": state["critique"],
                "summary": self._extract_summary(state["discussion"]),
            }

            try:
                result = await self._enrich_result_with_prices(result)
            except Exception as e:
                print(f"[SerenityGraph] Price enrichment failed (non-fatal): {e}")

            # Save to DB
            with self.job_repo.session_factory() as session:
                analysis_run = AnalysisRun(
                    job_id=state["job_id"],
                    symbol=state["sector_name"],
                    market="sector",
                    summary_verdict="watch",
                    score=70.0,
                    risk_level="medium"
                )
                session.add(analysis_run)
                session.commit()
                session.refresh(analysis_run)

                db_job = session.get(AnalysisJob, state["job_id"])
                if db_job:
                    db_job.status = "completed"
                    db_job.analysis_id = analysis_run.analysis_id
                    if state["target_date"]:
                        db_job.snapshot_id = state["target_date"]
                    db_job.result_payload = result
                    db_job.finished_at = datetime.now()
                    session.add(db_job)
                    session.commit()

            await self.update_progress_async(state["job_id"], "completed", 100, message="研讨完成，报告已生成。")
            return {"result": result}

        # Build Graph State Machine
        builder = StateGraph(GraphState)
        builder.add_node("build_snapshot", build_snapshot_node)
        builder.add_node("run_discussion", run_discussion_node)
        builder.add_node("run_critique", run_critique_node)
        builder.add_node("save_results", save_results_node)

        builder.add_edge(START, "build_snapshot")
        builder.add_edge("build_snapshot", "run_discussion")
        builder.add_edge("run_discussion", "run_critique")
        builder.add_edge("run_critique", "save_results")
        builder.add_edge("save_results", END)

        graph = builder.compile()

        # Initialize State
        initial_state = {
            "job_id": job_id,
            "sector_name": sector_name,
            "model": model,
            "config": config,
            "target_date": target_date,
            "level": level,
            "snapshot": None,
            "discussion": None,
            "critique": None,
            "result": None,
            "error": None
        }

        try:
            await graph.ainvoke(initial_state)
        except asyncio.CancelledError:
            self.job_repo.update_status(job_id, "cancelled")
            raise
        except Exception as e:
            traceback.print_exc()
            self.job_repo.update_status(job_id, "failed", error_message=str(e))
