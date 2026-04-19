import structlog
from prisma.enums import WorkflowReadiness
from app.database import get_db_context
from app.graph.state import AgentState, DecisionProposal

logger = structlog.get_logger(__name__)

async def context_builder_node(state: AgentState) -> AgentState:
    """
    Node 1: Fetch task and workflow graph context.
    Strictly READ ONLY access to Supabase.
    Uses get_db_context() for automatic retry on P2024/P1001 pool exhaustion.
    """
    project_id = state["project_id"]
    task_id = state.get("task_id")
    correlation_id = state["correlation_id"]

    async with get_db_context() as db:
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

        # 2. Fetch Workflow Stages
        stages = await db.workflowstage.find_many(where={"projectId": project_id})
        workflow_stages = [s.model_dump() for s in stages]

        # 3. Fetch Task Context (if task_id provided)
        current_stage = None
        task_data = {}          # default to empty dict — never None downstream
        historical_context = {"recent_activities": [], "recent_decisions": []}
        last_transition_time = None

        if task_id:
            task = await db.task.find_unique(
                where={"id": task_id},
                include={
                    "currentStage": True,
                    "assignee": {
                        "include": {
                            "user": True
                        }
                    }
                }
            )
            if task:
                task_data = task.model_dump()
                if task.currentStage:
                    current_stage = task.currentStage.model_dump()
            else:
                logger.warning("task_not_found", task_id=task_id, correlation_id=correlation_id)

            # 4. Fetch Task Memory / History
            try:
                activities = await db.taskactivity.find_many(
                    where={"taskId": task_id},
                    order={"createdAt": "desc"},
                    take=15
                )

                # Find most recent agent decisions for cooldown/history
                decisions = await db.agentdecision.find_many(
                    where={"taskId": task_id},
                    order={"createdAt": "desc"},
                    take=5
                )

                # Use the most recent decision time as the last transition reference
                if decisions:
                    last_transition_time = decisions[0].createdAt.isoformat()

                historical_context = {
                    "recent_activities": [{"type": a.activityType, "time": a.createdAt.isoformat()} for a in activities],
                    "recent_decisions": [{"status": d.status, "reason": d.reasoning, "time": d.createdAt.isoformat()} for d in decisions]
                }
            except Exception as e:
                logger.warning("failed_to_fetch_history", error=str(e))
                historical_context = {"recent_activities": [], "recent_decisions": []}

    logger.info("context_fetched", task_id=task_id, stage_count=len(stages))

    return {
        **state,
        "workflow_stages": workflow_stages,
        "current_stage": current_stage,
        "task_data": task_data,
        "historical_context": historical_context,
        "last_transition_time": last_transition_time
    }
