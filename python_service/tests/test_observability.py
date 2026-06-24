"""P2-1: Observability — metrics collection and audit logging.

Tests for:
- MetricsCollector: records API latency, LLM success/failure, data source health
- AuditLog: records all critical actions (job creation, signal, risk check, order)
- Metrics aggregation for dashboard queries
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from python_service.app.observability.metrics import MetricsCollector
from python_service.app.observability.audit import AuditLogger, AuditAction


class TestMetricsCollector:
    """System and business metrics collection."""

    def test_record_api_latency(self):
        mc = MetricsCollector()
        mc.record("api_latency_ms", 150.0, tags={"endpoint": "/api/analysis/jobs", "method": "POST"})
        mc.record("api_latency_ms", 230.0, tags={"endpoint": "/api/analysis/jobs", "method": "POST"})
        stats = mc.get_stats("api_latency_ms")
        assert stats["count"] == 2
        assert stats["avg"] == pytest.approx(190.0)
        assert stats["max"] == 230.0

    def test_record_llm_call_success(self):
        mc = MetricsCollector()
        mc.record("llm_call", 1.0, tags={"model": "deepseek-v4", "status": "success"})
        mc.record("llm_call", 1.0, tags={"model": "deepseek-v4", "status": "success"})
        mc.record("llm_call", 1.0, tags={"model": "deepseek-v4", "status": "error"})
        rate = mc.get_rate("llm_call", success_tag="status", success_value="success")
        assert rate == pytest.approx(2 / 3)

    def test_record_data_source_health(self):
        mc = MetricsCollector()
        mc.record("data_source", 1.0, tags={"vendor": "akshare", "status": "success"})
        mc.record("data_source", 1.0, tags={"vendor": "akshare", "status": "timeout"})
        rate = mc.get_rate("data_source", success_tag="status", success_value="success")
        assert rate == 0.5

    def test_record_risk_rejection(self):
        mc = MetricsCollector()
        mc.record("risk_check", 1.0, tags={"result": "PASS"})
        mc.record("risk_check", 1.0, tags={"result": "REJECT"})
        mc.record("risk_check", 1.0, tags={"result": "PASS"})
        reject_rate = mc.get_rate("risk_check", success_tag="result", success_value="REJECT")
        assert reject_rate == pytest.approx(1 / 3)

    def test_metrics_filtered_by_tags(self):
        mc = MetricsCollector()
        mc.record("api_latency_ms", 100.0, tags={"endpoint": "/health"})
        mc.record("api_latency_ms", 500.0, tags={"endpoint": "/api/analysis"})
        stats = mc.get_stats("api_latency_ms", filter_tags={"endpoint": "/api/analysis"})
        assert stats["count"] == 1
        assert stats["avg"] == 500.0


class TestAuditLogger:
    """Audit logging for critical system actions."""

    def test_log_job_creation(self):
        logger = AuditLogger()
        logger.log(
            action=AuditAction.JOB_CREATED,
            actor="system",
            details={"job_id": "job_abc123", "symbol": "MSFT", "level": "deep"},
        )
        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].action == AuditAction.JOB_CREATED
        assert entries[0].details["job_id"] == "job_abc123"
        assert entries[0].timestamp is not None

    def test_log_signal_generation(self):
        logger = AuditLogger()
        logger.log(
            action=AuditAction.SIGNAL_GENERATED,
            actor="decision_court",
            details={"signal_id": "sig_001", "symbol": "MSFT", "verdict": "buy", "strength": 0.72},
        )
        entries = logger.get_entries(action=AuditAction.SIGNAL_GENERATED)
        assert len(entries) == 1

    def test_log_risk_decision(self):
        logger = AuditLogger()
        logger.log(
            action=AuditAction.RISK_CHECK,
            actor="risk_gateway",
            details={"signal_id": "sig_001", "status": "REJECT", "rules": ["DATA_QUALITY_MINIMUM"]},
        )
        entries = logger.get_entries(action=AuditAction.RISK_CHECK)
        assert entries[0].details["status"] == "REJECT"

    def test_log_kill_switch_triggered(self):
        logger = AuditLogger()
        logger.log(
            action=AuditAction.KILL_SWITCH_TRIGGERED,
            actor="risk_monitor",
            details={"trigger": "DAILY_LOSS_EXCEEDED", "loss_pct": -3.2},
        )
        entries = logger.get_entries(action=AuditAction.KILL_SWITCH_TRIGGERED)
        assert len(entries) == 1

    def test_log_human_approval(self):
        logger = AuditLogger()
        logger.log(
            action=AuditAction.HUMAN_APPROVAL,
            actor="user_001",
            details={"approval_id": "appr_001", "decision": "approved_with_resize"},
        )
        entries = logger.get_entries(action=AuditAction.HUMAN_APPROVAL)
        assert entries[0].actor == "user_001"

    def test_entries_ordered_by_time(self):
        logger = AuditLogger()
        logger.log(action=AuditAction.JOB_CREATED, actor="a", details={"order": 1})
        logger.log(action=AuditAction.SIGNAL_GENERATED, actor="b", details={"order": 2})
        logger.log(action=AuditAction.RISK_CHECK, actor="c", details={"order": 3})
        entries = logger.get_entries()
        assert len(entries) == 3
        # Should be in chronological order
        assert entries[0].details["order"] == 1
        assert entries[2].details["order"] == 3
