"""Tests for TradingFieldsValidator — trading signal schema enforcement."""
import pytest
from python_service.app.decision.trading_fields_validator import (
    TradingFieldsValidator, ValidationResult,
)


class TestValidateBasic:
    """Test basic validation scenarios."""

    def test_no_trading_plan_is_valid_but_not_eligible(self):
        result = TradingFieldsValidator.validate({"score": 75})
        assert result.is_valid is True
        assert result.signal_eligible is False

    def test_valid_trading_plan(self):
        fields = {
            "score": 80,
            "sentiment": "Bullish",
            "tradingPlan": {
                "targetPrice": "185.50",
                "entryPrice": "170.00",
                "stopLoss": "160.00",
                "strategy": "建仓 20% 仓位",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid is True
        assert result.signal_eligible is True
        assert result.target_price == 185.50
        assert result.entry_price == 170.00
        assert result.stop_loss == 160.00
        assert result.position_pct == 20.0

    def test_invalid_score(self):
        result = TradingFieldsValidator.validate({"score": 150})
        assert result.is_valid is False
        assert any("score" in e for e in result.errors)

    def test_negative_score_invalid(self):
        result = TradingFieldsValidator.validate({"score": -5})
        assert result.is_valid is False


class TestPriceValidation:
    """Test price parsing and validation."""

    def test_numeric_string_parsed(self):
        fields = {
            "tradingPlan": {
                "targetPrice": "185.50",
                "entryPrice": "170",
                "stopLoss": "160.00",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.target_price == 185.50
        assert result.entry_price == 170.0

    def test_currency_suffix_stripped(self):
        fields = {
            "tradingPlan": {
                "targetPrice": "185.50 CNY",
                "entryPrice": "170 USD",
                "stopLoss": "160 HKD",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.target_price == 185.50

    def test_qualifier_words_reject_price(self):
        """Approximate/uncertain prices should be rejected."""
        fields = {
            "tradingPlan": {
                "targetPrice": "约185元附近",
                "entryPrice": "170",
                "stopLoss": "160",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.target_price is None  # Rejected due to qualifier

    def test_non_numeric_string_rejected(self):
        fields = {
            "tradingPlan": {
                "targetPrice": "见逻辑分析",
                "entryPrice": "170",
                "stopLoss": "160",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.target_price is None

    def test_empty_price_fields(self):
        fields = {
            "tradingPlan": {
                "targetPrice": "",
                "entryPrice": "",
                "stopLoss": "",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid is True
        assert result.signal_eligible is False  # No prices = not eligible


class TestCrossFieldValidation:
    """Test cross-field logical consistency."""

    def test_bullish_stop_above_target_rejected(self):
        fields = {
            "sentiment": "Bullish",
            "tradingPlan": {
                "targetPrice": "100",
                "entryPrice": "90",
                "stopLoss": "110",  # stop > target for bullish = wrong
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid is False
        assert any("stopLoss" in e for e in result.errors)

    def test_bearish_stop_below_target_rejected(self):
        fields = {
            "sentiment": "Bearish",
            "tradingPlan": {
                "targetPrice": "80",
                "entryPrice": "100",
                "stopLoss": "70",  # stop < target for bearish = wrong
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid is False

    def test_bullish_correct_direction_passes(self):
        fields = {
            "sentiment": "Bullish",
            "tradingPlan": {
                "targetPrice": "200",
                "entryPrice": "150",
                "stopLoss": "130",  # stop < target for bullish = correct
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid is True


class TestPositionSizing:
    """Test position percentage parsing."""

    def test_valid_position_percentage(self):
        fields = {
            "tradingPlan": {
                "strategy": "建议建仓 30% 仓位",
                "targetPrice": "100",
                "entryPrice": "90",
                "stopLoss": "80",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.position_pct == 30.0

    def test_position_exceeds_100_rejected(self):
        fields = {
            "tradingPlan": {
                "strategy": "建仓 150% 仓位",
                "targetPrice": "100",
                "entryPrice": "90",
                "stopLoss": "80",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.is_valid is False
        assert result.position_pct is None

    def test_no_strategy_text(self):
        fields = {
            "tradingPlan": {
                "strategy": "",
                "targetPrice": "100",
                "entryPrice": "90",
                "stopLoss": "80",
            }
        }
        result = TradingFieldsValidator.validate(fields)
        assert result.position_pct is None


class TestParsePrice:
    """Test the internal _parse_price method."""

    def test_simple_number(self):
        assert TradingFieldsValidator._parse_price("185.50") == 185.50

    def test_with_comma(self):
        assert TradingFieldsValidator._parse_price("1,850") == 1850.0

    def test_empty_string(self):
        assert TradingFieldsValidator._parse_price("") is None

    def test_none_input(self):
        assert TradingFieldsValidator._parse_price(None) is None

    def test_mostly_text_rejected(self):
        assert TradingFieldsValidator._parse_price("参考PE估值来看") is None
