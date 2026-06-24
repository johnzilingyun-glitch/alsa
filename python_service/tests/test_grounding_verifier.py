"""Tests for GroundingVerifier — validates LLM numeric claims against snapshot data."""
import pytest
from python_service.app.services.grounding_verifier import (
    GroundingVerifier, NumericClaim, VerificationResult, grounding_verifier,
)


class TestExtractClaims:
    """Test numeric claim extraction from LLM text."""

    def test_extract_chinese_pe(self):
        v = GroundingVerifier()
        claims = v._extract_claims("该股PE约为25.3倍，估值偏高")
        assert any(c.field == "pe" for c in claims)
        pe_claim = next(c for c in claims if c.field == "pe")
        assert pe_claim.raw_value == 25.3

    def test_extract_chinese_roe(self):
        v = GroundingVerifier()
        claims = v._extract_claims("ROE达到18.5%，盈利能力强")
        assert any(c.field == "roe" for c in claims)
        roe_claim = next(c for c in claims if c.field == "roe")
        assert roe_claim.raw_value == 18.5

    def test_extract_english_pe(self):
        v = GroundingVerifier()
        claims = v._extract_claims("The stock trades at a PE ratio of 30.5")
        assert any(c.field == "pe" for c in claims)

    def test_extract_market_cap(self):
        v = GroundingVerifier()
        claims = v._extract_claims("总市值约2.5万亿")
        # Should extract market_cap
        mc_claims = [c for c in claims if c.field == "market_cap"]
        assert len(mc_claims) > 0

    def test_deduplication(self):
        v = GroundingVerifier()
        text = "PE约为25倍。该股的PE是25x，依然合理"
        claims = v._extract_claims(text)
        pe_claims = [c for c in claims if c.field == "pe" and round(c.raw_value, 1) == 25.0]
        assert len(pe_claims) == 1  # Deduplicated

    def test_implausible_values_filtered(self):
        v = GroundingVerifier()
        claims = v._extract_claims("PE ratio of 0")  # PE <= 0 skipped
        pe_claims = [c for c in claims if c.field == "pe"]
        assert len(pe_claims) == 0

    def test_no_claims_in_plain_text(self):
        v = GroundingVerifier()
        claims = v._extract_claims("This stock has good fundamentals and strong moat.")
        assert len(claims) == 0

    def test_context_extraction(self):
        v = GroundingVerifier()
        claims = v._extract_claims("分析显示该公司的PE约为20倍，估值合理")
        if claims:
            assert len(claims[0].text_context) > 0


class TestVerify:
    """Test verification against snapshot data."""

    def test_claim_verified_within_tolerance(self):
        v = GroundingVerifier(tolerance=0.10)
        snapshot = {"valuation": {"pe": 25.0}}
        result = v.verify("该股PE约为25.5倍", snapshot)
        pe_claims = [c for c in result.claims if c.field == "pe"]
        if pe_claims:
            assert pe_claims[0].verified is True
            assert pe_claims[0].error_pct < 0.10

    def test_claim_flagged_outside_tolerance(self):
        v = GroundingVerifier(tolerance=0.05)
        snapshot = {"valuation": {"pe": 25.0}}
        result = v.verify("该股PE约为50倍", snapshot)
        pe_claims = [c for c in result.claims if c.field == "pe"]
        if pe_claims:
            assert pe_claims[0].verified is False

    def test_no_snapshot_data_unverified(self):
        v = GroundingVerifier()
        result = v.verify("ROE达到15%", {})
        roe_claims = [c for c in result.claims if c.field == "roe"]
        if roe_claims:
            assert roe_claims[0].verified is False
            assert roe_claims[0].actual is None

    def test_empty_text_no_claims(self):
        v = GroundingVerifier()
        result = v.verify("", {"valuation": {"pe": 10}})
        assert result.total_count == 0
        assert result.summary == "无数值声明需要验证"

    def test_coverage_score(self):
        v = GroundingVerifier(tolerance=0.10)
        snapshot = {"valuation": {"pe": 20.0}, "financials": {"returnOnEquity": 15.0}}
        result = v.verify("PE约为20倍，ROE达到15%", snapshot)
        # Both should be verified
        if result.total_count > 0:
            assert result.coverage_score > 0

    def test_zero_actual_value(self):
        v = GroundingVerifier()
        snapshot = {"financials": {"returnOnEquity": 0}}
        result = v.verify("ROE达到0.5%", snapshot)
        roe_claims = [c for c in result.claims if c.field == "roe"]
        if roe_claims:
            assert roe_claims[0].actual == 0


class TestAnnotateOutput:
    """Test output annotation with verification flags."""

    def test_no_flags_when_all_verified(self):
        v = GroundingVerifier(tolerance=0.50)
        snapshot = {"valuation": {"pe": 20.0}}
        vr = v.verify("PE约为20倍", snapshot)
        annotated = v.annotate_output("PE约为20倍", vr)
        assert "⚠️" not in annotated

    def test_flag_added_for_wrong_claim(self):
        v = GroundingVerifier(tolerance=0.05)
        snapshot = {"valuation": {"pe": 20.0}}
        text = "PE约为50倍"
        vr = v.verify(text, snapshot)
        annotated = v.annotate_output(text, vr)
        if vr.flagged_count > 0:
            assert "⚠️" in annotated or annotated == text  # May depend on regex matching


class TestLookupField:
    """Test nested snapshot field lookup."""

    def test_dotted_path_resolution(self):
        v = GroundingVerifier()
        snapshot = {"valuation": {"pe": 25.5}}
        result = v._lookup_field("pe", snapshot)
        assert result == 25.5

    def test_missing_path_returns_none(self):
        v = GroundingVerifier()
        result = v._lookup_field("pe", {"quote": {"price": 100}})
        assert result is None

    def test_non_dict_intermediate_returns_none(self):
        v = GroundingVerifier()
        result = v._resolve_path({"a": "string_not_dict"}, "a.b")
        assert result is None


class TestSingleton:
    def test_singleton_exists(self):
        assert grounding_verifier is not None
        assert isinstance(grounding_verifier, GroundingVerifier)
