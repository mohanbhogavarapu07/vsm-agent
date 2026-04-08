"""
VSM AI Agent – Pydantic Signal Models (PRD 3 §4)

Defines the normalized signal types that the AI engine understands.
All external events are mapped to these signals before reasoning.
"""

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SignalType(str, enum.Enum):
    """
    Canonical signal vocabulary.
    PRD 3 §5 Signal Interpreter mapping table.
    """
    # GitHub signals
    PR_CREATED = "PR_CREATED"
    PR_MERGED = "PR_MERGED"
    COMMIT_PUSHED = "COMMIT_PUSHED"

    # CI signals
    CI_PASSED = "CI_PASSED"
    CI_FAILED = "CI_FAILED"
    CI_RUNNING = "CI_RUNNING"

    # NLP-derived signals
    USER_BLOCKED = "USER_BLOCKED"
    USER_PROGRESS = "USER_PROGRESS"
    USER_COMPLETED = "USER_COMPLETED"
    USER_CONFUSED = "USER_CONFUSED"

    # Derived composite signals
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    UNBLOCKED = "UNBLOCKED"
    BLOCKED = "BLOCKED"
    MERGED = "MERGED"


# ── Signal Mapping Table (PRD 3 §5) ───────────────────────────────────────────
EVENT_TO_SIGNAL_MAP: dict[str, list[SignalType]] = {
    "PR_CREATED": [SignalType.PR_CREATED, SignalType.READY_FOR_REVIEW],
    "PR_MERGED": [SignalType.PR_MERGED, SignalType.MERGED],
    "GIT_COMMIT": [SignalType.COMMIT_PUSHED],
    "CI_STATUS_SUCCESS": [SignalType.CI_PASSED, SignalType.UNBLOCKED],
    "CI_STATUS_FAILED": [SignalType.CI_FAILED, SignalType.BLOCKED],
    "NLP_BLOCKER": [SignalType.USER_BLOCKED, SignalType.BLOCKED],
    "NLP_PROGRESS": [SignalType.USER_PROGRESS],
    "NLP_COMPLETION": [SignalType.USER_COMPLETED],
    "NLP_CONFUSION": [SignalType.USER_CONFUSED],
}


class NormalizedSignal(BaseModel):
    """A single normalized signal extracted from an event."""
    signal_type: SignalType
    source_event_id: int | None = None
    source_event_type: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalBundle(BaseModel):
    """Collection of signals from a single aggregation window."""
    signals: list[NormalizedSignal] = Field(default_factory=list)
    correlation_id: str
    window_start: datetime
    window_end: datetime

    def get_signal_types(self) -> list[str]:
        return [s.signal_type.value for s in self.signals]

    def has_signal(self, signal_type: SignalType) -> bool:
        return any(s.signal_type == signal_type for s in self.signals)

    def max_confidence_for(self, signal_type: SignalType) -> float:
        matching = [s.confidence for s in self.signals if s.signal_type == signal_type]
        return max(matching) if matching else 0.0
