"""Model evaluation framework.

Evaluates model/prompt versions against test suites:
- Golden set: fixed historical cases with known correct answers
- Regression set: previously-failed cases that must stay fixed
- Adversarial set: edge cases designed to trigger hallucinations

A model can only be promoted to production if it passes all required suites.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvalVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class EvalCase:
    case_id: str
    input_symbol: str
    input_context: str
    expected_direction: str  # bullish, bearish, neutral
    expected_min_confidence: float


@dataclass
class EvalSuite:
    name: str
    cases: List[EvalCase]


@dataclass
class CaseFailure:
    case_id: str
    reason: str
    expected: str
    actual: str


@dataclass
class EvalResult:
    suite_name: str
    verdict: EvalVerdict
    pass_rate: float
    total_cases: int
    passed_cases: int
    failures: List[CaseFailure] = field(default_factory=list)


class ModelEvaluator:
    """Evaluate model predictions against a test suite."""

    def __init__(self, pass_threshold: float = 0.8):
        self.pass_threshold = pass_threshold

    def evaluate(self, suite: EvalSuite, predictions: Dict[str, Dict[str, Any]]) -> EvalResult:
        """Run all cases in a suite against predictions.
        
        predictions: {case_id: {"direction": str, "confidence": float}}
        """
        failures: List[CaseFailure] = []
        passed = 0

        for case in suite.cases:
            pred = predictions.get(case.case_id)

            if pred is None:
                failures.append(CaseFailure(
                    case_id=case.case_id,
                    reason="missing prediction",
                    expected=case.expected_direction,
                    actual="<no output>",
                ))
                continue

            pred_direction = pred.get("direction", "")
            pred_confidence = pred.get("confidence", 0.0)

            # Check direction
            if pred_direction != case.expected_direction:
                failures.append(CaseFailure(
                    case_id=case.case_id,
                    reason=f"direction mismatch",
                    expected=case.expected_direction,
                    actual=pred_direction,
                ))
                continue

            # Check confidence
            if pred_confidence < case.expected_min_confidence:
                failures.append(CaseFailure(
                    case_id=case.case_id,
                    reason=f"confidence {pred_confidence:.2f} below minimum {case.expected_min_confidence:.2f}",
                    expected=f">= {case.expected_min_confidence}",
                    actual=str(pred_confidence),
                ))
                continue

            passed += 1

        total = len(suite.cases)
        pass_rate = passed / total if total > 0 else 0.0
        verdict = EvalVerdict.PASS if pass_rate >= self.pass_threshold else EvalVerdict.FAIL

        return EvalResult(
            suite_name=suite.name,
            verdict=verdict,
            pass_rate=pass_rate,
            total_cases=total,
            passed_cases=passed,
            failures=failures,
        )

    def compare(self, baseline: EvalResult, candidate: EvalResult) -> Dict[str, Any]:
        """Compare two evaluation results."""
        return {
            "improved": candidate.pass_rate > baseline.pass_rate,
            "pass_rate_delta": candidate.pass_rate - baseline.pass_rate,
            "baseline_verdict": baseline.verdict.value,
            "candidate_verdict": candidate.verdict.value,
            "baseline_pass_rate": baseline.pass_rate,
            "candidate_pass_rate": candidate.pass_rate,
        }
