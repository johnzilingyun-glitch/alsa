from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RiskStatus(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RiskRuleHit(BaseModel):
    rule_id: str
    message: str
    severity: Literal["low", "medium", "high", "block"] = "block"


class PreTradeRiskRequest(BaseModel):
    portfolio_id: str
    signal_id: str
    symbol: str
    market: str
    side: Literal["BUY", "SELL", "SHORT", "COVER"]
    requested_quantity: float = Field(gt=0)
    requested_notional: float = Field(gt=0)
    order_type: str
    limit_price: float | None = None
    as_of_date: str
    evidence_quality: float = Field(ge=0.0, le=1.0)
    data_quality_score: float = Field(ge=0.0, le=1.0)
    conflict_level: Literal["C0", "C1", "C2", "C3", "C4"]
    # Portfolio context for weight checks (optional for backward compat)
    portfolio_value: float | None = None
    existing_position_notional: float | None = None
    daily_new_exposure_so_far: float | None = None


class PreTradeRiskResult(BaseModel):
    status: RiskStatus
    blocking_rules: list[RiskRuleHit] = Field(default_factory=list)
    allowed_quantity: float = 0
    allowed_notional: float = 0
    human_review_required: bool = False
    live_execution_allowed: bool = False


class PreTradeRiskGateway:
    def __init__(
        self,
        min_data_quality: float = 0.85,
        min_evidence_quality: float = 0.60,
        max_single_name_pct: float = 10.0,
        max_daily_new_exposure_pct: float = 5.0,
    ):
        self.min_data_quality = min_data_quality
        self.min_evidence_quality = min_evidence_quality
        self.max_single_name_pct = max_single_name_pct
        self.max_daily_new_exposure_pct = max_daily_new_exposure_pct

    def check(self, request: PreTradeRiskRequest) -> PreTradeRiskResult:
        blocking_rules: list[RiskRuleHit] = []

        if request.data_quality_score < self.min_data_quality:
            blocking_rules.append(
                RiskRuleHit(
                    rule_id="DATA_QUALITY_MINIMUM",
                    message=f"Data quality score {request.data_quality_score:.2f} is below {self.min_data_quality:.2f}.",
                )
            )

        if request.evidence_quality < self.min_evidence_quality:
            blocking_rules.append(
                RiskRuleHit(
                    rule_id="EVIDENCE_QUALITY_MINIMUM",
                    message=f"Evidence quality score {request.evidence_quality:.2f} is below {self.min_evidence_quality:.2f}.",
                )
            )

        if request.conflict_level in ("C3", "C4"):
            blocking_rules.append(
                RiskRuleHit(
                    rule_id="AGENT_CONFLICT_BLOCK",
                    message=f"Conflict level {request.conflict_level} blocks order intent.",
                )
            )

        # Single name weight limit
        if request.portfolio_value and request.portfolio_value > 0:
            existing = request.existing_position_notional or 0.0
            new_weight_pct = (existing + request.requested_notional) / request.portfolio_value * 100
            if new_weight_pct > self.max_single_name_pct:
                blocking_rules.append(
                    RiskRuleHit(
                        rule_id="SINGLE_NAME_WEIGHT_LIMIT",
                        message=(
                            f"Position weight {new_weight_pct:.1f}% exceeds "
                            f"max {self.max_single_name_pct:.1f}%."
                        ),
                    )
                )

        # Daily new exposure limit
        if request.portfolio_value and request.portfolio_value > 0 and request.daily_new_exposure_so_far is not None:
            total_today = request.daily_new_exposure_so_far + request.requested_notional
            daily_pct = total_today / request.portfolio_value * 100
            if daily_pct > self.max_daily_new_exposure_pct:
                blocking_rules.append(
                    RiskRuleHit(
                        rule_id="DAILY_EXPOSURE_LIMIT",
                        message=(
                            f"Daily new exposure {daily_pct:.1f}% exceeds "
                            f"max {self.max_daily_new_exposure_pct:.1f}%."
                        ),
                    )
                )

        if blocking_rules:
            return PreTradeRiskResult(
                status=RiskStatus.REJECT,
                blocking_rules=blocking_rules,
                allowed_quantity=0,
                allowed_notional=0,
                human_review_required=True,
                live_execution_allowed=False,
            )

        return PreTradeRiskResult(
            status=RiskStatus.PASS,
            allowed_quantity=request.requested_quantity,
            allowed_notional=request.requested_notional,
            human_review_required=request.conflict_level == "C2",
            live_execution_allowed=False,
        )
