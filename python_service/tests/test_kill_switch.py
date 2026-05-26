"""P0-6: Kill Switch mechanism tests.

The kill switch must:
- Transition system to read-only mode when triggered
- Block all new order submissions
- Allow risk-reducing actions (sell/cover) with human confirmation
- Record the trigger event with timestamp and reason
- Be triggerable by multiple conditions (loss, heartbeat, manual)
- Be resettable only via explicit human action
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from python_service.app.risk.kill_switch import (
    KillSwitch,
    KillSwitchState,
    KillSwitchTrigger,
)


class TestKillSwitch:
    """Verify kill switch behavior."""

    def test_initial_state_is_active(self):
        ks = KillSwitch()
        assert ks.state == KillSwitchState.ACTIVE

    def test_trigger_transitions_to_killed(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.DAILY_LOSS_EXCEEDED, reason="Daily loss -3.2% exceeds -2% limit")
        assert ks.state == KillSwitchState.KILLED

    def test_killed_state_blocks_new_orders(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.MANUAL, reason="Risk officer triggered")
        assert ks.can_submit_order() is False

    def test_killed_state_allows_risk_reducing(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.BROKER_HEARTBEAT_LOST, reason="No heartbeat for 60s")
        # Selling existing position reduces risk
        assert ks.can_reduce_risk() is True

    def test_killed_state_allows_cancel(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.DATA_SOURCE_ANOMALY, reason="5 sources failed")
        assert ks.can_cancel_order() is True

    def test_trigger_records_event(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.RISK_SERVICE_UNAVAILABLE, reason="Risk gateway timeout")
        assert len(ks.events) == 1
        ev = ks.events[0]
        assert ev.trigger == KillSwitchTrigger.RISK_SERVICE_UNAVAILABLE
        assert "timeout" in ev.reason
        assert ev.timestamp is not None

    def test_cannot_reset_without_human_action(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.MANUAL, reason="test")
        # Attempting reset without approval_id fails
        with pytest.raises(ValueError, match="approval"):
            ks.reset(approval_id=None)
        assert ks.state == KillSwitchState.KILLED

    def test_reset_with_approval_restores_active(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.MANUAL, reason="test")
        ks.reset(approval_id="appr_001")
        assert ks.state == KillSwitchState.ACTIVE
        assert ks.can_submit_order() is True

    def test_multiple_triggers_accumulate_events(self):
        ks = KillSwitch()
        ks.trigger(KillSwitchTrigger.DAILY_LOSS_EXCEEDED, reason="loss")
        ks.trigger(KillSwitchTrigger.BROKER_HEARTBEAT_LOST, reason="heartbeat")
        assert len(ks.events) == 2
        assert ks.state == KillSwitchState.KILLED

    def test_active_state_allows_orders(self):
        ks = KillSwitch()
        assert ks.can_submit_order() is True
