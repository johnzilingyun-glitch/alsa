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
    """Global system circuit breaker with SQLite persistence and HMAC validation."""

    def __init__(self, db_path="kill_switch_state.db"):
        self.db_path = db_path
        self.events = []
        self.state = self._load_state()

    def _compute_signature(self, state: str, reason: str) -> str:
        import hmac, hashlib, os
        key = os.getenv("API_TOKEN", "fallback_secret_key").encode()
        message = f"{state}:{reason}".encode()
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def _load_state(self) -> KillSwitchState:
        import sqlite3, os
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kill_switch_state (
                id INTEGER PRIMARY KEY,
                state TEXT,
                reason TEXT,
                signature TEXT,
                triggered_at TEXT,
                reset_at TEXT
            )
        """)
        
        cursor.execute("SELECT state, reason, signature FROM kill_switch_state WHERE id = 1")
        row = cursor.fetchone()
        
        if not row:
            state = "ACTIVE"
            reason = "Initial state"
            signature = self._compute_signature(state, reason)
            cursor.execute("""
                INSERT INTO kill_switch_state (id, state, reason, signature, triggered_at, reset_at)
                VALUES (1, ?, ?, ?, NULL, NULL)
            """, (state, reason, signature))
            conn.commit()
            conn.close()
            return KillSwitchState.ACTIVE
            
        state_str, reason, signature = row
        conn.close()
        
        # Verify signature
        expected_signature = self._compute_signature(state_str, reason)
        if signature != expected_signature:
            print("WARNING: Kill switch state signature verification failed! Forcing KILLED state.")
            return KillSwitchState.KILLED
            
        return KillSwitchState(state_str)

    def trigger(self, trigger: KillSwitchTrigger, reason: str) -> None:
        """Activate the kill switch. System enters read-only mode."""
        self.state = KillSwitchState.KILLED
        self.events.append(KillSwitchEvent(trigger=trigger, reason=reason))
        
        import sqlite3
        from datetime import datetime, timezone
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        signature = self._compute_signature(self.state.value, reason)
        triggered_at = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            UPDATE kill_switch_state
            SET state = ?, reason = ?, signature = ?, triggered_at = ?
            WHERE id = 1
        """, (self.state.value, reason, signature, triggered_at))
        conn.commit()
        conn.close()

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
        
        import sqlite3
        from datetime import datetime, timezone
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        reason = f"Reset by {approval_id}"
        signature = self._compute_signature(self.state.value, reason)
        reset_at = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            UPDATE kill_switch_state
            SET state = ?, reason = ?, signature = ?, reset_at = ?
            WHERE id = 1
        """, (self.state.value, reason, signature, reset_at))
        conn.commit()
        conn.close()
