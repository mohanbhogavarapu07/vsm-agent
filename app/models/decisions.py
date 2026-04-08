"""
VSM AI Agent – Decision Models (PRD 3 §3, §8)

Defines all decision types and their structured output formats.
Every decision includes confidence, reason, and signal traceability.
"""

import enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, enum.Enum):
    """All possible actions the AI engine can take."""
    UPDATE_STATUS = "UPDATE_STATUS"          # Move task to a new status
    ASK_USER = "ASK_USER"                   # Request human confirmation
    NO_OP = "NO_OP"                         # Do nothing (no valid transition)
    WAIT_FOR_MORE_DATA = "WAIT_FOR_MORE_DATA"  # Insufficient context
    BLOCKED = "BLOCKED"                     # Mark task as blocked
    LINK_ACTIVITY = "LINK_ACTIVITY"         # Link unlinked commit/PR to task


class DecisionReason(str, enum.Enum):
    """Structured reason codes for observability."""
    CONDITIONS_MET = "all_conditions_met"
    CONDITIONS_NOT_MET = "conditions_not_met"
    CONFLICTING_SIGNALS = "conflicting_signals"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_CONTEXT = "missing_context"
    MANUAL_APPROVAL_REQUIRED = "manual_approval_required"
    RULE_ENGINE_BLOCKED = "rule_engine_blocked"
    NO_VALID_TRANSITION = "no_valid_transition"


class AgentDecision(BaseModel):
    """
    PRD 3 – Expected output format for every AI decision.

    {
      "decision": "MOVE_TO_REVIEW",
      "confidence": 0.91,
      "reason": "PR created and CI passed, ready for review",
      "requires_confirmation": false
    }
    """
    action: ActionType
    target_category: str | None = None          # e.g. "REVIEW"
    new_status_id: int | None = None            # Resolved status ID
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    reason_code: DecisionReason
    requires_confirmation: bool = False

    # Full signal traceability (PRD 3 §3 Principle 3)
    signals_used: list[str] = Field(default_factory=list)
    decision_source: str = "AI_MODEL"           # AI_MODEL | RULE_ENGINE

    # For ASK_USER actions
    prompt_for_user: str | None = None

    # For LINK_ACTIVITY actions
    suggested_task_id: int | None = None

    def to_backend_payload(self) -> dict[str, Any]:
        """Serializes decision for sending back to vsm-backend."""
        return {
            "action": self.action.value,
            "target_category": self.target_category,
            "new_status_id": self.new_status_id,
            "confidence": self.confidence,
            "reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
            "signals_used": self.signals_used,
            "decision_source": self.decision_source,
            "prompt_for_user": self.prompt_for_user,
        }


class UnlinkedActivityDecision(BaseModel):
    """Decision output for unlinked activity resolution."""
    activity_id: int
    suggested_task_id: int | None = None
    confidence: float
    mapping_method: str = "AI_AUTO"
    reason: str
