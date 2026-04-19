import structlog
from app.graph.state import AgentState, DecisionProposal

logger = structlog.get_logger(__name__)

async def action_executor_node(state: AgentState) -> AgentState:
    """
    Node 6: Build the final decision proposal to be returned.
    Does NOT write to DB.
    """
    status = state.get("status", "NO_TRANSITION")
    selected_action = state.get("selected_action")
    candidate_actions = state.get("candidate_actions") or []
    llm_reasoning = state.get("llm_reasoning", "No LLM reasoning available.")
    correlation_id = state["correlation_id"]
    validation_result = state.get("validation_result")

    if state.get("decision_proposal"):
        # If a previous node already set a proposal, we respect it.
        return state

    # What did the LLM *originally* propose?
    original_llm_action = (
        selected_action.get("actionType") if selected_action
        else (candidate_actions[0].get("actionType") if candidate_actions else "NO_TRANSITION")
    )
    original_confidence = (
        selected_action.get("confidence", 0.0) if selected_action
        else (candidate_actions[0].get("confidence", 0.0) if candidate_actions else 0.0)
    )
    original_to_stage = (
        selected_action.get("toStageId") if selected_action
        else (candidate_actions[0].get("toStageId") if candidate_actions else None)
    )

    final_status = status
    # For the DecisionProposal, use selected_action if approved, else the candidate
    action_type = original_llm_action

    # ── Reconcile reasoning with actual outcome ───────────────────────────────
    # If the LLM proposed a MOVE but the validator blocked it (cooldown, low
    # confidence, etc.), the raw LLM reasoning describes a successful move —
    # which is misleading. Override with an honest explanation.
    final_reasoning = llm_reasoning
    if original_llm_action == "MOVE" and final_status in ("NO_TRANSITION", "BLOCK"):
        validation_errors = (
            validation_result.errors
            if validation_result and validation_result.errors
            else []
        )
        block_reason = (
            "; ".join(validation_errors)
            if validation_errors
            else "confidence below required threshold for this stage."
        )
        final_reasoning = (
            f"⚠️ Transition considered but held back: {block_reason}\n\n"
            f"AI assessment: {llm_reasoning}"
        )

    # ── Build DecisionProposal ─────────────────────────────────────────────────
    proposal = DecisionProposal(
        status=final_status,
        toStageId=original_to_stage,
        actionType=action_type,
        confidenceScore=original_confidence,
        reasoning=final_reasoning,
        postActions=[],
        correlationId=correlation_id
    )

    # ── Enhanced Detailed Logging ─────────────────────────────────────────────
    # Get human-readable stage names for the log
    from_stage_name = (state.get("current_stage") or {}).get("name", "Unknown")
    to_stage_name = "None"
    if original_to_stage:
        stages = state.get("workflow_stages", [])
        target_stage = next((s for s in stages if str(s.get("id")) == str(original_to_stage)), None)
        to_stage_name = target_stage.get("name", f"ID:{original_to_stage}") if target_stage else f"ID:{original_to_stage}"

    log_message = (
        f"AI DECISION: {final_status} | "
        f"Task: {state.get('task_id', 'N/A')} | "
        f"{from_stage_name} --> {to_stage_name} | "
        f"Reasoning: {final_reasoning}"
    )
    
    logger.info("action_executor_complete", 
                message=log_message,
                status=final_status, 
                actionType=action_type, 
                correlation_id=correlation_id,
                task_id=state.get("task_id"))

    return {
        **state,
        "decision_proposal": proposal
    }
