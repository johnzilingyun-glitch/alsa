"""Valuation Module — multi-method stock valuation with probability weighting.

Provides:
- DCF (Discounted Cash Flow) valuation
- Relative PE valuation
- EV/EBITDA valuation
- PEG ratio analysis
- Probability-weighted target price with confidence intervals
"""
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ValuationResult:
    """Result of a single valuation method."""
    method: str
    fair_value: float
    confidence: float  # 0-1
    weight: float      # Weight in probability averaging
    assumptions: Dict = field(default_factory=dict)

    @property
    def weighted_value(self) -> float:
        return self.fair_value * self.weight


@dataclass
class ValuationReport:
    """Complete valuation report with multiple methods."""
    symbol: str
    current_price: float
    methods: List[ValuationResult] = field(default_factory=list)
    probability_weighted_price: float = 0.0
    confidence_interval: Tuple[float, float] = (0.0, 0.0)
    recommendation: str = "Hold"
    upside_pct: float = 0.0
    downside_pct: float = 0.0

    def compute_derived(self):
        """Compute derived metrics from methods."""
        if not self.methods:
            return

        # Probability-weighted price
        total_weight = sum(m.weight for m in self.methods)
        if total_weight > 0:
            self.probability_weighted_price = sum(m.weighted_value for m in self.methods) / total_weight

        # Confidence interval (weighted std dev)
        if len(self.methods) > 1:
            values = [m.fair_value for m in self.methods]
            weights = [m.weight for m in self.methods]
            weighted_mean = np.average(values, weights=weights)
            weighted_var = np.average((np.array(values) - weighted_mean) ** 2, weights=weights)
            weighted_std = np.sqrt(weighted_var)
            self.confidence_interval = (
                round(weighted_mean - 1.96 * weighted_std, 2),
                round(weighted_mean + 1.96 * weighted_std, 2),
            )

        # Upside/downside
        if self.current_price > 0:
            self.upside_pct = (self.probability_weighted_price / self.current_price - 1) * 100
            self.downside_pct = -self.upside_pct  # Symmetric for simplicity

        # Recommendation
        if self.upside_pct > 20:
            self.recommendation = "Strong Buy"
        elif self.upside_pct > 10:
            self.recommendation = "Buy"
        elif self.upside_pct > -10:
            self.recommendation = "Hold"
        elif self.upside_pct > -20:
            self.recommendation = "Sell"
        else:
            self.recommendation = "Strong Sell"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "probability_weighted_price": round(self.probability_weighted_price, 2),
            "confidence_interval": self.confidence_interval,
            "recommendation": self.recommendation,
            "upside_pct": round(self.upside_pct, 2),
            "methods": [
                {
                    "method": m.method,
                    "fair_value": round(m.fair_value, 2),
                    "confidence": round(m.confidence, 2),
                    "weight": round(m.weight, 2),
                    "assumptions": m.assumptions,
                }
                for m in self.methods
            ],
        }


class ValuationEngine:
    """
    Multi-method stock valuation engine.
    
    Combines DCF, relative PE, EV/EBITDA, and PEG methods
    with probability weighting for robust target prices.
    """

    def dcf_valuation(
        self,
        fcf_base: float,
        growth_rates: List[float],
        terminal_growth: float,
        wacc: float,
        shares_outstanding: float,
        net_debt: float,
    ) -> ValuationResult:
        """
        Discounted Cash Flow valuation.
        
        Args:
            fcf_base: Current year free cash flow
            growth_rates: List of yearly growth rates (e.g., [0.15, 0.12, 0.10, 0.08, 0.06])
            terminal_growth: Perpetual growth rate (must be < WACC)
            wacc: Weighted Average Cost of Capital
            shares_outstanding: Shares outstanding in millions
            net_debt: Net debt in millions (debt - cash)
            
        Returns:
            ValuationResult with fair value per share
        """
        if wacc <= terminal_growth:
            return ValuationResult(
                method="DCF",
                fair_value=0,
                confidence=0.1,
                weight=0,
                assumptions={"error": "WACC must be > terminal growth"},
            )

        # Project FCF for each year
        fcf_projections = []
        current_fcf = fcf_base
        for growth in growth_rates:
            current_fcf *= (1 + growth)
            fcf_projections.append(current_fcf)

        # Terminal value (Gordon Growth Model)
        terminal_value = fcf_projections[-1] * (1 + terminal_growth) / (wacc - terminal_growth)

        # Discount all cash flows to present
        discounted_fcf = sum(
            fcf / (1 + wacc) ** (i + 1)
            for i, fcf in enumerate(fcf_projections)
        )
        discounted_terminal = terminal_value / (1 + wacc) ** len(growth_rates)

        # Enterprise value → Equity value → Per share
        enterprise_value = discounted_fcf + discounted_terminal
        equity_value = enterprise_value - net_debt
        fair_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

        return ValuationResult(
            method="DCF",
            fair_value=max(0, fair_value_per_share),
            confidence=0.7,
            weight=0.35,
            assumptions={
                "wacc": wacc,
                "terminal_growth": terminal_growth,
                "projection_years": len(growth_rates),
                "fcf_base": fcf_base,
            },
        )

    def relative_pe_valuation(
        self,
        target_pe: float,
        target_eps: float,
        peer_avg_pe: float,
        growth_rate: float,
    ) -> ValuationResult:
        """
        Relative PE valuation based on peer comparison.
        
        Args:
            target_pe: Current PE of the target stock
            target_eps: Trailing EPS
            peer_avg_pe: Average PE of peer group
            growth_rate: Expected earnings growth rate
            
        Returns:
            ValuationResult with fair value per share
        """
        # Adjusted PE: blend current PE with peer PE, adjusted for growth
        growth_premium = min(growth_rate * 10, 10)  # Cap growth premium
        adjusted_pe = peer_avg_pe * (1 + growth_premium / 100)

        fair_value = target_eps * adjusted_pe

        # Confidence: higher if PE is close to peers
        pe_ratio = target_pe / peer_avg_pe if peer_avg_pe > 0 else 1
        confidence = max(0.3, min(0.8, 1 - abs(pe_ratio - 1) * 0.5))

        return ValuationResult(
            method="Relative PE",
            fair_value=max(0, fair_value),
            confidence=confidence,
            weight=0.30,
            assumptions={
                "target_pe": target_pe,
                "peer_avg_pe": peer_avg_pe,
                "adjusted_pe": adjusted_pe,
                "growth_premium": growth_premium,
            },
        )

    def ev_ebitda_valuation(
        self,
        ebitda: float,
        ev_ebitda_multiple: float,
        net_debt: float,
        shares_outstanding: float,
    ) -> ValuationResult:
        """
        EV/EBITDA valuation.
        
        Args:
            ebitda: Earnings Before Interest, Tax, Depreciation, Amortization
            ev_ebitda_multiple: Target EV/EBITDA multiple
            net_debt: Net debt
            shares_outstanding: Shares outstanding
            
        Returns:
            ValuationResult with fair value per share
        """
        enterprise_value = ebitda * ev_ebitda_multiple
        equity_value = enterprise_value - net_debt
        fair_value = equity_value / shares_outstanding if shares_outstanding > 0 else 0

        return ValuationResult(
            method="EV/EBITDA",
            fair_value=max(0, fair_value),
            confidence=0.6,
            weight=0.20,
            assumptions={
                "ebitda": ebitda,
                "ev_ebitda_multiple": ev_ebitda_multiple,
            },
        )

    def peg_valuation(
        self,
        eps: float,
        pe: float,
        earnings_growth_pct: float,
        fair_peg: float = 1.0,
    ) -> ValuationResult:
        """
        PEG ratio valuation.
        
        PEG = PE / Earnings Growth Rate
        Fair PEG ≈ 1.0 for reasonable valuation
        
        Args:
            eps: Earnings per share
            pe: Current PE ratio
            earnings_growth_pct: Earnings growth rate (%)
            fair_peg: Target PEG ratio (default 1.0)
            
        Returns:
            ValuationResult with fair value per share
        """
        if earnings_growth_pct <= 0:
            return ValuationResult(
                method="PEG",
                fair_value=0,
                confidence=0.2,
                weight=0,
                assumptions={"error": "Negative growth not suitable for PEG"},
            )

        fair_pe = fair_peg * earnings_growth_pct
        fair_value = eps * fair_pe

        # Confidence based on growth consistency
        confidence = min(0.7, earnings_growth_pct / 30)  # Higher growth = less certain

        return ValuationResult(
            method="PEG",
            fair_value=max(0, fair_value),
            confidence=confidence,
            weight=0.15,
            assumptions={
                "current_pe": pe,
                "fair_pe": fair_pe,
                "earnings_growth_pct": earnings_growth_pct,
                "fair_peg": fair_peg,
            },
        )

    def compute_target_price(
        self,
        symbol: str,
        current_price: float,
        fcf_base: float = None,
        growth_rates: List[float] = None,
        terminal_growth: float = 0.03,
        wacc: float = 0.09,
        shares_outstanding: float = None,
        net_debt: float = 0,
        target_pe: float = None,
        eps: float = None,
        peer_avg_pe: float = None,
        earnings_growth_pct: float = None,
        ebitda: float = None,
        ev_ebitda_multiple: float = None,
    ) -> ValuationReport:
        """
        Compute probability-weighted target price from multiple valuation methods.
        
        Only runs methods where sufficient data is provided.
        """
        report = ValuationReport(symbol=symbol, current_price=current_price)

        # DCF
        if fcf_base and growth_rates and shares_outstanding:
            result = self.dcf_valuation(fcf_base, growth_rates, terminal_growth, wacc, shares_outstanding, net_debt)
            if result.fair_value > 0:
                report.methods.append(result)

        # Relative PE
        if target_pe and eps and peer_avg_pe and earnings_growth_pct:
            result = self.relative_pe_valuation(target_pe, eps, peer_avg_pe, earnings_growth_pct)
            if result.fair_value > 0:
                report.methods.append(result)

        # EV/EBITDA
        if ebitda and ev_ebitda_multiple and shares_outstanding:
            result = self.ev_ebitda_valuation(ebitda, ev_ebitda_multiple, net_debt, shares_outstanding)
            if result.fair_value > 0:
                report.methods.append(result)

        # PEG
        if eps and target_pe and earnings_growth_pct:
            result = self.peg_valuation(eps, target_pe, earnings_growth_pct)
            if result.fair_value > 0:
                report.methods.append(result)

        # Normalize weights
        if report.methods:
            total_weight = sum(m.weight for m in report.methods)
            for m in report.methods:
                m.weight = m.weight / total_weight

        report.compute_derived()
        return report


# Singleton
valuation_engine = ValuationEngine()
