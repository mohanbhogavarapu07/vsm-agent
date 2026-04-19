import structlog
from typing import Any, Optional, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.graph.workflow import get_agent_graph
from app.graph.state import AgentState, DecisionProposal

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])

class InferRequest(BaseModel):
    project_id: int
    team_id: int
    task_id: Optional[int] = None
    github_event_type: str
    actor_github_login: str
    aggregated_events: List[dict]
    correlation_id: str
    window_start: str
    window_end: str

@router.post(
    "/infer",
    response_model=Any,
    status_code=status.HTTP_200_OK,
    summary="Run AI agent inference on GitHub event",
)
async def infer(request: InferRequest, simulate: bool = False) -> Any:
    """
    Step 5 Node 6 endpoint.
    Runs the full 6-node LangGraph pipeline.
    """
    logger.info("infer: start", project_id=request.project_id, task_id=request.task_id, correlation_id=request.correlation_id)

    # 1. Build initial state
    initial_state = {
        "project_id": request.project_id,
        "team_id": request.team_id,
        "task_id": request.task_id,
        "github_event_type": request.github_event_type,
        "actor_login": request.actor_github_login,
        "aggregated_events": request.aggregated_events,
        "raw_payload": request.aggregated_events[0]["payload"] if request.aggregated_events else {},
        "correlation_id": request.correlation_id,
        "window_start": request.window_start,
        "window_end": request.window_end,
        "workflow_graph": {},
        "current_stage": None,
        "interpreted_signals": [],
        "rule_violations": [],
        "llm_reasoning": None,
        "candidate_transitions": [],
        "selected_transition": None,
        "validation_result": {"is_valid": False},
    }

    # 2. Run LangGraph
    try:
        graph = get_agent_graph()
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("infer: graph execution failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent graph execution failed: {exc}",
        )

    # 3. Extract final decision proposal
    proposal = final_state.get("decision_proposal")
    if not proposal:
        logger.error("infer: no proposal returned from graph")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent graph completed without a proposal",
        )

    if simulate:
        # Return the entire internal state to visualize decision bounds
        return {
            "proposal": proposal,
            "fused_signal_score": final_state.get("fused_signal_score"),
            "intent_scores": final_state.get("intent_scores"),
            "allowed_next_stages": final_state.get("allowed_next_stages"),
            "historical_context": final_state.get("historical_context")
        }

    return proposal
