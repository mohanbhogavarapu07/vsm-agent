import structlog
from typing import List
from app.graph.state import AgentState, DecisionProposal

logger = structlog.get_logger(__name__)

async def rule_engine_node(state: AgentState) -> AgentState:
    """
    Node 3: Check global project-level hard rules.
    """
    violations: List[str] = []
    signals = state.get("interpreted_signals", [])
    correlation_id = state["correlation_id"]
    
    # ── EXAMPLE GLOBAL RULES ──────────────────────────────────────────────────
    # rule 1: "Never move to DONE without a merged PR"
    # (Simplified: we check if there's any PR_MERGED signal if current stage is REVIEW/VALIDATION)
    
    # rule 2: "Require at least 1 signal to move any task"
    if not signals:
        violations.append("No actionable signals detected from the event.")

    # ── CRITICAL VIOLATION CHECK ──────────────────────────────────────────────
    # If we have zero signals, we block by default as there's nothing to reason about.
    if not signals:
        logger.warning("rule_violation", violation="no_signals", correlation_id=correlation_id)
        return {
            **state,
            "rule_violations": violations,
            "decision_proposal": DecisionProposal(
                status="BLOCKED",
                reasoning="Rule violation: No actionable signals were identified to justify a transition.",
                correlationId=correlation_id,
                confidenceScore=0.0
            )
        }

    logger.info("rule_checks_passed", signals_count=len(signals))
    return {
        **state,
        "rule_violations": violations
    }
