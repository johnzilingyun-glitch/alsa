"""Kill Switch — global circuit breaker for the trading system.

When triggered, the system enters read-only mode:
- No new order submissions allowed
- Existing order cancellation allowed
- Risk-reducing trades (sell/cover) allowed with human confirmation
- Only resettable via explicit human approval
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class KillSwitchState(str, Enum):
    ACTIVE = "ACTIVE"
    KILLED = "KILLED"


class KillSwitchTrigger(str, Enum):
    DAILY_LOSS_EXCEEDED = "DAILY_LOSS_EXCEEDED"
    BROKER_HEARTBEAT_LOST = "BROKER_HEARTBEAT_LOST"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    DATA_SOURCE_ANOMALY = "DATA_SOURCE_ANOMALY"
    LLM_ERROR_RATE_SPIKE = "LLM_ERROR_RATE_SPIKE"
    ORDER_REJECT_RATE_ANOMALY = "ORDER_REJECT_RATE_ANOMALY"
    RISK_SERVICE_UNAVAILABLE = "RISK_SERVICE_UNAVAILABLE"
    MANUAL = "MANUAL"


@dataclass
class KillSwitchEvent:
    trigger: KillSwitchTrigger
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class KillSwitch:
    """Global system circuit breaker."""

    def __init__(self, db_path="kill_switch_state.json"):
        import json, os
        self.db_path = db_path
        self.state, self.events = self._load_state()

    def _load_state(self):
        import json, os
        if os.path.exists(self.db_path):
            with open(self.db_path) as f:
                data = json.load(f)
                return KillSwitchState(data.get("state", "ACTIVE")), []
        return KillSwitchState.ACTIVE, []

    def _save_state(self):
        import json
        with open(self.db_path, 'w') as f:
            json.dump({"state": self.state.value}, f)

    def trigger(self, trigger: KillSwitchTrigger, reason: str) -> None:
        """Activate the kill switch. System enters read-only mode."""
        self.state = KillSwitchState.KILLED
        self.events.append(KillSwitchEvent(trigger=trigger, reason=reason))
        self._save_state()

    def can_submit_order(self) -> bool:
        """New orders are blocked when killed."""
        return self.state == KillSwitchState.ACTIVE

    def can_reduce_risk(self) -> bool:
        """Risk-reducing actions (sell/cover) are always allowed."""
        return True

    def can_cancel_order(self) -> bool:
        """Cancellation is always allowed."""
        return True

    def reset(self, approval_id: Optional[str] = None) -> None:
        """Reset kill switch. Requires human approval_id."""
        if not approval_id:
            raise ValueError("Kill switch reset requires human approval_id")
        self.state = KillSwitchState.ACTIVE
        self._save_state()
