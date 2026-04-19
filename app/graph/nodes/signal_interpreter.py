import structlog
from typing import List, Dict
from datetime import datetime
import math
from difflib import SequenceMatcher
from app.database import get_prisma
from app.graph.state import AgentState, Signal, DecisionProposal

logger = structlog.get_logger(__name__)

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
    
    # ── ELITE: DYNAMIC SIGNAL MAPPING ──
    # Map backend EventType strings to AI signal types
    EVENT_TYPE_MAP = {
        "PR_CREATED": "PR_OPENED",
        "PR_MERGED": "PR_MERGED",
        "GIT_COMMIT": "COMMIT_PUSH",
        "CI_STATUS": "CI_UPDATE",
        "CHAT_MESSAGE": "CHAT_SIGNAL"
    }

    SIGNAL_WEIGHTS = {
        "PR_MERGED": 1.0,
        "PR_OPENED": 0.8, # Slightly bumped for better sensitivity
        "COMMIT_PUSH": 0.4,
        "CI_UPDATE": 0.3,
        "CHAT_SIGNAL": 0.2
    }
    TAU_HOURS = 24.0 # Decay factor: signals older than 24 hours lose ~63% power
    
    aggregated_events = state.get("aggregated_events", [])
    window_end_str = state.get("window_end")
    reference_time = datetime.fromisoformat(window_end_str.replace("Z", "+00:00")) if window_end_str else datetime.utcnow()
    
    fused_score = 0.0

    # 1. Dynamic Signal Extraction across ALL aggregated events
    if not aggregated_events and payload:
        aggregated_events = [{"payload": payload, "event_type": state.get("github_event_type", "UNKNOWN"), "created_at": datetime.utcnow().isoformat()}]
        
    for evt_entry in aggregated_events:
        evt_payload = evt_entry.get("payload", {})
        evt_type = evt_entry.get("event_type", "UNKNOWN")
        created_str = evt_entry.get("created_at")
        
        # Calculate time diff in hours
        try:
            evt_time = datetime.fromisoformat(created_str.replace("Z", "+00:00")) if created_str else reference_time
            time_diff_hours = (reference_time - evt_time).total_seconds() / 3600.0
            time_diff_hours = max(0.0, time_diff_hours)
        except Exception:
            time_diff_hours = 0.0
            
        decay_factor = math.exp(-time_diff_hours / TAU_HOURS)
        
        sig_type = "UNKNOWN"
        metadata = {}

        # First, try to map from explicit backend event_type (Preferred/Dynamic)
        if evt_type in EVENT_TYPE_MAP:
            sig_type = EVENT_TYPE_MAP[evt_type]
            metadata["original_type"] = evt_type
            metadata["action"] = evt_payload.get("action")
            
            # Enrich metadata based on type
            if "pull_request" in evt_payload:
                metadata["number"] = evt_payload["pull_request"].get("number")
            elif "commits" in evt_payload:
                metadata["count"] = len(evt_payload["commits"])
                
        # Second, fallback to payload shape if type is UNKNOWN (Legacy/Discovery)
        elif "pull_request" in evt_payload:
            pr = evt_payload["pull_request"]
            action = evt_payload.get("action")
            sig_type = "PR_MERGED" if (action == "closed" and pr.get("merged")) else "PR_OPENED"
            metadata = {"number": pr.get("number"), "action": action}
        elif "commits" in evt_payload:
            sig_type = "COMMIT_PUSH"
            metadata = {"count": len(evt_payload["commits"])}
            
        if sig_type != "UNKNOWN":
            base_weight = SIGNAL_WEIGHTS.get(sig_type, 0.1)
            final_weight = base_weight * decay_factor
            fused_score += final_weight
            signals.append(Signal(type=sig_type, confidence=1.0, weight=final_weight, metadata=metadata))
            logger.info("signal_extracted", 
                        sig_type=sig_type, 
                        sig_weight=f"{final_weight:.2f}", 
                        correlation_id=correlation_id)


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
        "interpreted_signals": signals,
        "fused_signal_score": min(1.0, fused_score) # Cap at 1.0 for the generalized context metric
    }
