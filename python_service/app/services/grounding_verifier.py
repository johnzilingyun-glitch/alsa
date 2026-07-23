"""Grounding Verifier — validates LLM output numeric claims against actual market data.

Prevents hallucinated financial figures from reaching users by cross-referencing
LLM-generated numbers with the snapshot data collected from market APIs.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Patterns that match common financial figure mentions in Chinese/English
NUMERIC_PATTERNS = [
    # Chinese: "PE约XX倍" "市盈率为XX" "ROE达到XX%"
    (r'(?:PE|市盈率|P/E)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(倍|x|X)?', 'pe'),
    (r'(?:PB|市净率|P/B)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(倍|x|X)?', 'pb'),
    (r'(?:ROE|净资产收益率)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(%)?', 'roe'),
    (r'(?:总营收|营业总收入|营业收入)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(亿|万|百万|B|M|K)?', 'revenue'),
    (r'(?:净利润|归母净利润|扣非净利润)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(亿|万|百万|B|M|K)?', 'net_income'),
    (r'(?:市值|总市值)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(亿|万|百万|B|M|K)?', 'market_cap'),
    (r'(?:股息率|分红率)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(%)?', 'dividend_yield'),
    (r'(?:毛利率)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(%)?', 'gross_margin'),
    (r'(?:净利率)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(%)?', 'net_margin'),
    (r'(?:资产负债率)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)\s*(%)?', 'debt_ratio'),
    (r'(?:EPS|每股收益)[\s:：=是为约达到在]{0,5}\s*(\d+\.?\d*)()?', 'eps'),
    # English patterns
    (r'(?:PE|P/E)\s*(?:ratio)?[\s:=]{0,3}\s*(\d+\.?\d*)()?', 'pe'),
    (r'(?:PB|P/B)\s*(?:ratio)?[\s:=]{0,3}\s*(\d+\.?\d*)()?', 'pb'),
    (r'ROE[\s:=]{0,3}\s*(\d+\.?\d*)\s*(%)?', 'roe'),
    (r'(?:revenue|Revenue)[\s:=]{0,3}\s*(\d+\.?\d*)\s*(B|M|bn|mn)?', 'revenue'),
    (r'(?:net income|Net Income)[\s:=]{0,3}\s*(\d+\.?\d*)\s*(B|M|bn|mn)?', 'net_income'),
    (r'(?:market cap|Market Cap|marketcap)[\s:=]{0,3}\s*(\d+\.?\d*)\s*(B|T|M|bn|tn)?', 'market_cap'),
]

# Unit conversion factors (to standard units)
UNIT_MULTIPLIERS = {
    '亿': 1e8, '万': 1e4, '百万': 1e6,
    'B': 1e9, 'M': 1e6, 'K': 1e3,
    'bn': 1e9, 'mn': 1e6,
    'T': 1e12, 'tn': 1e12,
}

# Tolerance for verification (5% relative error)
DEFAULT_TOLERANCE = 0.05

# Fields expressed as percentages in prose. API stores them as fractions
# (e.g. ROE -0.03 == -3%); normalize so unit & magnitude match the displayed value.
PERCENT_FIELDS = {'roe', 'dividend_yield', 'gross_margin', 'net_margin', 'debt_ratio'}


@dataclass
class NumericClaim:
    """A numeric claim extracted from LLM output."""
    field: str           # e.g. "pe", "roe", "revenue"
    raw_value: float     # value as extracted from text (e.g. 4.17)
    normalized_value: float # value adjusted by unit multiplier (e.g. 4.17e8)
    text_context: str    # surrounding text for context
    start_idx: int = -1  # start index in the original text
    end_idx: int = -1    # end index in the original text
    verified: bool = False
    actual: Optional[float] = None
    tolerance: float = DEFAULT_TOLERANCE
    error_pct: Optional[float] = None


@dataclass
class VerificationResult:
    """Result of grounding verification."""
    claims: List[NumericClaim] = field(default_factory=list)
    verified_count: int = 0
    flagged_count: int = 0
    total_count: int = 0
    coverage_score: float = 0.0  # % of claims verified

    @property
    def summary(self) -> str:
        if not self.claims:
            return "无数值声明需要验证"
        return (
            f"验证 {self.total_count} 个数值声明: "
            f"{self.verified_count} 个通过, "
            f"{self.flagged_count} 个未验证/存疑"
        )


class GroundingVerifier:
    """Verifies LLM output numeric claims against snapshot data."""

    def __init__(self, tolerance: float = DEFAULT_TOLERANCE):
        self.tolerance = tolerance
        self._field_map = self._build_field_map()

    def _build_field_map(self) -> Dict[str, List[str]]:
        """Map claim fields to snapshot data paths."""
        return {
            'pe': ['valuation.pe', 'valuation.市盈率-动态', 'quote.trailingPE', 'financials.trailingPE'],
            'pb': ['valuation.pb', 'valuation.市净率', 'quote.priceToBook', 'financials.priceToBook'],
            'roe': ['financials.returnOnEquity', 'financials.roe'],
            'revenue': ['financials.totalRevenue', 'financials.revenue'],
            'net_income': ['financials.netIncome', 'financials净利润'],
            'market_cap': ['quote.marketCap', 'valuation.总市值', 'financials.marketCap'],
            'dividend_yield': ['quote.dividendYield', 'financials.dividendYield'],
            'gross_margin': ['financials.grossMargins', 'financials.毛利率'],
            'net_margin': ['financials.profitMargins', 'financials.净利率'],
            'debt_ratio': ['financials.debtToEquity', 'financials.资产负债率'],
            'eps': ['financials.eps', 'financials.每股收益'],
        }

    def verify(self, llm_output: str, snapshot: Dict) -> VerificationResult:
        """
        Verify all numeric claims in LLM output against snapshot data.

        Args:
            llm_output: The LLM-generated analysis text
            snapshot: Market data snapshot with quote, valuation, financials

        Returns:
            VerificationResult with verified/flagged claims
        """
        claims = self._extract_claims(llm_output)

        for claim in claims:
            actual = self._lookup_field(claim.field, snapshot)
            if actual is not None:
                # Align units: % fields are stored as fractions in the API → scale to %
                if claim.field in PERCENT_FIELDS and abs(actual) <= 1:
                    actual = actual * 100
                claim.actual = actual
                if actual != 0:
                    claim.error_pct = abs(claim.normalized_value - actual) / abs(actual)
                    claim.verified = claim.error_pct <= claim.tolerance
                else:
                    # If actual is 0, only match if claim is also near 0
                    claim.verified = abs(claim.normalized_value) < 1.0
                    claim.error_pct = 0.0 if claim.verified else 1.0
            else:
                # No data to verify against — mark as unverified (not necessarily wrong)
                claim.verified = False

        result = VerificationResult(
            claims=claims,
            verified_count=sum(1 for c in claims if c.verified),
            flagged_count=sum(1 for c in claims if not c.verified),
            total_count=len(claims),
        )
        if result.total_count > 0:
            result.coverage_score = result.verified_count / result.total_count

        return result

    def annotate_output(self, llm_output: str, verification: VerificationResult) -> str:
        """
        Annotate LLM output with verification flags.
        Returns the original text with [⚠️未验证] markers on unverified claims.
        """
        if not verification.flagged_count:
            return llm_output

        annotated = llm_output
        
        # Sort claims by start_idx descending to replace from back to front
        sorted_claims = sorted(
            [c for c in verification.claims if c.start_idx >= 0 and c.end_idx >= 0], 
            key=lambda x: x.start_idx, 
            reverse=True
        )

        annotated_indices = set()

        for claim in sorted_claims:
            # Check if any index in the range is already annotated
            overlap = False
            for idx in range(claim.start_idx, claim.end_idx):
                if idx in annotated_indices:
                    overlap = True
                    break
            if overlap:
                continue

            if not claim.verified and claim.actual is not None:
                num_str = annotated[claim.start_idx:claim.end_idx]
                around = annotated[max(0, claim.start_idx - 1):min(len(annotated), claim.end_idx + 2)]
                if re.search(r'[-~\u2013\u2014\uff5e]\s*\d', around):
                    continue
                # Format actual in the SAME unit as the displayed claim
                if claim.field in PERCENT_FIELDS:
                    actual_fmt = f"{claim.actual:.2f}%"
                elif abs(claim.actual) >= 1e8:
                    actual_fmt = f"{claim.actual / 1e8:.2f}\u4ebf"
                elif abs(claim.actual) >= 1e4:
                    actual_fmt = f"{claim.actual / 1e4:.2f}\u4e07"
                else:
                    actual_fmt = f"{claim.actual:.2f}"
                
                # Mark original indices as annotated
                for idx in range(claim.start_idx, claim.end_idx):
                    annotated_indices.add(idx)

                annotated = (
                    annotated[:claim.start_idx]
                    + f"{num_str}\uff08\u5b9e\u9645{actual_fmt}\uff09"
                    + annotated[claim.end_idx:]
                )
            elif not claim.verified and claim.actual is None:
                pass

        return annotated

    def _extract_claims(self, text: str) -> List[NumericClaim]:
        """Extract numeric claims from LLM output text."""
        claims = []

        for pattern, field_name in NUMERIC_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    raw_val = float(match.group(1))
                    unit = match.group(2) if len(match.groups()) >= 2 else None
                    value = raw_val
                    if unit and unit in UNIT_MULTIPLIERS:
                        value *= UNIT_MULTIPLIERS[unit]
                    
                    # Skip implausible values
                    if raw_val <= 0 and field_name in ('pe', 'pb', 'roe', 'market_cap'):
                        continue
                    if raw_val > 10000 and field_name in ('pe', 'pb', 'roe', 'dividend_yield'):
                        continue

                    # Get surrounding context (50 chars before/after)
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].replace('\n', ' ').strip()

                    claims.append(NumericClaim(
                        field=field_name,
                        raw_value=raw_val,
                        normalized_value=value,
                        text_context=context,
                        start_idx=match.start(1),
                        end_idx=match.end(1)
                    ))
                except (ValueError, IndexError):
                    continue

        # Deduplicate claims by field and normalized_value
        unique_claims = []
        seen = set()
        for claim in claims:
            key = (claim.field, round(claim.normalized_value, 4))
            if key not in seen:
                seen.add(key)
                unique_claims.append(claim)

        return unique_claims

    def _lookup_field(self, field_name: str, snapshot: Dict) -> Optional[float]:
        """Look up a field value from the snapshot data."""
        paths = self._field_map.get(field_name, [])

        for path in paths:
            value = self._resolve_path(snapshot, path)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        return None

    def _resolve_path(self, data: Dict, path: str) -> Optional[object]:
        """Resolve a dotted path like 'valuation.pe' in a nested dict."""
        parts = path.split('.')
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current


# Singleton
grounding_verifier = GroundingVerifier()
