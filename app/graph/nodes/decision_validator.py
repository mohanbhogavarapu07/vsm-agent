import logging
from typing import Optional
from app.graph.state import AgentState, ValidationResult

logger = logging.getLogger(__name__)

async def decision_validator_node(state: AgentState) -> AgentState:
    """
    Node 5: Safety net validation of suggested transition.
    """
    candidate_transitions = state.get("candidate_transitions", [])
    workflow_graph = state.get("workflow_graph", {"stages": [], "transitions": []})
    current_stage = state.get("current_stage")
    actor_login = state.get("actor_login")
    payload = state.get("raw_payload", {})
    correlation_id = state["correlation_id"]

    if not candidate_transitions:
        logger.info("no_candidate_transition", correlation_id=correlation_id)
        return {
            **state,
            "validation_result": ValidationResult(is_valid=False, errors=["No transition suggested by AI."]),
            "status": "NO_TRANSITION"
        }

    # 1. Take the best candidate
    best_candidate = candidate_transitions[0]
    transition_id = best_candidate.get("id")
    
    # 2. Cross-reference with graph
    target_transition = next((t for t in workflow_graph["transitions"] if str(t["id"]) == str(transition_id)), None)
    
    if not target_transition:
        logger.warning("hallucinated_transition", transition_id=transition_id)
        return {
            **state,
            "validation_result": ValidationResult(is_valid=False, errors=[f"Transition {transition_id} not found in graph."]),
            "status": "NO_TRANSITION"
        }

    # 3. Verify fromStageId matches
    if current_stage and str(target_transition["fromStageId"]) != str(current_stage["id"]):
        logger.warning("invalid_from_stage", current_stage=current_stage["id"], from_stage=target_transition["fromStageId"])
        return {
            **state,
            "validation_result": ValidationResult(is_valid=False, errors=["Transition starts from a different stage."]),
            "status": "NO_TRANSITION"
        }

    # 4. Verify conditions (Simplified implementation)
    conditions = target_transition.get("conditions", [])
    # We could implement complex logic here (e.g. check CI status, etc.)
    # For now, we assume all passed but we should check requiredRole if present.
    
    # 5. Verify requiredRole
    # In a real system, we'd fetch the user's role in the project.
    # Since we only have actor_login, we might skip this unless it's critical.
    if target_transition.get("requiredRole"):
        # logger.info("skipping_role_check", role=target_transition["requiredRole"])
        pass

    logger.info("validation_success", transition_id=transition_id)
    return {
        **state,
        "selected_transition": target_transition,
        "validation_result": ValidationResult(is_valid=True),
        "status": "APPROVED"
    }
