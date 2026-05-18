"""
Sector Analysis Service — POC
Orchestrates sector-level multi-expert analysis flow.
"""
import json
import asyncio
import re
import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any, List


class SectorAnalysisService:
    """Manages sector-level analysis jobs: snapshot → discussion → report."""

    def __init__(self, job_repo):
        self.job_repo = job_repo
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._progress: Dict[str, Dict[str, Any]] = {}
        self._results: Dict[str, Dict[str, Any]] = {}

    async def start_sector_job(self, sector_name: str, model: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> str:
        job_id = f"sector_{uuid.uuid4().hex[:8]}"
        # Create job in DB
        self.job_repo.create(job_id, sector_name, "sector", level="sector", model=model)

        task = asyncio.create_task(self._run_sector_job(job_id, sector_name, model=model, config=config))
        self._running_tasks[job_id] = task
        task.add_done_callback(lambda t: self._running_tasks.pop(job_id, None))
        return job_id

    def update_progress(self, job_id: str, stage: str, pct: int, **kwargs):
        self._progress[job_id] = {"stage": stage, "progress": pct, **kwargs}

    def get_progress(self, job_id: str) -> Dict[str, Any]:
        return self._progress.get(job_id, {})

    async def _run_sector_job(self, job_id: str, sector_name: str, model: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        from .discussion_service import discussion_service
        from ..db.models import AnalysisRun, AnalysisJob

        self.job_repo.update_status(job_id, "running")
        self.update_progress(job_id, "sector_snapshot", 10)

        try:
            # 1. Build sector snapshot (lightweight — no per-stock data fetching)
            snapshot = await self._build_sector_snapshot(sector_name)

            # 1.5 Pre-enrich snapshot with sector constituent stocks + real-time prices
            try:
                sector_stocks = await self._fetch_sector_stocks(sector_name)
                if sector_stocks:
                    snapshot["sector_stocks"] = sector_stocks
                    print(f"[SectorAnalysis] Pre-enriched snapshot with {len(sector_stocks)} sector stocks")
            except Exception as e:
                print(f"[SectorAnalysis] Sector stock pre-enrichment failed (non-fatal): {e}")

            self.update_progress(job_id, "discussion", 30)

            # 2. Run sector expert discussion
            job = self.job_repo.get_by_id(job_id)
            requested_model = model
            if not requested_model and job:
                requested_model = job.requested_model

            def report_progress(round_num, total, msg, count=None, error_type=None):
                self.update_progress(job_id, "discussion", 30 + int((round_num / total) * 55),
                                     round=round_num, total_rounds=total, message=msg,
                                     count=count, error_type=error_type)

            discussion_messages = await discussion_service.run_discussion(
                sector_name,           # symbol → sector_name
                sector_name,           # name → sector_name
                snapshot,
                level="sector",        # triggers SECTOR_TOPOLOGY
                model=requested_model,
                on_progress=report_progress,
                job_id=job_id,
                config=config
            )

            self.update_progress(job_id, "finalizing", 90)

            # 3. Build result payload
            result = {
                "symbol": sector_name,
                "market": "sector",
                "job_type": "sector",
                "stockInfo": {
                    "symbol": sector_name,
                    "market": "sector",
                    "name": f"{sector_name}板块分析",
                    "lastUpdated": datetime.now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
                },
                "snapshot": snapshot,
                "discussion": discussion_messages,
                "summary": self._extract_summary(discussion_messages),
            }

            # 3.5 Post-process: enrich result with verified real-time prices
            try:
                result = await self._enrich_result_with_prices(result)
            except Exception as e:
                print(f"[SectorAnalysis] Post-processing price enrichment failed (non-fatal): {e}")

            self._results[job_id] = result

            # 4. Save to DB
            with self.job_repo.session_factory() as session:
                analysis_run = AnalysisRun(
                    job_id=job_id,
                    symbol=sector_name,
                    market="sector",
                    summary_verdict="watch",
                    score=70.0,
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
                    db_job.finished_at = datetime.now()
                    session.add(db_job)
                    session.commit()

        except asyncio.CancelledError:
            self.job_repo.update_status(job_id, "cancelled")
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.job_repo.update_status(job_id, "failed", error_message=str(e))

    async def _build_sector_snapshot(self, sector_name: str) -> Dict[str, Any]:
        """Build a lightweight sector snapshot with macro + commodity data."""
        from .macro_service import macro_service

        snapshot = {
            "name": sector_name,
            "type": "sector",
            "timestamp": datetime.now().isoformat(),
        }

        # Fetch macro data
        try:
            fx_data = await macro_service.get_latest_fx()
            snapshot["fx"] = fx_data
        except Exception as e:
            print(f"FX fetch failed: {e}")

        # Fetch relevant commodity data based on sector name
        commodity_keywords = {
            "铝": ["Aluminum", "Alumina"],
            "锂": ["Lithium Carbonate"],
            "铜": ["Copper"],
            "钢": ["Crude Oil"],
            "能源": ["Crude Oil", "Methanol"],
            "化工": ["Crude Oil", "Methanol", "Polypropylene", "LLDPE"],
            "光伏": ["Silicon"],
            "半导体": ["Silicon"],
        }

        for keyword, commodities in commodity_keywords.items():
            if keyword in sector_name:
                try:
                    commodity_data = await macro_service.get_commodity_prices(commodities)
                    snapshot["commodities"] = commodity_data
                except Exception as e:
                    print(f"Commodity fetch failed: {e}")
                break

        # Fetch macro indicators
        try:
            macro_indicators = await macro_service.get_macro_indicators()
            snapshot["macro_indicators"] = macro_indicators
        except Exception as e:
            print(f"Macro indicators failed: {e}")

        return snapshot

    def _extract_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Extract summary from the last expert's output."""
        for msg in reversed(messages):
            content = msg.get("content", "")
            if content and len(content) > 100:
                # Take first 500 chars as summary
                return content[:500]
        return ""

    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._results.get(job_id)

    async def _fetch_sector_stocks(self, sector_name: str) -> List[Dict[str, Any]]:
        """Fetch constituent stocks for a sector with real-time prices from AkShare."""
        import akshare as ak
        from ..utils.network import safe_ak_call

        stocks = []
        try:
            # 1. Get all industry board names and find best match
            board_names_df = await safe_ak_call(ak.stock_board_industry_name_em)
            if board_names_df is not None and not board_names_df.empty:
                board_col = "板块名称" if "板块名称" in board_names_df.columns else board_names_df.columns[0]
                board_names = board_names_df[board_col].tolist()

                # Fuzzy match: find boards whose name overlaps with sector_name
                best_match = None
                best_score = 0
                for bn in board_names:
                    # Score by character overlap
                    common = sum(1 for c in sector_name if c in bn)
                    score = common / max(len(sector_name), 1)
                    if score > best_score and score >= 0.4:
                        best_score = score
                        best_match = bn

                if best_match:
                    print(f"[SectorAnalysis] Matched board: '{best_match}' for sector '{sector_name}' (score: {best_score:.2f})")
                    cons_df = await safe_ak_call(ak.stock_board_industry_cons_em, symbol=best_match)
                    if cons_df is not None and not cons_df.empty:
                        # Take top 20 by market cap or turnover
                        sort_col = None
                        for c in ["总市值", "成交额", "成交量"]:
                            if c in cons_df.columns:
                                sort_col = c
                                break
                        if sort_col:
                            cons_df = cons_df.sort_values(sort_col, ascending=False)

                        for _, row in cons_df.head(20).iterrows():
                            code = str(row.get("代码", "")).strip()
                            name = str(row.get("名称", "")).strip()
                            price = row.get("最新价")
                            change_pct = row.get("涨跌幅")
                            pe = row.get("市盈率-动态")
                            pb = row.get("市净率")
                            market_cap = row.get("总市值")
                            turnover = row.get("换手率")

                            if code and name and price is not None:
                                stock = {
                                    "code": code,
                                    "name": name,
                                    "price": float(price) if price else None,
                                    "change_pct": float(change_pct) if change_pct else None,
                                    "pe": float(pe) if pe else None,
                                    "pb": float(pb) if pb else None,
                                    "market_cap_yi": round(float(market_cap) / 1e8, 1) if market_cap else None,
                                    "turnover_pct": float(turnover) if turnover else None,
                                }
                                stocks.append(stock)
        except Exception as e:
            print(f"[SectorAnalysis] Failed to fetch sector stocks: {e}")

        # Fallback: try concept board if industry board gave no results
        if not stocks:
            try:
                concept_df = await safe_ak_call(ak.stock_board_concept_name_em)
                if concept_df is not None and not concept_df.empty:
                    concept_col = "板块名称" if "板块名称" in concept_df.columns else concept_df.columns[0]
                    concept_names = concept_df[concept_col].tolist()

                    best_match = None
                    best_score = 0
                    for cn in concept_names:
                        common = sum(1 for c in sector_name if c in cn)
                        score = common / max(len(sector_name), 1)
                        if score > best_score and score >= 0.4:
                            best_score = score
                            best_match = cn

                    if best_match:
                        print(f"[SectorAnalysis] Matched concept board: '{best_match}' for sector '{sector_name}' (score: {best_score:.2f})")
                        cons_df = await safe_ak_call(ak.stock_board_concept_cons_em, symbol=best_match)
                        if cons_df is not None and not cons_df.empty:
                            sort_col = None
                            for c in ["总市值", "成交额", "成交量"]:
                                if c in cons_df.columns:
                                    sort_col = c
                                    break
                            if sort_col:
                                cons_df = cons_df.sort_values(sort_col, ascending=False)

                            for _, row in cons_df.head(20).iterrows():
                                code = str(row.get("代码", "")).strip()
                                name = str(row.get("名称", "")).strip()
                                price = row.get("最新价")
                                change_pct = row.get("涨跌幅")
                                pe = row.get("市盈率-动态")
                                pb = row.get("市净率")
                                market_cap = row.get("总市值")

                                if code and name and price is not None:
                                    stocks.append({
                                        "code": code,
                                        "name": name,
                                        "price": float(price) if price else None,
                                        "change_pct": float(change_pct) if change_pct else None,
                                        "pe": float(pe) if pe else None,
                                        "pb": float(pb) if pb else None,
                                        "market_cap_yi": round(float(market_cap) / 1e8, 1) if market_cap else None,
                                    })
            except Exception as e:
                print(f"[SectorAnalysis] Concept board fallback also failed: {e}")

        return stocks

    async def _enrich_result_with_prices(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract stock codes from discussion, fetch real-time prices, add to result."""
        import akshare as ak
        import yfinance as yf
        from ..utils.network import safe_ak_call

        discussion = result.get("discussion", [])
        all_text = " ".join(msg.get("content", "") for msg in discussion)

        # Extract 6-digit A-share stock codes
        codes = set(re.findall(r'\b(\d{6})\b', all_text))
        # Filter to valid A-share codes (starts with 0, 3, 6)
        valid_codes = [c for c in codes if c[0] in ('0', '3', '6')]

        if not valid_codes:
            return result

        print(f"[SectorAnalysis] Enriching {len(valid_codes)} stock codes with real-time prices...")

        realtime_prices = {}

        # Strategy 1: Try AkShare batch (all A-shares at once — most efficient)
        try:
            spot_df = await safe_ak_call(ak.stock_zh_a_spot_em)
            if spot_df is not None and not spot_df.empty:
                for code in valid_codes:
                    match = spot_df[spot_df["代码"] == code]
                    if not match.empty:
                        row = match.iloc[0]
                        realtime_prices[code] = {
                            "name": str(row.get("名称", "")),
                            "price": float(row["最新价"]) if row.get("最新价") is not None else None,
                            "change_pct": float(row["涨跌幅"]) if row.get("涨跌幅") is not None else None,
                            "open": float(row["今开"]) if row.get("今开") is not None else None,
                            "high": float(row["最高"]) if row.get("最高") is not None else None,
                            "low": float(row["最低"]) if row.get("最低") is not None else None,
                            "prev_close": float(row["昨收"]) if row.get("昨收") is not None else None,
                            "volume_yi": round(float(row["成交额"]) / 1e8, 2) if row.get("成交额") is not None else None,
                            "pe": float(row["市盈率-动态"]) if row.get("市盈率-动态") is not None else None,
                            "pb": float(row["市净率"]) if row.get("市净率") is not None else None,
                            "market_cap_yi": round(float(row["总市值"]) / 1e8, 1) if row.get("总市值") is not None else None,
                            "exchange": "上交所" if code.startswith("6") else "深交所",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
        except Exception as e:
            print(f"[SectorAnalysis] AkShare spot data failed, falling back to yfinance: {e}")

        # Strategy 2: yfinance fallback for codes not found via AkShare
        missing_codes = [c for c in valid_codes if c not in realtime_prices]
        if missing_codes:
            print(f"[SectorAnalysis] Fetching {len(missing_codes)} stocks via yfinance fallback...")
            for code in missing_codes:
                try:
                    yf_symbol = f"{code}.SS" if code.startswith("6") else f"{code}.SZ"
                    ticker = yf.Ticker(yf_symbol)
                    info = ticker.info
                    price = info.get("currentPrice") or info.get("regularMarketPrice")
                    if price:
                        prev_close = info.get("regularMarketPreviousClose")
                        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else None
                        realtime_prices[code] = {
                            "name": info.get("shortName") or info.get("longName") or code,
                            "price": float(price),
                            "change_pct": round(change_pct, 2) if change_pct else None,
                            "open": float(info.get("regularMarketOpen")) if info.get("regularMarketOpen") else None,
                            "high": float(info.get("regularMarketDayHigh")) if info.get("regularMarketDayHigh") else None,
                            "low": float(info.get("regularMarketDayLow")) if info.get("regularMarketDayLow") else None,
                            "prev_close": float(prev_close) if prev_close else None,
                            "volume_yi": None,
                            "pe": float(info.get("trailingPE")) if info.get("trailingPE") else None,
                            "pb": float(info.get("priceToBook")) if info.get("priceToBook") else None,
                            "market_cap_yi": round(float(info.get("marketCap")) / 1e8, 1) if info.get("marketCap") else None,
                            "exchange": "上交所" if code.startswith("6") else "深交所",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                except Exception as e:
                    print(f"[SectorAnalysis] yfinance fallback failed for {code}: {e}")

        if realtime_prices:
            result["realtime_prices"] = realtime_prices
            print(f"[SectorAnalysis] Enriched {len(realtime_prices)} stocks with real-time prices")

        return result
