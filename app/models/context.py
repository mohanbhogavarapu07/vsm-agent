"""
VSM AI Agent – Context Models (PRD 3 §5)

Defines the full context object the AI engine operates on.
The context builder populates this; all graph nodes read from it.
"""

from typing import Any
from pydantic import BaseModel, Field

from app.models.signals import SignalBundle


class TaskStatusContext(BaseModel):
    """Lightweight status representation used by AI (category-based, not name-based)."""
    status_id: int
    status_name: str
    category: str          # BACKLOG | TODO | ACTIVE | REVIEW | VALIDATION | DONE | BLOCKED
    stage_order: int
    is_terminal: bool


class TransitionOption(BaseModel):
    """A valid transition option with its conditions."""
    transition_id: int
    to_status_id: int
    to_category: str
    priority: int
    requires_manual_approval: bool
    conditions_met: bool
    conditions: list[dict[str, Any]] = Field(default_factory=list)


class NLPInsightContext(BaseModel):
    """Relevant NLP insight for current reasoning context."""
    insight_id: int
    detected_intent: str
    confidence_score: float
    requires_confirmation: bool


class AgentContext(BaseModel):
    """
    Full context object fed into the LangGraph agent.
    This is the PRD 3 §5 'Context Object'.

    All graph nodes read from this object.
    Only the action_executor node writes back to DB.
    """
    # ── Task ──────────────────────────────────────────────────────────────────
    task_id: int | None = None
    team_id: int
    current_status: TaskStatusContext | None = None
    candidate_tasks: list[dict[str, Any]] = Field(default_factory=list) # Discovery Mode

    # ── Signals ───────────────────────────────────────────────────────────────
    signal_bundle: SignalBundle | None = None

    # ── Workflow ──────────────────────────────────────────────────────────────
    valid_transitions: list[TransitionOption] = Field(default_factory=list)
    team_rules: list[dict[str, Any]] = Field(default_factory=list)

    # ── Recent Activity ────────────────────────────────────────────────────────
    recent_activity: list[dict[str, Any]] = Field(default_factory=list)

    # ── NLP Insights ──────────────────────────────────────────────────────────
    nlp_insights: list[NLPInsightContext] = Field(default_factory=list)

    # ── Raw Events (original payloads from aggregation window) ────────────────
    aggregated_events: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str = ""

    def has_conflict(self) -> bool:
        """
        PRD 3 §8.3 — conflict detection:
        NLP says BLOCKED but CI says PASSED.
        """
        signal_types = self.signal_bundle.get_signal_types() if self.signal_bundle else []
        nlp_intents = [i.detected_intent for i in self.nlp_insights]

        has_block_signal = "BLOCKED" in signal_types or "USER_BLOCKED" in signal_types
        has_ci_pass = "CI_PASSED" in signal_types
        has_nlp_block = "BLOCKER" in nlp_intents

        return (has_nlp_block and has_ci_pass) or (has_block_signal and has_ci_pass)
