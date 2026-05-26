"""P0-4: Agent output schema validation.

Trading-critical fields extracted from Chief Strategist output MUST pass
schema validation before being persisted or used in any trade signal.
Regex-extracted strings that fail numeric parsing must be rejected.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from python_service.app.decision.trading_fields_validator import (
    TradingFieldsValidator,
    ValidationResult,
)


class TestTradingFieldsValidation:
    """Validate that extracted trading plan fields pass schema checks."""

    def test_valid_trading_plan_passes(self):
        """Well-formed numeric fields pass validation."""
        fields = {
            "sentiment": "Bullish",
            "recommendation": "Buy",
            "tradingPlan": {
                "targetPrice": "185.50",
                "entryPrice": "170.00",
                "stopLoss": "158.00",
                "strategy": "趋势跟踪，分批建仓（仓位: 5%）",
            },
            "score": 72,
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid
        assert result.target_price == 185.50
        assert result.entry_price == 170.00
        assert result.stop_loss == 158.00
        assert result.position_pct == 5.0
        assert result.errors == []

    def test_garbage_price_rejected(self):
        """Non-numeric price strings must be rejected, not silently passed."""
        fields = {
            "sentiment": "Bullish",
            "recommendation": "Buy",
            "tradingPlan": {
                "targetPrice": "约185元附近",  # Garbage from regex
                "entryPrice": "170左右",
                "stopLoss": "见逻辑止损",
            },
        }
        result = TradingFieldsValidator.validate(fields)
        assert not result.is_valid
        assert any("targetPrice" in e for e in result.errors)

    def test_stop_above_target_rejected(self):
        """Stop loss higher than target price for bullish direction is invalid."""
        fields = {
            "sentiment": "Bullish",
            "recommendation": "Buy",
            "tradingPlan": {
                "targetPrice": "100.00",
                "entryPrice": "95.00",
                "stopLoss": "110.00",  # Above target — impossible for long
            },
        }
        result = TradingFieldsValidator.validate(fields)
        assert not result.is_valid
        assert any("stopLoss" in e for e in result.errors)

    def test_position_over_100_percent_rejected(self):
        """Position size above 100% must be blocked."""
        fields = {
            "sentiment": "Bullish",
            "recommendation": "Buy",
            "tradingPlan": {
                "strategy": "仓位: 150%",
            },
        }
        result = TradingFieldsValidator.validate(fields)
        assert not result.is_valid
        assert any("position" in e.lower() for e in result.errors)

    def test_missing_trading_plan_returns_empty_valid(self):
        """If no trading plan extracted, validation passes vacuously (no signal)."""
        fields = {"sentiment": "Neutral", "recommendation": "Hold"}
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid
        assert result.signal_eligible is False

    def test_score_out_of_range_clamped(self):
        """Score must be 0-100; values outside are rejected."""
        fields = {"score": 150}
        result = TradingFieldsValidator.validate(fields)
        assert not result.is_valid
        assert any("score" in e for e in result.errors)

    def test_valid_result_is_signal_eligible(self):
        """Only fully validated plans with numeric prices are signal-eligible."""
        fields = {
            "sentiment": "Bullish",
            "recommendation": "Buy",
            "tradingPlan": {
                "targetPrice": "50.00",
                "entryPrice": "42.00",
                "stopLoss": "38.00",
                "strategy": "建议仓位: 3%",
            },
            "score": 65,
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid
        assert result.signal_eligible is True
