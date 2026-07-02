"""Audit logging for critical system actions.

Every action that changes system state or affects trading decisions
must be recorded with actor, timestamp, and details.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class AuditAction(str, Enum):
    JOB_CREATED = "JOB_CREATED"
    PROMPT_VERSION_CHANGED = "PROMPT_VERSION_CHANGED"
    MODEL_POLICY_CHANGED = "MODEL_POLICY_CHANGED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RISK_CHECK = "RISK_CHECK"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    ORDER_INTENT_CREATED = "ORDER_INTENT_CREATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_SUBMISSION_REJECTED = "ORDER_SUBMISSION_REJECTED"
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"
    RISK_LIMIT_MODIFIED = "RISK_LIMIT_MODIFIED"


@dataclass
class AuditEntry:
    action: AuditAction
    actor: str
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLogger:
    """In-memory audit logger with size cap (production would use DB/append-only log)."""

    MAX_ENTRIES = 2000

    def __init__(self):
        self._entries: List[AuditEntry] = []

    def log(self, action: AuditAction, actor: str, details: Dict[str, Any]) -> None:
        """Record an audit entry. Evicts oldest when full."""
        self._entries.append(AuditEntry(action=action, actor=actor, details=details))
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]

    def get_entries(self, action: Optional[AuditAction] = None) -> List[AuditEntry]:
        """Retrieve entries, optionally filtered by action type."""
        if action is None:
            return list(self._entries)
        return [e for e in self._entries if e.action == action]


audit_logger = AuditLogger()
