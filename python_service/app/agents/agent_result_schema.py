"""Agent 结构化输出 Schema (Phase 2, §7.1).

开发指南 §7.1:
  "所有 Agent 输出必须结构化 JSON (Pydantic schema + response_format).
   禁止 content[:2000] 截断."

本模块定义面向 LLM 输出的 Pydantic schema, 用于:
  1. agent_orchestrator.generate_with_tools(response_schema=...) 强制 JSON 输出
  2. 解析 LLM 输出为 contracts.AgentResult (带 stance 维度, v3.1)

与 contracts.AgentResult 的关系:
  - contracts.AgentResult: dataclass, 层间流转的内部表示 (含 agent_id/role)
  - AgentOutputSchema:     Pydantic, LLM 直接产出的结构 (不含 agent_id, 由 BaseAgent 补)
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from ..schemas.contracts import AgentResult, Evidence, RiskItem

logger = logging.getLogger(__name__)


class EvidenceItem(BaseModel):
    """LLM 产出的单条证据 (v3.1 stance 维度)."""
    claim: str = Field(..., description="可追溯的断言")
    stance: str = Field("neutral", description="bullish / bearish / neutral")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="置信度 0-1")
    source: List[str] = Field(default_factory=list, description="数据源 ID/描述")

    @field_validator("stance")
    @classmethod
    def _valid_stance(cls, v: str) -> str:
        v = (v or "neutral").lower().strip()
        if v not in ("bullish", "bearish", "neutral"):
            return "neutral"
        return v


class RiskItemSchema(BaseModel):
    """LLM 产出的单条风险."""
    category: str = Field("market", description="market/liquidity/fundamental/...")
    description: str = Field(..., description="风险描述")
    severity: str = Field("medium", description="low / medium / high")

    @field_validator("severity")
    @classmethod
    def _valid_severity(cls, v: str) -> str:
        v = (v or "medium").lower().strip()
        return v if v in ("low", "medium", "high") else "medium"


class AgentOutputSchema(BaseModel):
    """Agent 结构化输出 (强制 JSON, 移除 2000 字截断).

    LLM 经 response_format 产出此结构, BaseAgent 解析为 AgentResult.
    """
    summary: str = Field(..., description="分析摘要, ≤500 tokens, 禁止截断")
    score: float = Field(0.5, ge=0.0, le=1.0, description="综合评分 0-1")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="置信度 0-1")
    stance: str = Field("neutral", description="整体立场 bullish/bearish/neutral")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="结构化证据列表")
    risk: List[RiskItemSchema] = Field(default_factory=list, description="风险列表")
    status: str = Field("ok", description="ok / degraded / failed / skipped")

    @field_validator("stance")
    @classmethod
    def _valid_stance(cls, v: str) -> str:
        v = (v or "neutral").lower().strip()
        return v if v in ("bullish", "bearish", "neutral") else "neutral"

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        v = (v or "ok").lower().strip()
        return v if v in ("ok", "degraded", "failed", "skipped") else "ok"


# ── JSON Schema (供 OpenAI response_format) ─────────────────────────────────

def agent_output_json_schema() -> dict:
    """返回 OpenAI response_format 兼容的 JSON schema dict."""
    return AgentOutputSchema.model_json_schema()


def response_format_spec() -> dict:
    """返回 OpenAI chat completion 的 response_format 参数."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "AgentOutput",
            "schema": agent_output_json_schema(),
            "strict": False,
        },
    }


# ── 解析: LLM 输出 → contracts.AgentResult ──────────────────────────────────

def parse_agent_output(raw: str, agent_id: str, role: str) -> AgentResult:
    """把 LLM 的 JSON 输出解析为 contracts.AgentResult.

    容错: 若 raw 不是合法 JSON, 降级为 degraded 状态 (不抛异常, 保证不阻塞).
    """
    if not raw:
        return AgentResult(agent_id=agent_id, role=role, status="degraded",
                           summary="(empty output)")
    try:
        # 尝试提取 JSON (LLM 可能包裹在 markdown code block)
        text = raw.strip()
        if text.startswith("```"):
            # 去掉 ```json ... ``` 包裹
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        data = json.loads(text)
        schema = AgentOutputSchema.model_validate(data)
    except Exception as e:
        logger.warning("[AgentOutput] 解析失败 (%s), 降级. raw[:200]=%s", e, raw[:200])
        return AgentResult(
            agent_id=agent_id, role=role, status="degraded",
            summary=raw[:500] if isinstance(raw, str) else str(raw)[:500],
            confidence=0.3,
        )

    # 转为 contracts 内部表示
    evidence = [
        Evidence(
            claim=e.claim, stance=e.stance, confidence=e.confidence,
            source=e.source, agent=role,
        )
        for e in schema.evidence
    ]
    risks = [
        RiskItem(category=r.category, description=r.description, severity=r.severity)
        for r in schema.risk
    ]
    return AgentResult(
        agent_id=agent_id, role=role,
        summary=schema.summary,
        score=schema.score, confidence=schema.confidence,
        evidence=evidence, risk=risks,
        status=schema.status,
    )
