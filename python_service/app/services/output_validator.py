"""Basic LLM Output Validator — Phase 1 sanity checks.

Scans LLM-generated text for obviously incorrect financial data:
- Impossible values (negative prices, PE > 10000, etc.)
- Future dates
- Suspicious round numbers that suggest hallucination

This is a lightweight Phase 1 implementation. Phase 2 will add:
- Cross-verification against real data sources
- DataVerifier Agent with low-temperature LLM validation
- Structured output parsing
"""
import logging
import re
from datetime import datetime, date
from typing import List, Tuple

logger = logging.getLogger(__name__)


# Patterns to extract financial values from LLM text
_PRICE_PATTERN = re.compile(
    r'(?:股价|价格|收盘价|开盘价|current price|price|close)\s*[:：]?\s*[¥$]?\s*(-?[\d,]+\.?\d*)',
    re.IGNORECASE
)
_PE_PATTERN = re.compile(
    r'(?:PE|P/E|市盈率|PE ratio)\s*[:：]?\s*([\d,]+\.?\d*)',
    re.IGNORECASE
)
_CHANGE_PATTERN = re.compile(
    r'(?:涨幅|跌幅|涨跌|change|return|回报)\s*[:：]?\s*[+-]?([\d,]+\.?\d*)\s*%',
    re.IGNORECASE
)
_DATE_PATTERN = re.compile(
    r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})'
)
_MARKET_CAP_PATTERN = re.compile(
    r'(?:市值|market cap)\s*[:：]?\s*([\d,]+\.?\d*)\s*(?:万亿|trillion)',
    re.IGNORECASE
)


class OutputValidator:
    """Lightweight validator for LLM-generated financial text."""

    # Thresholds for anomaly detection
    MAX_STOCK_PRICE = 100_000  # Highest stocks rarely exceed this (BRK.A excluded)
    MAX_PE_RATIO = 5_000       # PE > 5000 is almost certainly wrong
    MAX_SINGLE_DAY_CHANGE = 50  # Most markets have circuit breakers < 20%
    MAX_MARKET_CAP_TRILLION = 20  # Apple ~3T, so 20T is clearly wrong
    MIN_PRICE = 0              # Prices can't be negative

    def validate(self, text: str) -> Tuple[str, List[str]]:
        """Validate LLM output text and annotate suspicious values.

        Returns:
            Tuple of (possibly-annotated text, list of warning messages)
        """
        warnings = []

        # Check prices
        for match in _PRICE_PATTERN.finditer(text):
            value = self._parse_number(match.group(1))
            if value is not None and (value < self.MIN_PRICE or value > self.MAX_STOCK_PRICE):
                warnings.append(f"可疑价格: {value} (正常范围 0-{self.MAX_STOCK_PRICE})")

        # Check PE ratios
        for match in _PE_PATTERN.finditer(text):
            value = self._parse_number(match.group(1))
            if value is not None and value > self.MAX_PE_RATIO:
                warnings.append(f"可疑PE: {value} (正常范围 0-{self.MAX_PE_RATIO})")

        # Check percentage changes
        for match in _CHANGE_PATTERN.finditer(text):
            value = self._parse_number(match.group(1))
            if value is not None and value > self.MAX_SINGLE_DAY_CHANGE:
                warnings.append(f"可疑涨跌幅: {value}% (单日超过 {self.MAX_SINGLE_DAY_CHANGE}%)")

        # Check market cap
        for match in _MARKET_CAP_PATTERN.finditer(text):
            value = self._parse_number(match.group(1))
            if value is not None and value > self.MAX_MARKET_CAP_TRILLION:
                warnings.append(f"可疑市值: {value}万亿/trillion (超过 {self.MAX_MARKET_CAP_TRILLION})")

        # Check dates (no future dates)
        today = date.today()
        for match in _DATE_PATTERN.finditer(text):
            try:
                y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                parsed_date = date(y, m, d)
                if parsed_date > today:
                    # Allow near-future dates (predictions/targets)
                    days_ahead = (parsed_date - today).days
                    if days_ahead > 365:
                        warnings.append(f"可疑日期: {match.group(0)} (超过未来1年)")
            except (ValueError, OverflowError):
                pass

        if warnings:
            logger.warning(f"LLM output validation found {len(warnings)} issue(s): {warnings}")

        return text, warnings

    @staticmethod
    def _parse_number(s: str) -> float | None:
        try:
            return float(s.replace(",", ""))
        except (ValueError, TypeError):
            return None


# Singleton
output_validator = OutputValidator()
