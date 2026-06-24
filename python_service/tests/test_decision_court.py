"""P1-2: Decision Court — evidence-driven agent arbitration.

Tests for:
- Agent claims submission with evidence references
- Conflict detection between opposing claims
- Conflict level assignment (C0-C4)
- Decision case verdict generation
- Position ceiling enforcement based on conflict level
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.decision.court import (
    DecisionCourt,
    AgentSubmission,
)
from python_service.app.decision.schemas import (
    AgentClaim,
    AgentDecisionOutput,
    ConflictLevel,
    ScoreContribution,
    PositionImpact,
)


def _bullish_submission() -> AgentSubmission:
    return AgentSubmission(
        output=AgentDecisionOutput(
            agent_role="Fundamental Analyst",
            run_id="run_001",
            snapshot_id="snap_001",
            as_of_date="2026-05-25T15:00:00+08:00",
            claims=[
                AgentClaim(
                    claim_id="c1",
                    statement="Revenue growth is re-accelerating with 3 consecutive quarters of improvement.",
                    direction="bullish",
                    horizon="6m",
                    confidence=0.82,
                    evidence_ids=["ev_001", "ev_002"],
                    falsification_condition="Revenue growth drops below 5% for 2 quarters.",
                )
            ],
            score_contribution=ScoreContribution(quality=0.75, growth=0.80),
            position_impact=PositionImpact(direction="increase", max_weight_delta=0.02),
        )
    )


def _bearish_submission() -> AgentSubmission:
    return AgentSubmission(
        output=AgentDecisionOutput(
            agent_role="Bear Advocate",
            run_id="run_002",
            snapshot_id="snap_001",
            as_of_date="2026-05-25T15:00:00+08:00",
            claims=[
                AgentClaim(
                    claim_id="c2",
                    statement="Revenue growth is artificially inflated by one-time contract recognition.",
                    direction="bearish",
                    horizon="6m",
                    confidence=0.75,
                    evidence_ids=["ev_003"],
                    falsification_condition="Next quarter organic growth confirmed above 10%.",
                )
            ],
            score_contribution=ScoreContribution(quality=0.40, growth=0.30),
            position_impact=PositionImpact(direction="decrease", max_weight_delta=-0.03),
        )
    )


class TestDecisionCourt:
    """Test the evidence-driven decision court."""

    def test_single_bullish_agent_no_conflict(self):
        court = DecisionCourt()
        court.submit(_bullish_submission())
        case = court.adjudicate(symbol="MSFT")
        assert case.conflict_level == ConflictLevel.C0
        assert case.signal_strength > 0

    def test_opposing_claims_create_conflict(self):
        """Bullish vs bearish high-confidence claims on same horizon = conflict."""
        court = DecisionCourt()
        court.submit(_bullish_submission())
        court.submit(_bearish_submission())
        case = court.adjudicate(symbol="MSFT")
        assert case.conflict_level in (ConflictLevel.C1, ConflictLevel.C2)

    def test_c2_conflict_reduces_position_ceiling(self):
        """C2 conflict must reduce position ceiling by at least 30%."""
        court = DecisionCourt()
        court.submit(_bullish_submission())
        court.submit(_bearish_submission())
        case = court.adjudicate(symbol="MSFT")
        if case.conflict_level == ConflictLevel.C2:
            assert case.position_ceiling <= 0.70  # 30% reduction from 1.0 max

    def test_decision_case_has_required_fields(self):
        court = DecisionCourt()
        court.submit(_bullish_submission())
        case = court.adjudicate(symbol="MSFT")
        assert case.decision_case_id is not None
        assert case.symbol == "MSFT"
        assert case.verdict in ("buy", "sell", "watch", "hold")
        assert 0.0 <= case.signal_strength <= 1.0
        assert 0.0 <= case.confidence <= 1.0
        assert case.evidence_quality >= 0.0

    def test_no_submissions_returns_watch(self):
        court = DecisionCourt()
        case = court.adjudicate(symbol="MSFT")
        assert case.verdict == "watch"
        assert case.signal_strength == 0.0

    def test_falsification_conditions_collected(self):
        court = DecisionCourt()
        court.submit(_bullish_submission())
        court.submit(_bearish_submission())
        case = court.adjudicate(symbol="MSFT")
        assert len(case.falsification_conditions) >= 2

    def test_human_review_required_at_c2_plus(self):
        """C2+ conflict should flag human review."""
        court = DecisionCourt()
        court.submit(_bullish_submission())
        court.submit(_bearish_submission())
        case = court.adjudicate(symbol="MSFT")
        if case.conflict_level >= ConflictLevel.C2:
            assert case.human_review_required is True
