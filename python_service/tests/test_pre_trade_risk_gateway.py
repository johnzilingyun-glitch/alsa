import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.risk.pre_trade import PreTradeRiskGateway, PreTradeRiskRequest, RiskStatus


def test_pre_trade_risk_rejects_low_data_quality():
    gateway = PreTradeRiskGateway()
    request = PreTradeRiskRequest(
        portfolio_id="pf_1",
        signal_id="sig_1",
        symbol="MSFT",
        market="US-Share",
        side="BUY",
        requested_quantity=10,
        requested_notional=4000,
        order_type="LMT",
        limit_price=400,
        as_of_date="2026-05-25T15:00:00Z",
        evidence_quality=0.90,
        data_quality_score=0.70,
        conflict_level="C0",
    )

    result = gateway.check(request)

    assert result.status == RiskStatus.REJECT
    assert result.allowed_quantity == 0
    assert result.blocking_rules[0].rule_id == "DATA_QUALITY_MINIMUM"


def test_pre_trade_risk_rejects_high_conflict_level():
    gateway = PreTradeRiskGateway()
    request = PreTradeRiskRequest(
        portfolio_id="pf_1",
        signal_id="sig_1",
        symbol="MSFT",
        market="US-Share",
        side="BUY",
        requested_quantity=10,
        requested_notional=4000,
        order_type="LMT",
        limit_price=400,
        as_of_date="2026-05-25T15:00:00Z",
        evidence_quality=0.90,
        data_quality_score=0.95,
        conflict_level="C3",
    )

    result = gateway.check(request)

    assert result.status == RiskStatus.REJECT
    assert result.blocking_rules[0].rule_id == "AGENT_CONFLICT_BLOCK"


def test_pre_trade_risk_passes_clean_research_intent_without_live_execution():
    gateway = PreTradeRiskGateway()
    request = PreTradeRiskRequest(
        portfolio_id="pf_1",
        signal_id="sig_1",
        symbol="MSFT",
        market="US-Share",
        side="BUY",
        requested_quantity=10,
        requested_notional=4000,
        order_type="LMT",
        limit_price=400,
        as_of_date="2026-05-25T15:00:00Z",
        evidence_quality=0.90,
        data_quality_score=0.95,
        conflict_level="C1",
    )

    result = gateway.check(request)

    assert result.status == RiskStatus.PASS
    assert result.allowed_quantity == 10
    assert result.live_execution_allowed is False
