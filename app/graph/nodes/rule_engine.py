import structlog
from typing import List
from app.graph.state import AgentState, DecisionProposal

logger = structlog.get_logger(__name__)

CATEGORY_ORDER = ["BACKLOG", "TODO", "ACTIVE", "REVIEW", "VALIDATION", "DONE", "BLOCKED"]

async def rule_engine_node(state: AgentState) -> AgentState:
    """
    Node 3: The Invisible State Machine
    Generates allowed_next_stages mathematically.
    """
    violations: List[str] = []
    signals = state.get("interpreted_signals", [])
    correlation_id = state["correlation_id"]
    workflow_stages = state.get("workflow_stages", [])
    current_stage = state.get("current_stage")
    intent = state.get("intent_scores", {})
    
    logger.debug("rule_engine_input", 
                 current_stage=current_stage.get('name') if current_stage else 'None',
                 workflow_stages_full=[{"id": s.get("id"), "cat": s.get("systemCategory")} for s in workflow_stages])
    
    if not signals:
        violations.append("No actionable signals detected.")
        return {
            **state,
            "rule_violations": violations,
            "allowed_next_stages": [],
            "decision_proposal": DecisionProposal(
                status="NO_TRANSITION",
                reasoning="No actionable signals.",
                correlationId=correlation_id,
                confidenceScore=0.0
            )
        }

    # 1. Determine Current Category Index
    current_cat = current_stage.get("systemCategory", "TODO").upper() if current_stage else "TODO"
    
    try:
        current_idx = CATEGORY_ORDER.index(current_cat)
    except ValueError:
        current_idx = 1 # Fallback to TODO

    allowed_cats = {current_cat, "BLOCKED"} # We can always stay here or get blocked
    
    # 2. Sequential Expansion based on Intent & Signals (Dynamic)
    # Move to ACTIVE
    if current_idx < CATEGORY_ORDER.index("ACTIVE"):
        if sum(s.weight for s in signals) > 0.0:
            allowed_cats.add("ACTIVE")
            
    # Move to REVIEW / VALIDATION
    if current_idx <= CATEGORY_ORDER.index("REVIEW"):
        review_score = intent.get("review_readiness_score", 0)
        has_pr_signal = any(s.type == "PR_OPENED" for s in signals)
        
        # DYNAMIC: Allow Review if intent is high OR if an explicit PR was opened
        if review_score > 0.5 or has_pr_signal:
            allowed_cats.add("REVIEW")
            allowed_cats.add("VALIDATION")
            logger.info("transition_allowed", cat="REVIEW", score=review_score, has_pr=has_pr_signal)
        else:
            logger.info("transition_suppressed", cat="REVIEW", score=review_score, threshold=0.5)
            
    # Move to DONE
    if current_idx <= CATEGORY_ORDER.index("DONE"):
        done_score = intent.get("completion_score", 0)
        has_merge_signal = any(s.type == "PR_MERGED" for s in signals)
        
        # DYNAMIC: Allow Done if intent is high OR if PR was merged
        if done_score > 0.7 or has_merge_signal:
            allowed_cats.add("DONE")
            logger.info("transition_allowed", cat="DONE", score=done_score, merged=has_merge_signal)
        else:
            logger.info("transition_suppressed", cat="DONE", score=done_score, threshold=0.7)
            
    # 3. Filter Workflow Stages
    allowed_next_stages = []
    category_counts = {}
    
    for s in workflow_stages:
        cat = (s.get("systemCategory") or "TODO").upper()
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if cat in allowed_cats:
            allowed_next_stages.append(s)

    logger.debug("stage_category_distribution", distribution=category_counts, allowed=list(allowed_cats))
    
    # Exclude the current stage from "allowed_next_stages" so we only present forward movements,
    # because relying on NO_TRANSITION is how we stay.
    if current_stage:
        allowed_next_stages = [s for s in allowed_next_stages if str(s.get("id")) != str(current_stage.get("id"))]
    # else: if no current_stage (Unknown/None), we allow moving to ANY stage in allowed_cats

    logger.info("rule_checks_passed", allowed_cats=list(allowed_cats), stages_count=len(allowed_next_stages))
    
    return {
        **state,
        "rule_violations": violations,
        "allowed_next_stages": allowed_next_stages
    }
