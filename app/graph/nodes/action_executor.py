import structlog
from app.graph.state import AgentState, DecisionProposal

logger = structlog.get_logger(__name__)

async def action_executor_node(state: AgentState) -> AgentState:
    """
    Node 6: Build the final decision proposal to be returned.
    Does NOT write to DB.
    """
    status = state.get("status", "NO_TRANSITION")
    selected_transition = state.get("selected_transition")
    llm_reasoning = state.get("llm_reasoning", "No LLM reasoning available.")
    correlation_id = state["correlation_id"]
    
    # 1. Map to final status
    final_status = status
    if state.get("decision_proposal"):
        # If a previous node (like context_builder or signal_interpreter) already set a proposal,
        # we respect it.
        return state

    # 2. Build DecisionProposal
    proposal = DecisionProposal(
        status=final_status,
        toStageId=selected_transition["toStageId"] if selected_transition else None,
        transitionId=selected_transition["id"] if selected_transition else None,
        confidenceScore=state.get("candidate_transitions", [{}])[0].get("confidence", 0.0) if selected_transition else 0.0,
        reasoning=llm_reasoning,
        postActions=selected_transition.get("postActions", []) if selected_transition else [],
        correlationId=correlation_id
    )

    logger.info("action_executor_complete", status=final_status, correlation_id=correlation_id)
    
    return {
        **state,
        "decision_proposal": proposal
    }
