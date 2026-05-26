"""Trading fields validator — schema enforcement for extracted trading signals.

Ensures that regex-extracted trading fields from Chief Strategist output
are numerically valid and logically consistent before they can become
trade signals. Rejects garbage strings that regex might capture.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    is_valid: bool = True
    signal_eligible: bool = False
    target_price: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    position_pct: Optional[float] = None
    errors: List[str] = field(default_factory=list)


class TradingFieldsValidator:
    """Validate extracted trading plan fields before they become signals."""

    # Regex to extract the first numeric value from a string
    _NUM_RE = re.compile(r"([\d]+(?:[.,]\d+)?)")
    _PCT_RE = re.compile(r"([\d]+(?:\.\d+)?)\s*%")

    @classmethod
    def validate(cls, fields: Dict[str, Any]) -> ValidationResult:
        result = ValidationResult()
        errors: List[str] = []

        # Score validation
        score = fields.get("score")
        if score is not None:
            if not isinstance(score, (int, float)) or score < 0 or score > 100:
                errors.append("score must be 0-100")

        trading_plan = fields.get("tradingPlan")
        if not trading_plan:
            # No trading plan = no signal, but not an error
            result.errors = errors
            result.is_valid = len(errors) == 0
            result.signal_eligible = False
            return result

        # Parse numeric price fields
        target_raw = trading_plan.get("targetPrice", "")
        entry_raw = trading_plan.get("entryPrice", "")
        stop_raw = trading_plan.get("stopLoss", "")
        strategy_raw = trading_plan.get("strategy", "")

        target_price = cls._parse_price(target_raw)
        entry_price = cls._parse_price(entry_raw)
        stop_loss = cls._parse_price(stop_raw)
        position_pct = cls._parse_position(strategy_raw)

        # Validate target price
        if target_raw and target_price is None:
            errors.append(f"targetPrice '{target_raw}' is not a valid numeric price")
        elif target_price is not None:
            result.target_price = target_price

        # Validate entry price
        if entry_raw and entry_price is None:
            errors.append(f"entryPrice '{entry_raw}' is not a valid numeric price")
        elif entry_price is not None:
            result.entry_price = entry_price

        # Validate stop loss
        if stop_raw and stop_loss is None:
            errors.append(f"stopLoss '{stop_raw}' is not a valid numeric price")
        elif stop_loss is not None:
            result.stop_loss = stop_loss

        # Validate position size
        if position_pct is not None:
            if position_pct > 100.0:
                errors.append(f"position size {position_pct}% exceeds 100%")
            elif position_pct < 0:
                errors.append(f"position size {position_pct}% is negative")
            else:
                result.position_pct = position_pct

        # Cross-field logical checks
        sentiment = fields.get("sentiment", "Neutral")
        if target_price and stop_loss:
            if sentiment == "Bullish" and stop_loss >= target_price:
                errors.append(
                    f"stopLoss ({stop_loss}) must be below targetPrice ({target_price}) for bullish direction"
                )
            elif sentiment == "Bearish" and stop_loss <= target_price:
                errors.append(
                    f"stopLoss ({stop_loss}) must be above targetPrice ({target_price}) for bearish direction"
                )

        result.errors = errors
        result.is_valid = len(errors) == 0

        # Signal eligible only if we have valid numeric prices and no errors
        result.signal_eligible = (
            result.is_valid
            and target_price is not None
            and entry_price is not None
            and stop_loss is not None
        )

        return result

    # Qualifier words that indicate an approximate/uncertain price (not actionable)
    _QUALIFIER_RE = re.compile(r"[约大概左右附近以上以下之间到]|见|逻辑")

    @classmethod
    def _parse_price(cls, raw: str) -> Optional[float]:
        """Extract a clean numeric price from potentially messy regex output.
        
        Returns None if the string contains qualifier words indicating
        uncertainty (e.g. "约185元附近") or is not predominantly numeric.
        """
        if not raw or not raw.strip():
            return None

        raw = raw.strip()

        # Reject if qualifier words are present (uncertain/approximate price)
        if cls._QUALIFIER_RE.search(raw):
            return None

        # Strip known currency suffixes for ratio calculation
        cleaned = re.sub(r"\s*(CNY|USD|HKD|元)\s*$", "", raw)

        # Reject strings where numeric content is less than 50% of cleaned length
        digits_and_dots = sum(1 for c in cleaned if c.isdigit() or c in ".,")
        if len(cleaned) > 0 and digits_and_dots / len(cleaned) < 0.5:
            return None

        m = cls._NUM_RE.search(raw)
        if not m:
            return None

        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    @classmethod
    def _parse_position(cls, strategy: str) -> Optional[float]:
        """Extract position percentage from strategy text."""
        if not strategy:
            return None
        m = cls._PCT_RE.search(strategy)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None
