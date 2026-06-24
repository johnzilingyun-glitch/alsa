"""P2-3: Model evaluation framework.

Tests for:
- Golden set evaluation (fixed historical cases, must reproduce expected results)
- Regression set (known failure cases must not regress)
- Evaluation result comparison between model/prompt versions
- Pass/fail threshold enforcement
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.evaluation.model_eval import (
    ModelEvaluator,
    EvalCase,
    EvalSuite,
    EvalVerdict,
)


class TestModelEvaluator:
    """Model evaluation framework tests."""

    def test_golden_set_all_pass(self):
        """All golden cases pass → suite passes."""
        evaluator = ModelEvaluator()
        suite = EvalSuite(
            name="golden_v1",
            cases=[
                EvalCase(
                    case_id="g1",
                    input_symbol="MSFT",
                    input_context="Strong earnings beat, Azure growth 30%",
                    expected_direction="bullish",
                    expected_min_confidence=0.6,
                ),
                EvalCase(
                    case_id="g2",
                    input_symbol="BABA",
                    input_context="Regulatory crackdown, revenue miss",
                    expected_direction="bearish",
                    expected_min_confidence=0.5,
                ),
            ],
        )

        # Simulate model outputs
        predictions = {
            "g1": {"direction": "bullish", "confidence": 0.78},
            "g2": {"direction": "bearish", "confidence": 0.65},
        }

        result = evaluator.evaluate(suite, predictions)
        assert result.verdict == EvalVerdict.PASS
        assert result.pass_rate == 1.0

    def test_golden_set_wrong_direction_fails(self):
        """Wrong direction on golden case → suite fails."""
        evaluator = ModelEvaluator()
        suite = EvalSuite(
            name="golden_v1",
            cases=[
                EvalCase(
                    case_id="g1",
                    input_symbol="MSFT",
                    input_context="Clear bullish signals",
                    expected_direction="bullish",
                    expected_min_confidence=0.6,
                ),
            ],
        )

        predictions = {"g1": {"direction": "bearish", "confidence": 0.80}}

        result = evaluator.evaluate(suite, predictions)
        assert result.verdict == EvalVerdict.FAIL
        assert result.pass_rate == 0.0
        assert any("direction" in f.reason for f in result.failures)

    def test_low_confidence_fails(self):
        """Confidence below minimum threshold → case fails."""
        evaluator = ModelEvaluator()
        suite = EvalSuite(
            name="confidence_test",
            cases=[
                EvalCase(
                    case_id="c1",
                    input_symbol="TSLA",
                    input_context="Mixed signals",
                    expected_direction="bullish",
                    expected_min_confidence=0.7,
                ),
            ],
        )

        predictions = {"c1": {"direction": "bullish", "confidence": 0.55}}

        result = evaluator.evaluate(suite, predictions)
        assert result.verdict == EvalVerdict.FAIL
        assert any("confidence" in f.reason for f in result.failures)

    def test_partial_pass_with_threshold(self):
        """Suite passes if pass_rate >= threshold (default 0.8)."""
        evaluator = ModelEvaluator(pass_threshold=0.5)
        suite = EvalSuite(
            name="partial",
            cases=[
                EvalCase(case_id="a", input_symbol="X", input_context="Bull",
                         expected_direction="bullish", expected_min_confidence=0.5),
                EvalCase(case_id="b", input_symbol="Y", input_context="Bear",
                         expected_direction="bearish", expected_min_confidence=0.5),
            ],
        )

        predictions = {
            "a": {"direction": "bullish", "confidence": 0.70},
            "b": {"direction": "bullish", "confidence": 0.60},  # Wrong
        }

        result = evaluator.evaluate(suite, predictions)
        assert result.pass_rate == 0.5
        assert result.verdict == EvalVerdict.PASS  # >= 0.5 threshold

    def test_regression_set_known_failure_must_not_regress(self):
        """Previously fixed failure case must stay fixed."""
        evaluator = ModelEvaluator(pass_threshold=1.0)  # Strict for regression
        suite = EvalSuite(
            name="regression_v1",
            cases=[
                EvalCase(
                    case_id="reg_001",
                    input_symbol="PDD",
                    input_context="Hallucination case: model previously invented fake revenue numbers",
                    expected_direction="bearish",
                    expected_min_confidence=0.5,
                ),
            ],
        )

        predictions = {"reg_001": {"direction": "bearish", "confidence": 0.62}}
        result = evaluator.evaluate(suite, predictions)
        assert result.verdict == EvalVerdict.PASS

    def test_missing_prediction_counts_as_failure(self):
        """If model doesn't produce output for a case, it fails."""
        evaluator = ModelEvaluator()
        suite = EvalSuite(
            name="missing",
            cases=[
                EvalCase(case_id="m1", input_symbol="X", input_context="test",
                         expected_direction="bullish", expected_min_confidence=0.5),
            ],
        )

        predictions = {}  # No output
        result = evaluator.evaluate(suite, predictions)
        assert result.verdict == EvalVerdict.FAIL

    def test_version_comparison(self):
        """Compare two model versions on the same suite."""
        evaluator = ModelEvaluator()
        suite = EvalSuite(
            name="compare",
            cases=[
                EvalCase(case_id="x", input_symbol="A", input_context="Bull",
                         expected_direction="bullish", expected_min_confidence=0.5),
            ],
        )

        v1_result = evaluator.evaluate(suite, {"x": {"direction": "bearish", "confidence": 0.5}})
        v2_result = evaluator.evaluate(suite, {"x": {"direction": "bullish", "confidence": 0.8}})

        comparison = evaluator.compare(v1_result, v2_result)
        assert comparison["improved"] is True
        assert comparison["pass_rate_delta"] > 0
