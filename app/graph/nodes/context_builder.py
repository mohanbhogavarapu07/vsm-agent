import logging
from prisma.enums import WorkflowReadiness
from app.database import get_prisma
from app.graph.state import AgentState, DecisionProposal

logger = logging.getLogger(__name__)

async def context_builder_node(state: AgentState) -> AgentState:
    """
    Node 1: Fetch task and workflow graph context.
    Strictly READ ONLY access to Supabase.
    """
    project_id = state["project_id"]
    task_id = state.get("task_id")
    correlation_id = state["correlation_id"]
    
    db = get_prisma()
    
    # 1. Fetch Project & Readiness
    project = await db.project.find_unique(where={"id": project_id})
    if not project:
        logger.error("project_not_found", project_id=project_id, correlation_id=correlation_id)
        return {
            **state,
            "decision_proposal": DecisionProposal(
                status="BLOCKED",
                reasoning="Project not found.",
                correlationId=correlation_id,
                confidenceScore=0.0
            )
        }

    if project.workflowReadiness != WorkflowReadiness.ACTIVE:
        logger.info("workflow_not_ready", project_id=project_id, readiness=project.workflowReadiness)
        return {
            **state,
            "decision_proposal": DecisionProposal(
                status="BLOCKED",
                reasoning="Workflow not ready (DRAFT or INCOMPLETE).",
                correlationId=correlation_id,
                confidenceScore=0.0
            )
        }

    # 2. Fetch Workflow Graph
    stages = await db.workflowstage.find_many(where={"projectId": project_id})
    transitions = await db.workflowtransition.find_many(where={"projectId": project_id, "isActive": True})
    
    workflow_graph = {
        "stages": [s.model_dump() for s in stages],
        "transitions": [t.model_dump() for t in transitions]
    }

    # 3. Fetch Task Context (if task_id provided)
    current_stage = None
    if task_id:
        task = await db.task.find_unique(
            where={"id": task_id},
            include={"currentStage": True}
        )
        if task and task.currentStage:
            current_stage = task.currentStage.model_dump()

    logger.info("context_fetched", task_id=task_id, stage_count=len(stages), transition_count=len(transitions))
    
    return {
        **state,
        "workflow_graph": workflow_graph,
        "current_stage": current_stage
    }
