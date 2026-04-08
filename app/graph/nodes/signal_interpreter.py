import logging
from typing import List
from difflib import SequenceMatcher
from app.database import get_prisma
from app.graph.state import AgentState, Signal, DecisionProposal

logger = logging.getLogger(__name__)

def get_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

async def signal_interpreter_node(state: AgentState) -> AgentState:
    """
    Node 2: Interpret raw signals and resolve task_id if missing.
    """
    payload = state["raw_payload"]
    actor_login = state["actor_login"]
    project_id = state["project_id"]
    task_id = state.get("task_id")
    correlation_id = state["correlation_id"]
    db = get_prisma()
    
    signals: List[Signal] = []
    
    # 1. Basic Signal Extraction
    event_type = state["github_event_type"]
    if "pull_request" in payload:
        pr = payload["pull_request"]
        action = payload.get("action")
        if action == "opened":
            signals.append(Signal(type="PR_OPENED", confidence=1.0, metadata={"number": pr["number"]}))
        elif action == "closed" and pr.get("merged"):
            signals.append(Signal(type="PR_MERGED", confidence=1.0, metadata={"number": pr["number"]}))
    elif "commits" in payload:
        signals.append(Signal(type="COMMIT_PUSH", confidence=1.0, metadata={"count": len(payload["commits"])}))

    # 2. Fuzzy Task Linking (if task_id is null)
    if not task_id:
        # Fetch open tasks for this project
        open_tasks = await db.task.find_many(
            where={
                "team": {"projectId": project_id}
            },
            include={"team": True}
        )
        
        # Determine search string from payload
        search_string = ""
        if "pull_request" in payload:
            search_string = payload["pull_request"].get("title", "")
        elif "commits" in payload and payload["commits"]:
            search_string = payload["commits"][0].get("message", "")
        
        best_match_task = None
        max_score = 0.0
        
        for task in open_tasks:
            title_score = get_similarity(search_string, task.title)
            desc_score = get_similarity(search_string, task.description or "")
            score = max(title_score, desc_score)
            if score > max_score:
                max_score = score
                best_match_task = task
        
        if best_match_task and max_score > 0.75:
            task_id = best_match_task.id
            signals.append(Signal(type="FUZZY_TASK_LINK", confidence=max_score, metadata={"task_id": task_id}))
            logger.info("fuzzy_match_success", task_id=task_id, score=max_score)
        else:
            logger.info("fuzzy_match_failed", score=max_score)
            # If we reached here without a task_id and couldn't fuzzy match, we must escalate.
            return {
                **state,
                "decision_proposal": DecisionProposal(
                    status="FUZZY_LINK",
                    reasoning=f"Could not link GitHub event to any task (best match score: {max_score:.2f}).",
                    correlationId=correlation_id,
                    confidenceScore=max_score
                )
            }

    return {
        **state,
        "task_id": task_id,
        "interpreted_signals": signals
    }
