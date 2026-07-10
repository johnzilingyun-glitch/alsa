"""Analysis V2 API — 新架构 Pipeline 对比测试端点.

新增独立端点 (不改旧 /api/analysis/jobs 流程):
  POST /api/analysis/v2-pipeline
    body: {symbol, market, question, mock}
    mock=true  (默认): 返回演示 PipelineResult (展示新架构结构化输出形态)
    mock=false: 真实调 analysis_pipeline.run() (需 LLM + 数据环境)

返回 PipelineResult 序列化:
  status / decision(FinalDecision) / aggregated(AggregatedEvidence)
  / critique / guardrail / report(markdown) / trace_summary

供前端 NewArchCompare 对比页面调用, 让用户对比旧流程(HTML报告)与新架构(结构化决策+证据).
"""
from __future__ import annotations

import logging
import json
import dataclasses
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Any
from ..utils.responses import success_response, error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis-v2"])


class V2PipelineRequest(BaseModel):
    symbol: str
    market: str = "US-Share"
    question: str = ""
    mock: bool = True  # 默认 mock 演示 (无需 LLM/数据环境)


@router.post("/v2-pipeline")
async def v2_pipeline(req: V2PipelineRequest):
    """新架构 Pipeline 端点 (对比测试用)."""
    try:
        if req.mock:
            return success_response(_mock_pipeline_result(req.symbol, req.market))
        # 真实模式: 调 analysis_pipeline
        from ..services.analysis_pipeline import analysis_pipeline
        result = await analysis_pipeline.run(
            req.symbol, req.question or f"分析 {req.symbol}",
            market=req.market,
        )
        return success_response(_serialize_pipeline_result(result))
    except Exception as e:
        logger.exception("[V2Pipeline] 执行失败")
        return error_response("v2_pipeline_error", f"v2-pipeline 失败: {e}")


@router.post("/v2-pipeline/stream")
async def v2_pipeline_stream(req: V2PipelineRequest):
    """新架构 Pipeline SSE 流式端点 (真实模式实时进度).

    以 Server-Sent Events 逐阶段推送进度:
      data: {"stage": "planning", "status": "start", ...}\\n\\n
      ...
      data: {"stage": "result", "status": "ok", "result": {...}}\\n\\n
    (阶段: planning → execution → aggregation → reflection → decision → guardrail → report)
    """
    from ..services.analysis_pipeline import analysis_pipeline

    async def event_gen():
        try:
            async for ev in analysis_pipeline.run_streaming(
                req.symbol, req.question or f"分析 {req.symbol}",
                market=req.market,
            ):
                if ev.get("stage") == "result":
                    payload = {
                        "stage": "result",
                        "status": ev.get("status"),
                        "result": _serialize_pipeline_result(ev["result"]),
                    }
                else:
                    payload = ev
                yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.exception("[V2PipelineStream] 执行失败")
            yield f"data: {json.dumps({'stage': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 序列化 ──────────────────────────────────────────────────────────────

def _serialize_pipeline_result(result) -> dict:
    """PipelineResult → dict (前端可消费)."""
    from ..schemas.contracts import AggregatedEvidence, CritiqueResult

    def _ev(e):
        return {"claim": e.claim, "stance": e.stance, "confidence": e.confidence,
                "source": e.source, "agent": e.agent}

    def _claim(c):
        return {"claim": c.claim, "consensus": c.consensus,
                "supporting": [_ev(e) for e in c.supporting],
                "contradicting": [_ev(e) for e in c.contradicting]}

    agg = result.aggregated
    return {
        "status": result.status,
        "symbol": result.decision.symbol if result.decision else "",
        "decision": {
            "final_score": result.decision.final_score,
            "stance": result.decision.stance,
            "action": result.decision.action,
            "confidence": result.decision.confidence,
            "summary": result.decision.summary,
            "can_act": result.decision.can_act,
            "key_claims": result.decision.key_claims,
            "rationale": result.decision.rationale,
            "risks": [{"category": r.category, "description": r.description, "severity": r.severity}
                      for r in result.decision.risks],
        } if result.decision else None,
        "aggregated": {
            "claims": [_claim(c) for c in agg.claims],
            "conflicts": [{"claim": c.claim, "supporting_n": len(c.supporting),
                           "contradicting_n": len(c.contradicting)} for c in agg.conflicts],
            "coverage": agg.coverage,
        } if agg else None,
        "critique": {
            "can_finalize": result.critique.can_finalize,
            "round_num": result.critique.round_num,
            "issues": [{"severity": i.severity, "description": i.description}
                       for i in result.critique.issues],
            "rerun_agents": result.critique.rerun_agents,
        } if result.critique else None,
        "guardrail": {
            "action": result.guardrail.action,
            "passed": result.guardrail.passed,
            "issues": [{"severity": i.severity, "rule": i.rule, "description": i.description}
                       for i in result.guardrail.issues],
        } if result.guardrail else None,
        "report": result.report,
        "trace_summary": result.trace_summary,
        "agent_results": [
            {"agent_id": r.agent_id, "role": r.role, "status": r.status,
             "score": r.score, "confidence": r.confidence,
             "evidence_count": len(r.evidence)} for r in result.results
        ],
    }


# ── Mock 演示数据 (展示新架构结构化输出形态) ─────────────────────────────

def _mock_pipeline_result(symbol: str, market: str) -> dict:
    """构造演示 PipelineResult (让用户看到新架构输出形态, 无需 LLM)."""
    from ..schemas.contracts import (
        ExecutionPlan, AgentSpec, AgentResult, Evidence, AggregatedEvidence,
        AggregatedClaim, Conflict, CritiqueResult, Issue, Snapshot,
    )
    from ..agents.decision_agent import FinalDecision
    from ..agents.report_builder import ReportBuilder
    from ..services.output_guardrail import OutputGuardrail, GuardrailResult

    # 演示: 3 个 Agent 结果
    results = [
        AgentResult(agent_id=f"TA@{symbol}", role="Technical Analyst", status="ok",
                    score=0.78, confidence=0.85, summary="MACD 金叉, 站上 MA20, 趋势偏多",
                    evidence=[
                        Evidence(claim="MACD 金叉确认", stance="bullish", confidence=0.9,
                                 source=["kline", "indicator"], agent="Technical Analyst"),
                        Evidence(claim="量能略有不足", stance="bearish", confidence=0.5,
                                 source=["kline"], agent="Technical Analyst"),
                    ]),
        AgentResult(agent_id=f"FA@{symbol}", role="Fundamental Analyst", status="ok",
                    score=0.72, confidence=0.8, summary="营收稳健增长, ROE 优于同业",
                    evidence=[
                        Evidence(claim="营收同比增长 18%", stance="bullish", confidence=0.85,
                                 source=["financial_stmt"], agent="Fundamental Analyst"),
                    ]),
        AgentResult(agent_id=f"SA@{symbol}", role="Sentiment Analyst", status="ok",
                    score=0.68, confidence=0.7, summary="舆情偏多, 机构评级买入占比 65%",
                    evidence=[
                        Evidence(claim="机构买入评级占多数", stance="bullish", confidence=0.7,
                                 source=["news", "analyst_rating"], agent="Sentiment Analyst"),
                    ]),
    ]

    # 聚合证据
    aggregated = AggregatedEvidence(
        claims=[
            AggregatedClaim(
                claim="MACD 金叉确认",
                supporting=[results[0].evidence[0]],
                contradicting=[results[0].evidence[1]],
                consensus=0.78,
            ),
            AggregatedClaim(
                claim="营收同比增长 18%",
                supporting=[results[1].evidence[0]],
                contradicting=[],
                consensus=1.0,
            ),
            AggregatedClaim(
                claim="机构买入评级占多数",
                supporting=[results[2].evidence[0]],
                contradicting=[],
                consensus=1.0,
            ),
        ],
        conflicts=[Conflict(claim="MACD 金叉确认",
                            supporting=[results[0].evidence[0]],
                            contradicting=[results[0].evidence[1]])],
        coverage={"Technical Analyst": 0.85, "Fundamental Analyst": 0.8, "Sentiment Analyst": 0.7},
    )

    # 反思
    critique = CritiqueResult(can_finalize=True, round_num=1,
                              issues=[Issue(severity="medium",
                                            description="MACD 金叉但量能不足, 需关注量价配合")])

    # 决策
    decision = FinalDecision(
        symbol=symbol, final_score=0.73, stance="bullish", action="buy",
        confidence=0.78, summary="技术面金叉+基本面稳健+舆情偏多, 综合建议买入",
        key_claims=["[0.78] MACD 金叉确认", "[1.0] 营收同比增长 18%", "[1.0] 机构买入评级占多数"],
        can_act=True,
        rationale="基于 3 个 Agent 加权评分 (TA 0.78 + FA 0.72 + SA 0.68); critique 可 finalize; 平均 coverage 0.78",
    )

    # Guardrail
    guardrail = GuardrailResult(passed=True, action="pass")

    # 报告
    report = ReportBuilder().build_markdown(decision, aggregated, results, critique)

    # 组装 (复用 _serialize 逻辑)
    from ..schemas.contracts import RiskItem
    decision.risks = [RiskItem(category="market", description="量能不足, 金叉有效性待验证", severity="medium"),
                      RiskItem(category="macro", description="需关注大盘系统性风险", severity="low")]

    serialized = _serialize_pipeline_result(type("R", (), {
        "status": "ok", "decision": decision, "aggregated": aggregated,
        "critique": critique, "guardrail": guardrail, "report": report,
        "trace_summary": {"trace_id": "demo_v2", "span_count": 7, "total_duration_ms": 4520,
                          "by_kind": {"planning": {"count": 1}, "dag": {"count": 1},
                                      "evidence": {"count": 1}, "reflection": {"count": 1},
                                      "decision": {"count": 1}, "guardrail": {"count": 1},
                                      "report": {"count": 1}},
                          "failed_spans": []},
        "results": results,
    })())
    serialized["mock"] = True
    serialized["architecture"] = "v3.1 七层多智能体 (Planner→DAG→Aggregator→Reflection→Decision→Guardrail→Report)"
    return serialized
