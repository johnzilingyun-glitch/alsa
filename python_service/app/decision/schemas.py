from enum import Enum
from typing import Dict, List, Literal

from pydantic import BaseModel, Field, field_validator


class ConflictLevel(str, Enum):
    C0 = "C0"
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"


class AgentClaim(BaseModel):
    claim_id: str
    statement: str = Field(min_length=10)
    direction: Literal["bullish", "bearish", "neutral", "mixed"]
    horizon: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: List[str] = Field(min_length=1)
    numeric_support: Dict[str, float | int | str] = Field(default_factory=dict)
    falsification_condition: str = Field(min_length=10)
    risk_flags: List[str] = Field(default_factory=list)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_must_not_be_blank(cls, value: List[str]) -> List[str]:
        if any(not item.strip() for item in value):
            raise ValueError("evidence_ids cannot contain blank values")
        return value


class ScoreContribution(BaseModel):
    quality: float | None = Field(default=None, ge=0.0, le=1.0)
    growth: float | None = Field(default=None, ge=0.0, le=1.0)
    valuation: float | None = Field(default=None, ge=0.0, le=1.0)
    momentum: float | None = Field(default=None, ge=0.0, le=1.0)
    text_catalyst: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_penalty: float | None = Field(default=None, ge=0.0, le=1.0)


class PositionImpact(BaseModel):
    direction: Literal["increase", "decrease", "hold", "block"]
    max_weight_delta: float


class AgentDecisionOutput(BaseModel):
    agent_role: str
    run_id: str
    snapshot_id: str
    as_of_date: str
    claims: List[AgentClaim] = Field(min_length=1)
    score_contribution: ScoreContribution
    position_impact: PositionImpact
    conflict_level: ConflictLevel = ConflictLevel.C0
