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
            snapshot["market"] = market
            
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
            # 4. Final Payload — enrich stockInfo with quote data for Flash UI
            quote = snapshot.get("quote", {})
            from datetime import datetime as _dt
            result = {
                "stockInfo": {
                    "symbol": symbol,
                    "market": market,
                    "name": snapshot.get("name", symbol),
                    "price": quote.get("price") or snapshot.get("price"),
                    "change": quote.get("change"),
                    "changePercent": quote.get("changePercent") or snapshot.get("changePercent"),
                    "currency": quote.get("currency") or snapshot.get("currency", "CNY" if market == "A-Share" else "USD"),
                    "previousClose": quote.get("previousClose"),
                    "marketCap": quote.get("marketCap"),
                    "pe": quote.get("trailingPE"),
                    "forwardPE": quote.get("forwardPE"),
                    "pb": quote.get("priceToBook"),
                    "dividendYield": quote.get("dividendYield"),
                    "lastUpdated": _dt.now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
                },
                "technicals": indicators,
                "valuation": snapshot.get("valuation"),
                "financials": snapshot.get("financials"),
                "snapshot": snapshot,
                "discussion": discussion_messages,
                "summary": self._extract_summary(discussion_messages),
            }
            
            # Extract structured fields for Flash UI (sentiment, recommendation, risks, etc.)
            structured = self._extract_structured_fields(discussion_messages)
            result.update(structured)
            
            # 5. Create Analysis Run and Update Job
            with self.job_repo.session_factory() as session:
                # Derive verdict from structured extraction
                rec = structured.get("recommendation", "Hold")
                if rec in ("Buy",): verdict = "buy"
                elif rec in ("Overweight",): verdict = "buy"
                elif rec in ("Sell",): verdict = "sell"
                elif rec in ("Underweight",): verdict = "sell"
                else: verdict = "watch"
                
                run_score = float(structured.get("score", 70.0))
                
                analysis_run = AnalysisRun(
                    job_id=job_id,
                    symbol=symbol,
                    market=market,
                    summary_verdict=verdict,
                    score=run_score,
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
        
        quote = snapshot.get("quote", {})
        from datetime import datetime as _dt
        result = {
            "stockInfo": {
                "symbol": symbol,
                "market": market,
                "name": snapshot.get("name", symbol),
                "price": quote.get("price") or snapshot.get("price"),
                "change": quote.get("change"),
                "changePercent": quote.get("changePercent") or snapshot.get("changePercent"),
                "currency": quote.get("currency") or snapshot.get("currency", "CNY" if market == "A-Share" else "USD"),
                "lastUpdated": _dt.now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
            },
            "technicals": indicators,
            "valuation": snapshot.get("valuation"),
            "financials": snapshot.get("financials"),
            "snapshot": snapshot,
            "discussion": valid_messages,
            "summary": self._extract_summary(valid_messages),
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

    @staticmethod
    def _extract_summary(discussion_messages: List[Dict[str, Any]]) -> str:
        """Extract a short summary from the Chief Strategist (last) message."""
        if not discussion_messages:
            return ""
        last = discussion_messages[-1]
        content = last.get("content", "")
        # Try to find a tagline or thesis section
        for marker in ["Tagline", "Investment Thesis", "核心摘要", "核心结论"]:
            idx = content.find(marker)
            if idx != -1:
                # Grab the paragraph after the marker
                block = content[idx:idx + 600]
                lines = [l.strip() for l in block.split("\n") if l.strip() and not l.strip().startswith("#")]
                # Skip the marker line itself, take up to 3 lines
                useful = [l for l in lines[1:4] if l and not l.startswith("|") and not l.startswith("---")]
                if useful:
                    return " ".join(useful)[:400]
        # Fallback: first non-heading paragraph
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("|") and not stripped.startswith("---") and len(stripped) > 30:
                return stripped[:400]
        return ""

    @staticmethod
    def _extract_structured_fields(discussion_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract structured analysis fields from the Chief Strategist's output for Flash UI."""
        import re
        fields: Dict[str, Any] = {}
        
        # Find expert messages by role
        chief_content = ""
        technical_content = ""
        fundamental_content = ""
        for msg in discussion_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "Chief Strategist" and content:
                chief_content = content
            elif role == "Technical Analyst" and content and not technical_content:
                technical_content = content
            elif role == "Fundamental Analyst" and content and not fundamental_content:
                fundamental_content = content
        
        # Populate technicalAnalysis and fundamentalAnalysis from expert messages
        if technical_content:
            fields["technicalAnalysis"] = technical_content[:2000]
        if fundamental_content:
            fields["fundamentalAnalysis"] = fundamental_content[:2000]
        
        if not chief_content:
            return fields
        
        # --- Sentiment & Recommendation ---
        # Extract from the verdict/final section table (most reliable)
        sentiment = "Neutral"
        recommendation = "Hold"
        
        # Find rating text from structured table rows
        rating_text = ""
        rating_patterns = [
            r'投资评级[^|]*\|\s*\*{0,2}([^*|\n]+)',   # Table: | 投资评级 | **value** |
            r'投资评级[：:]\s*\*{0,2}([^*\n]{3,80})',  # Inline: 投资评级: value
        ]
        for pat in rating_patterns:
            m = re.search(pat, chief_content)
            if m:
                rating_text = m.group(1).strip().strip('*').strip()
                break
        
        # Map rating text to sentiment/recommendation (check rating_text first, then broader context)
        if rating_text:
            rt = rating_text
            # Check cautious/hold FIRST (more specific: "谨慎观望" contains chars that overlap with bullish terms)
            if any(kw in rt for kw in ["谨慎观望", "观望", "Cautious Hold", "中性偏谨慎", "中性"]):
                sentiment, recommendation = "Neutral", "Hold"
            elif any(kw in rt for kw in ["持有", "Hold"]):
                sentiment, recommendation = "Neutral", "Hold"
            elif any(kw in rt for kw in ["强烈买入", "Strong Buy", "积极买入"]):
                sentiment, recommendation = "Bullish", "Buy"
            elif any(kw in rt for kw in ["买入", "Buy"]):
                sentiment, recommendation = "Bullish", "Buy"
            elif any(kw in rt for kw in ["增持", "Accumulate", "条件性增持", "Overweight"]):
                sentiment, recommendation = "Bullish", "Overweight"
            elif any(kw in rt for kw in ["强烈卖出", "Strong Sell"]):
                sentiment, recommendation = "Bearish", "Sell"
            elif any(kw in rt for kw in ["卖出", "Sell"]):
                sentiment, recommendation = "Bearish", "Sell"
            elif any(kw in rt for kw in ["减持", "Underweight"]):
                sentiment, recommendation = "Bearish", "Underweight"
        else:
            # Fallback: search the final verdict section (last 20% of content)
            tail = chief_content[int(len(chief_content) * 0.8):]
            if any(kw in tail for kw in ["强烈买入", "积极增持"]):
                sentiment, recommendation = "Bullish", "Buy"
            elif any(kw in tail for kw in ["增持", "条件性增持", "Overweight", "Accumulate"]):
                sentiment, recommendation = "Bullish", "Overweight"
            elif any(kw in tail for kw in ["谨慎观望", "观望", "Cautious Hold", "中性"]):
                sentiment, recommendation = "Neutral", "Hold"
            elif any(kw in tail for kw in ["减持", "Underweight"]):
                sentiment, recommendation = "Bearish", "Underweight"
        
        fields["sentiment"] = sentiment
        fields["recommendation"] = recommendation
        
        # --- Key Risks ---
        risks = []
        # Extract from verdict table (核心风险 row)
        risk_table = re.search(r'核心风险[^|]*\|\s*\*{0,2}([^*|\n]+)', chief_content)
        if risk_table:
            risk_text = risk_table.group(1).strip().strip('*').strip()
            if risk_text and len(risk_text) > 5:
                risks.append(risk_text)
        
        # Extract from 证伪/退出条件 section
        falsify_section = re.search(r'(?:证伪条件|论点证伪|退出条件)[^\n]*\n((?:.*\n){1,20})', chief_content)
        if falsify_section:
            for line in falsify_section.group(1).split('\n'):
                # Parse table rows
                cells = [c.strip() for c in line.split('|') if c.strip()]
                if len(cells) >= 2:
                    cell0 = cells[0].strip('*- ')
                    if cell0 and not cell0.startswith('---') and cell0 not in ('证伪条件', '审查项', '条件', '止损类型', '止盈条件'):
                        item = f"{cell0}: {cells[1].strip('*- ')}" if cells[1].strip('*- ') else cell0
                        if len(item) > 5 and item not in risks:
                            risks.append(item[:120])
                if len(risks) >= 6:
                    break
        
        # Extract ⚠️ warnings but only from relevant sections (not generic disclaimers)
        warning_section = re.findall(r'⚠️\s*\*{0,2}([^*\n]{10,100})\*{0,2}', chief_content)
        for w in warning_section[:3]:
            clean = w.strip().strip('*').strip()
            if clean and '免责' not in clean and '声明' not in clean and clean not in risks:
                risks.append(clean)
        
        if risks:
            fields["keyRisks"] = risks[:8]
        
        # --- Key Opportunities ---
        opps = []
        # From verdict table
        opp_table = re.search(r'核心机会[^|]*\|\s*\*{0,2}([^*|\n]+)', chief_content)
        if opp_table:
            opp_text = opp_table.group(1).strip().strip('*').strip()
            if opp_text and len(opp_text) > 5:
                opps.append(opp_text)
        
        # Extract named insights (洞察1:, 洞察2:, etc.)
        insight_matches = re.findall(r'\*{0,2}洞察\d+[：:]\s*(.+?)\*{0,2}\s*$', chief_content, re.MULTILINE)
        for insight in insight_matches:
            clean = insight.strip().strip('*').strip()
            if clean and len(clean) > 5 and clean not in opps:
                opps.append(clean[:120])
        
        # Non-consensus insights section header
        nci_match = re.search(r'非共识洞察[^：:\n]*[：:]?\s*(.+?)(?:\n|$)', chief_content)
        if nci_match:
            nci = nci_match.group(1).strip().strip('*').strip()
            if nci and len(nci) > 5 and nci not in opps:
                opps.append(nci[:120])
        
        if opps:
            fields["keyOpportunities"] = opps[:8]
        
        # --- Trading Plan ---
        trading_plan = {}
        
        # Extract from verdict table rows (most structured)
        strategy_table = re.search(r'核心策略[^|]*\|\s*\*{0,2}([^*|\n]+)', chief_content)
        if strategy_table:
            trading_plan["strategy"] = strategy_table.group(1).strip().strip('*')[:200]
        
        # Expected/target price from calculation
        exp_price = re.search(r'期望价格[^=]*=\s*\*{0,2}([\d.,]+\s*(?:CNY|USD|HKD|元)?)', chief_content)
        if exp_price:
            trading_plan["targetPrice"] = exp_price.group(1).strip()
        else:
            # From scenario table (基准 target)
            base_target = re.search(r'基准.*?\|\s*([\d.,]+(?:\s*(?:CNY|USD|HKD))?)', chief_content)
            if base_target:
                trading_plan["targetPrice"] = base_target.group(1).strip()
        
        # Entry price from strategy description
        entry = re.search(r'(?:回撤至|跌至|跌破|低于)\s*\*{0,2}([\d.,]+(?:\s*(?:CNY|USD|HKD|元))?(?:\s*(?:以下|附近|左右))?)', chief_content)
        if entry:
            trading_plan["entryPrice"] = entry.group(1).strip()
        
        # Stop loss - price-based
        stop = re.search(r'(?:硬止损|价格.*?止损|收盘价\s*[<＜])\s*\*{0,2}([\d.,]+(?:\s*(?:CNY|USD|HKD|元))?)', chief_content)
        if stop:
            trading_plan["stopLoss"] = stop.group(1).strip()
        
        # Logic stop loss
        logic_stop = re.search(r'逻辑止损[^|]*\|\s*\*{0,2}([^*|\n]{5,80})', chief_content)
        if logic_stop:
            ls = logic_stop.group(1).strip().strip('*').strip()
            if trading_plan.get("stopLoss"):
                trading_plan["stopLoss"] += f" / {ls}"
            else:
                trading_plan["stopLoss"] = ls
        
        # Position size
        pos_match = re.search(r'(?:建议.*?仓位|最大.*?仓位)[：:]\s*\*{0,2}([\d.]+%[^*\n]{0,40})', chief_content)
        if pos_match:
            if trading_plan.get("strategy"):
                trading_plan["strategy"] += f"（仓位: {pos_match.group(1).strip()}）"
            else:
                trading_plan["strategy"] = f"建议仓位: {pos_match.group(1).strip()}"

        # Strategy risks from 最大警告
        warning_match = re.search(r'最大警告[^|]*\|\s*\*{0,2}([^*|\n]+)', chief_content)
        if warning_match:
            trading_plan["strategyRisks"] = warning_match.group(1).strip().strip('*')[:200]
        
        if trading_plan:
            fields["tradingPlan"] = trading_plan
        
        # --- Score estimation from content ---
        # Look for explicit confidence/score mentions
        score_patterns = [
            r'综合可信度\s*[:：]?\s*(\d+)\s*/\s*100',
            r'信心[评分度]\s*[:：]?\s*(\d+)',
            r'评分\s*[:：]?\s*(\d+)\s*/\s*100',
        ]
        for pat in score_patterns:
            m = re.search(pat, chief_content)
            if m:
                try:
                    fields["score"] = min(100, max(0, int(m.group(1))))
                except ValueError:
                    pass
                break
        
        return fields

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
        
        # Backfill structured fields if missing (for older jobs)
        if "sentiment" not in result or "recommendation" not in result:
            discussion = result.get("discussion", [])
            if discussion:
                structured = self._extract_structured_fields(discussion)
                for k, v in structured.items():
                    if k not in result or result[k] is None:
                        result[k] = v
                # Also backfill summary
                if not result.get("summary"):
                    result["summary"] = self._extract_summary(discussion)
        
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
