"""
VSM AI Agent – Graph Node Unit Tests

Tests each node in isolation using mock state.
"""

import pytest
from datetime import datetime, timezone

from app.graph.nodes.signal_interpreter import signal_interpreter_node
from app.graph.nodes.rule_engine import rule_engine_node
from app.graph.nodes.decision_validator import decision_validator_node
from app.models.context import AgentContext, TaskStatusContext, TransitionOption
from app.models.signals import SignalBundle, NormalizedSignal, SignalType


def make_pr_created_event():
    return {
        "event_id": 1,
        "event_type": "PR_CREATED",
        "source": "GITHUB",
        "payload": {"ref": "refs/heads/feature/VSM-42-auth"},
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def make_ci_passed_event():
    return {
        "event_id": 2,
        "event_type": "CI_STATUS",
        "source": "CI",
        "payload": {"pipeline_status": "success", "branch": "feature/VSM-42-auth"},
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
    }


class TestSignalInterpreter:
    def test_pr_created_maps_to_ready_for_review(self):
        state = {
            "task_id": 42,
            "team_id": 1,
            "correlation_id": "gh_abc123",
            "aggregated_events": [make_pr_created_event()],
            "window_start": datetime.now(timezone.utc).isoformat(),
            "window_end": datetime.now(timezone.utc).isoformat(),
            "context": AgentContext(task_id=42, team_id=1),
        }
        result = signal_interpreter_node(state)
        bundle = result["signal_bundle"]
        assert bundle.has_signal(SignalType.PR_CREATED)
        assert bundle.has_signal(SignalType.READY_FOR_REVIEW)

    def test_ci_passed_maps_to_unblocked(self):
        state = {
            "task_id": 42,
            "team_id": 1,
            "correlation_id": "ci_xyz",
            "aggregated_events": [make_ci_passed_event()],
            "window_start": datetime.now(timezone.utc).isoformat(),
            "window_end": datetime.now(timezone.utc).isoformat(),
            "context": AgentContext(task_id=42, team_id=1),
        }
        result = signal_interpreter_node(state)
        bundle = result["signal_bundle"]
        assert bundle.has_signal(SignalType.CI_PASSED)
        assert bundle.has_signal(SignalType.UNBLOCKED)


class TestRuleEngine:
    def _make_active_context(self, transitions=None):
        return AgentContext(
            task_id=42,
            team_id=1,
            current_status=TaskStatusContext(
                status_id=2,
                status_name="In Progress",
                category="ACTIVE",
                stage_order=2,
                is_terminal=False,
            ),
            valid_transitions=transitions or [],
        )

    def test_terminal_status_blocks(self):
        context = AgentContext(
            task_id=42,
            team_id=1,
            current_status=TaskStatusContext(
                status_id=5,
                status_name="Done",
                category="DONE",
                stage_order=5,
                is_terminal=True,  # Terminal!
            ),
        )
        state = {"task_id": 42, "context": context, "signal_bundle": None}
        result = rule_engine_node(state)
        assert result["rule_engine_blocked"] is True
        assert result["rule_engine_reason"] == "terminal_status"

    def test_forbidden_skip_active_to_done_blocked(self):
        transitions = [
            TransitionOption(
                transition_id=1,
                to_status_id=10,
                to_category="DONE",        # Direct ACTIVE→DONE skip!
                priority=1,
                requires_manual_approval=False,
                conditions_met=True,
            )
        ]
        context = self._make_active_context(transitions=transitions)
        state = {"task_id": 42, "context": context, "signal_bundle": None}
        result = rule_engine_node(state)
        assert len(result["allowed_transitions"]) == 0  # Should be blocked

    def test_valid_transition_to_review_allowed(self):
        transitions = [
            TransitionOption(
                transition_id=2,
                to_status_id=3,
                to_category="REVIEW",      # Valid sequence
                priority=1,
                requires_manual_approval=False,
                conditions_met=True,
            )
        ]
        context = self._make_active_context(transitions=transitions)
        state = {"task_id": 42, "context": context, "signal_bundle": None}
        result = rule_engine_node(state)
        assert not result["rule_engine_blocked"]
        assert len(result["allowed_transitions"]) == 1
        assert result["allowed_transitions"][0]["to_category"] == "REVIEW"


class TestDecisionValidator:
    def _make_state_with_raw(self, action, confidence, target_category="REVIEW"):
        return {
            "task_id": 42,
            "ai_decision_raw": {
                "action": action,
                "confidence": confidence,
                "reason": "Test reason",
                "target_category": target_category,
                "signals_used": ["PR_CREATED"],
            },
            "allowed_transitions": [
                {
                    "transition_id": 1,
                    "to_status_id": 3,
                    "to_category": "REVIEW",
                    "priority": 1,
                    "requires_manual_approval": False,
                    "conditions_met": True,
                }
            ],
            "context": AgentContext(task_id=42, team_id=1),
        }

    def test_high_confidence_auto_executes(self):
        state = self._make_state_with_raw("UPDATE_STATUS", 0.92)
        result = decision_validator_node(state)
        decision = result["final_decision"]
        assert decision.requires_confirmation is False
        assert decision.confidence == 0.92

    def test_medium_confidence_asks_user(self):
        state = self._make_state_with_raw("UPDATE_STATUS", 0.72)
        result = decision_validator_node(state)
        decision = result["final_decision"]
        assert decision.requires_confirmation is True

    def test_low_confidence_noop(self):
        state = self._make_state_with_raw("UPDATE_STATUS", 0.45)
        result = decision_validator_node(state)
        decision = result["final_decision"]
        from app.models.decisions import ActionType
        assert decision.action == ActionType.NO_OP
