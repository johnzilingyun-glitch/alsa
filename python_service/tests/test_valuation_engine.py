"""Tests for ValuationEngine — multi-method stock valuation."""
import pytest
from python_service.app.quant.valuation import (
    ValuationEngine, ValuationResult, ValuationReport, valuation_engine,
)


class TestDCFValuation:
    """Test DCF valuation method."""

    def test_basic_dcf(self):
        engine = ValuationEngine()
        result = engine.dcf_valuation(
            fcf_base=1000,
            growth_rates=[0.15, 0.12, 0.10, 0.08, 0.06],
            terminal_growth=0.03,
            wacc=0.09,
            shares_outstanding=100,
            net_debt=500,
        )
        assert result.method == "DCF"
        assert result.fair_value > 0
        assert result.confidence == 0.7
        assert result.weight == 0.35

    def test_dcf_wacc_below_terminal_growth(self):
        engine = ValuationEngine()
        result = engine.dcf_valuation(
            fcf_base=1000,
            growth_rates=[0.10],
            terminal_growth=0.10,
            wacc=0.05,  # wacc < terminal_growth
            shares_outstanding=100,
            net_debt=0,
        )
        assert result.fair_value == 0
        assert result.weight == 0
        assert "error" in result.assumptions

    def test_dcf_zero_shares(self):
        engine = ValuationEngine()
        result = engine.dcf_valuation(
            fcf_base=1000,
            growth_rates=[0.10],
            terminal_growth=0.03,
            wacc=0.09,
            shares_outstanding=0,
            net_debt=0,
        )
        assert result.fair_value == 0


class TestRelativePEValuation:
    """Test Relative PE valuation."""

    def test_basic_relative_pe(self):
        engine = ValuationEngine()
        result = engine.relative_pe_valuation(
            target_pe=20,
            target_eps=5.0,
            peer_avg_pe=18,
            growth_rate=0.15,
        )
        assert result.method == "Relative PE"
        assert result.fair_value > 0
        assert 0.3 <= result.confidence <= 0.8

    def test_zero_peer_pe(self):
        engine = ValuationEngine()
        result = engine.relative_pe_valuation(
            target_pe=20,
            target_eps=5.0,
            peer_avg_pe=0,
            growth_rate=0.10,
        )
        # Should handle gracefully
        assert result.fair_value == 0

    def test_growth_premium_capped(self):
        engine = ValuationEngine()
        result = engine.relative_pe_valuation(
            target_pe=20,
            target_eps=5.0,
            peer_avg_pe=18,
            growth_rate=5.0,  # Very high growth
        )
        # Growth premium capped at 10
        assert result.assumptions["growth_premium"] <= 10


class TestEVEBITDAValuation:
    """Test EV/EBITDA valuation."""

    def test_basic_ev_ebitda(self):
        engine = ValuationEngine()
        result = engine.ev_ebitda_valuation(
            ebitda=5000,
            ev_ebitda_multiple=12,
            net_debt=10000,
            shares_outstanding=1000,
        )
        assert result.method == "EV/EBITDA"
        # EV = 5000*12 = 60000, Equity = 60000-10000 = 50000, per share = 50
        assert result.fair_value == pytest.approx(50.0)

    def test_negative_equity_value_clamped(self):
        engine = ValuationEngine()
        result = engine.ev_ebitda_valuation(
            ebitda=100,
            ev_ebitda_multiple=5,
            net_debt=1000,  # net_debt > EV
            shares_outstanding=100,
        )
        assert result.fair_value == 0  # Clamped to 0


class TestPEGValuation:
    """Test PEG valuation."""

    def test_basic_peg(self):
        engine = ValuationEngine()
        result = engine.peg_valuation(
            eps=3.0,
            pe=20,
            earnings_growth_pct=15,
        )
        assert result.method == "PEG"
        # fair_pe = 1.0 * 15 = 15, fair_value = 3.0 * 15 = 45
        assert result.fair_value == pytest.approx(45.0)

    def test_negative_growth_rejected(self):
        engine = ValuationEngine()
        result = engine.peg_valuation(
            eps=3.0,
            pe=20,
            earnings_growth_pct=-5,
        )
        assert result.fair_value == 0
        assert result.weight == 0
        assert "error" in result.assumptions

    def test_custom_fair_peg(self):
        engine = ValuationEngine()
        result = engine.peg_valuation(
            eps=3.0,
            pe=20,
            earnings_growth_pct=15,
            fair_peg=1.5,
        )
        # fair_pe = 1.5 * 15 = 22.5, fair_value = 3.0 * 22.5 = 67.5
        assert result.fair_value == pytest.approx(67.5)


class TestComputeTargetPrice:
    """Test integrated target price computation."""

    def test_all_methods_combined(self):
        engine = ValuationEngine()
        report = engine.compute_target_price(
            symbol="600519",
            current_price=1800,
            fcf_base=500,
            growth_rates=[0.12, 0.10, 0.08],
            terminal_growth=0.03,
            wacc=0.09,
            shares_outstanding=1256,
            net_debt=-500,
            target_pe=30,
            eps=60,
            peer_avg_pe=25,
            earnings_growth_pct=12,
            ebitda=80000,
            ev_ebitda_multiple=20,
        )
        assert report.symbol == "600519"
        assert len(report.methods) > 0
        assert report.probability_weighted_price > 0
        assert report.recommendation in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]

    def test_partial_data_only_available_methods(self):
        engine = ValuationEngine()
        report = engine.compute_target_price(
            symbol="AAPL",
            current_price=150,
            target_pe=25,
            eps=6.0,
            peer_avg_pe=22,
            earnings_growth_pct=10,
        )
        method_names = [m.method for m in report.methods]
        assert "Relative PE" in method_names
        assert "PEG" in method_names
        assert "DCF" not in method_names  # No FCF data

    def test_no_data_empty_methods(self):
        engine = ValuationEngine()
        report = engine.compute_target_price(
            symbol="TEST",
            current_price=100,
        )
        assert len(report.methods) == 0
        assert report.probability_weighted_price == 0

    def test_weights_normalized(self):
        engine = ValuationEngine()
        report = engine.compute_target_price(
            symbol="TEST",
            current_price=100,
            target_pe=20,
            eps=5.0,
            peer_avg_pe=18,
            earnings_growth_pct=15,
        )
        if report.methods:
            total_weight = sum(m.weight for m in report.methods)
            assert total_weight == pytest.approx(1.0, abs=0.01)


class TestValuationReport:
    """Test ValuationReport derived metrics."""

    def test_recommendation_strong_buy(self):
        report = ValuationReport(symbol="X", current_price=100)
        report.methods = [ValuationResult(method="A", fair_value=130, confidence=0.8, weight=1.0)]
        report.compute_derived()
        assert report.recommendation == "Strong Buy"
        assert report.upside_pct > 20

    def test_recommendation_strong_sell(self):
        report = ValuationReport(symbol="X", current_price=100)
        report.methods = [ValuationResult(method="A", fair_value=70, confidence=0.8, weight=1.0)]
        report.compute_derived()
        assert report.recommendation == "Strong Sell"

    def test_to_dict(self):
        report = ValuationReport(symbol="AAPL", current_price=150)
        report.methods = [ValuationResult(method="DCF", fair_value=180, confidence=0.7, weight=0.5)]
        report.compute_derived()
        d = report.to_dict()
        assert d["symbol"] == "AAPL"
        assert len(d["methods"]) == 1
        assert d["methods"][0]["method"] == "DCF"

    def test_confidence_interval_with_multiple_methods(self):
        report = ValuationReport(symbol="X", current_price=100)
        report.methods = [
            ValuationResult(method="A", fair_value=120, confidence=0.8, weight=0.5),
            ValuationResult(method="B", fair_value=140, confidence=0.6, weight=0.5),
        ]
        report.compute_derived()
        low, high = report.confidence_interval
        assert low < high
        assert low > 0
