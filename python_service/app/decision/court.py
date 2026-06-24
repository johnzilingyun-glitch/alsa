"""Decision Court — evidence-driven multi-agent arbitration.

Each agent submits structured claims with evidence. The court detects
directional conflicts, assigns conflict levels, and produces a DecisionCase
with signal strength, confidence, and position ceiling.
"""
import uuid
from dataclasses import dataclass, field
from typing import List

from .schemas import AgentDecisionOutput, ConflictLevel


@dataclass
class AgentSubmission:
    output: AgentDecisionOutput


@dataclass
class DecisionCase:
    decision_case_id: str
    symbol: str
    verdict: str  # buy, sell, watch, hold
    signal_strength: float  # 0.0 - 1.0
    confidence: float  # 0.0 - 1.0
    conflict_level: ConflictLevel
    evidence_quality: float
    position_ceiling: float  # 0.0 - 1.0 (1.0 = no restriction)
    human_review_required: bool
    falsification_conditions: List[str] = field(default_factory=list)


class DecisionCourt:
    """Adjudicates agent submissions into a decision case."""

    def __init__(self):
        self._submissions: List[AgentSubmission] = []

    def submit(self, submission: AgentSubmission) -> None:
        """Accept an agent's structured output for adjudication."""
        self._submissions.append(submission)

    def adjudicate(self, symbol: str) -> DecisionCase:
        """Evaluate all submissions and produce a decision case."""
        if not self._submissions:
            return DecisionCase(
                decision_case_id=f"case_{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                verdict="watch",
                signal_strength=0.0,
                confidence=0.0,
                conflict_level=ConflictLevel.C0,
                evidence_quality=0.0,
                position_ceiling=0.0,
                human_review_required=False,
            )

        # Collect all claims
        all_claims = []
        for sub in self._submissions:
            all_claims.extend(sub.output.claims)

        # Detect conflict level
        conflict_level = self._detect_conflict(all_claims)

        # Calculate signal strength from score contributions
        signal_strength = self._compute_signal_strength()

        # Calculate confidence from evidence quality
        confidence = self._compute_confidence(all_claims)

        # Evidence quality = average credibility across evidence-backed claims
        evidence_quality = confidence  # Simplified: same as confidence for now

        # Position ceiling based on conflict level
        position_ceiling = self._conflict_to_ceiling(conflict_level)

        # Determine verdict
        verdict = self._determine_verdict(signal_strength, conflict_level)

        # Collect falsification conditions
        falsification_conditions = [
            claim.falsification_condition for claim in all_claims
            if claim.falsification_condition
        ]

        case = DecisionCase(
            decision_case_id=f"case_{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            verdict=verdict,
            signal_strength=signal_strength,
            confidence=confidence,
            conflict_level=conflict_level,
            evidence_quality=evidence_quality,
            position_ceiling=position_ceiling,
            human_review_required=conflict_level in (ConflictLevel.C2, ConflictLevel.C3, ConflictLevel.C4),
            falsification_conditions=falsification_conditions,
        )

        # Clear submissions to prevent state leakage between calls
        self._submissions.clear()

        return case

    def _detect_conflict(self, claims) -> ConflictLevel:
        """Detect directional conflicts between high-confidence claims."""
        bullish = [c for c in claims if c.direction == "bullish" and c.confidence >= 0.6]
        bearish = [c for c in claims if c.direction == "bearish" and c.confidence >= 0.6]

        if not bullish or not bearish:
            return ConflictLevel.C0

        # Check if conflicting claims are on the same horizon
        bull_horizons = {c.horizon for c in bullish}
        bear_horizons = {c.horizon for c in bearish}

        if bull_horizons & bear_horizons:
            # Same-horizon directional conflict
            max_bull_conf = max(c.confidence for c in bullish)
            max_bear_conf = max(c.confidence for c in bearish)

            if max_bull_conf >= 0.8 and max_bear_conf >= 0.8:
                return ConflictLevel.C3  # Both very confident = data conflict
            elif max_bull_conf >= 0.7 and max_bear_conf >= 0.7:
                return ConflictLevel.C2  # Direction conflict
            else:
                return ConflictLevel.C1  # Explanatory conflict

        return ConflictLevel.C1  # Different horizons = mild conflict

    def _compute_signal_strength(self) -> float:
        """Weighted average of score contributions across submissions."""
        scores = []
        for sub in self._submissions:
            sc = sub.output.score_contribution
            # Average non-None scores
            values = [v for v in [sc.quality, sc.growth, sc.valuation, sc.momentum, sc.text_catalyst] if v is not None]
            if values:
                scores.append(sum(values) / len(values))

        if not scores:
            return 0.0
        return min(1.0, sum(scores) / len(scores))

    def _compute_confidence(self, claims) -> float:
        """Average confidence across all claims."""
        if not claims:
            return 0.0
        return sum(c.confidence for c in claims) / len(claims)

    @staticmethod
    def _conflict_to_ceiling(level: ConflictLevel) -> float:
        """Map conflict level to maximum position ceiling."""
        return {
            ConflictLevel.C0: 1.0,
            ConflictLevel.C1: 0.85,
            ConflictLevel.C2: 0.70,  # 30% reduction
            ConflictLevel.C3: 0.0,   # No position allowed
            ConflictLevel.C4: 0.0,
        }[level]

    @staticmethod
    def _determine_verdict(signal_strength: float, conflict_level: ConflictLevel) -> str:
        """Map signal strength and conflict to verdict."""
        if conflict_level in (ConflictLevel.C3, ConflictLevel.C4):
            return "watch"
        if signal_strength >= 0.65:
            return "buy"
        elif signal_strength >= 0.45:
            return "hold"
        elif signal_strength >= 0.25:
            return "watch"
        else:
            return "sell"
