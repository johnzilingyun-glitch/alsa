"""P0-5: Pre-trade risk gateway comprehensive tests.

Ensures the Risk Gateway enforces:
- Data quality minimum
- Evidence quality minimum
- Agent conflict level blocking
- Single name weight limit
- Daily new exposure limit
- All rules produce auditable rejection records
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.risk.pre_trade import (
    PreTradeRiskGateway,
    PreTradeRiskRequest,
    RiskStatus,
)


def _make_request(**overrides) -> PreTradeRiskRequest:
    """Factory for a valid baseline request."""
    defaults = {
        "portfolio_id": "port_001",
        "signal_id": "sig_001",
        "symbol": "MSFT",
        "market": "US-Share",
        "side": "BUY",
        "requested_quantity": 100,
        "requested_notional": 42000.0,
        "order_type": "LIMIT",
        "limit_price": 420.0,
        "as_of_date": "2026-05-25T16:00:00-04:00",
        "evidence_quality": 0.85,
        "data_quality_score": 0.92,
        "conflict_level": "C0",
    }
    defaults.update(overrides)
    return PreTradeRiskRequest(**defaults)


class TestPreTradeRiskGateway:
    """Tests for all pre-trade risk rules."""

    def test_clean_request_passes(self):
        gw = PreTradeRiskGateway()
        result = gw.check(_make_request())
        assert result.status == RiskStatus.PASS
        assert result.blocking_rules == []
        assert result.allowed_quantity == 100

    def test_low_data_quality_blocks(self):
        gw = PreTradeRiskGateway(min_data_quality=0.85)
        result = gw.check(_make_request(data_quality_score=0.78))
        assert result.status == RiskStatus.REJECT
        assert any(r.rule_id == "DATA_QUALITY_MINIMUM" for r in result.blocking_rules)

    def test_low_evidence_quality_blocks(self):
        gw = PreTradeRiskGateway(min_evidence_quality=0.60)
        result = gw.check(_make_request(evidence_quality=0.45))
        assert result.status == RiskStatus.REJECT
        assert any(r.rule_id == "EVIDENCE_QUALITY_MINIMUM" for r in result.blocking_rules)

    def test_c3_conflict_blocks(self):
        gw = PreTradeRiskGateway()
        result = gw.check(_make_request(conflict_level="C3"))
        assert result.status == RiskStatus.REJECT
        assert any(r.rule_id == "AGENT_CONFLICT_BLOCK" for r in result.blocking_rules)

    def test_c4_conflict_blocks(self):
        gw = PreTradeRiskGateway()
        result = gw.check(_make_request(conflict_level="C4"))
        assert result.status == RiskStatus.REJECT

    def test_c2_conflict_requires_human_review(self):
        gw = PreTradeRiskGateway()
        result = gw.check(_make_request(conflict_level="C2"))
        assert result.status == RiskStatus.PASS
        assert result.human_review_required is True

    # --- NEW: Single name weight limit ---

    def test_single_name_weight_exceeds_limit_blocks(self):
        """Order that would make single name exceed max weight must be rejected."""
        gw = PreTradeRiskGateway(max_single_name_pct=5.0)
        # Trying to buy 100k in a 1M portfolio = 10% weight, exceeds 5% limit
        result = gw.check(
            _make_request(
                requested_notional=100_000.0,
                portfolio_value=1_000_000.0,
                existing_position_notional=0.0,
            )
        )
        assert result.status == RiskStatus.REJECT
        assert any(r.rule_id == "SINGLE_NAME_WEIGHT_LIMIT" for r in result.blocking_rules)

    def test_single_name_within_limit_passes(self):
        """Order within weight limit passes."""
        gw = PreTradeRiskGateway(max_single_name_pct=5.0)
        result = gw.check(
            _make_request(
                requested_notional=40_000.0,
                portfolio_value=1_000_000.0,
                existing_position_notional=0.0,
            )
        )
        assert result.status == RiskStatus.PASS

    # --- NEW: Daily new exposure limit ---

    def test_daily_exposure_limit_blocks(self):
        """If daily new exposure budget is exhausted, new orders are blocked."""
        gw = PreTradeRiskGateway(max_daily_new_exposure_pct=3.0)
        # Already deployed 2.5% today, trying to add 1% more (total 3.5% > 3%)
        result = gw.check(
            _make_request(
                requested_notional=10_000.0,
                portfolio_value=1_000_000.0,
                daily_new_exposure_so_far=25_000.0,
            )
        )
        assert result.status == RiskStatus.REJECT
        assert any(r.rule_id == "DAILY_EXPOSURE_LIMIT" for r in result.blocking_rules)

    def test_multiple_violations_all_reported(self):
        """All blocking rules are reported, not just the first one."""
        gw = PreTradeRiskGateway()
        result = gw.check(
            _make_request(data_quality_score=0.50, evidence_quality=0.30, conflict_level="C4")
        )
        assert result.status == RiskStatus.REJECT
        assert len(result.blocking_rules) >= 3

    def test_live_execution_never_allowed_by_default(self):
        """Even passing requests don't get live execution without explicit enable."""
        gw = PreTradeRiskGateway()
        result = gw.check(_make_request())
        assert result.live_execution_allowed is False
