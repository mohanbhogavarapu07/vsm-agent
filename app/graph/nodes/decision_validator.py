import structlog
from typing import Optional
from datetime import datetime, timezone
from app.graph.state import AgentState, ValidationResult

logger = structlog.get_logger(__name__)

async def decision_validator_node(state: AgentState) -> AgentState:
    """
    Node 5: Semantic safety net validation of proposed actions.
    """
    candidate_actions = state.get("candidate_actions", [])
    workflow_stages = state.get("workflow_stages", [])
    correlation_id = state["correlation_id"]

    if not candidate_actions:
        logger.info("no_candidate_actions", correlation_id=correlation_id)
        return {
            **state,
            "validation_result": ValidationResult(is_valid=False, errors=["No semantic routing suggested by AI."]),
            "status": "NO_TRANSITION"
        }

    # 1. Take the best candidate
    best_candidate = candidate_actions[0]
    raw_action = best_candidate.get("actionType", "NO_TRANSITION").upper()
    to_stage_id = best_candidate.get("toStageId")
    
    # Normalize synonyms
    if raw_action in ["TRANSITION", "TO_STAGE", "CHANGE_STANCE"]:
        action_type = "MOVE"
    else:
        action_type = raw_action
    
    # 2. Stay Bias Penalty — skipped for explicit PR events (a PR IS the evidence)
    github_event_type = (state.get("github_event_type") or "").upper()
    is_pr_event = any(k in github_event_type for k in ["PR", "PULL_REQUEST", "PULL"])
    is_ci_event = any(k in github_event_type for k in ["CI", "BUILD", "WORKFLOW", "ACTION"])

    STAY_BIAS = 0.0 if is_pr_event else 0.15
    original_confidence = best_candidate.get("confidence", 0.0)
    adjusted_confidence = max(0.0, original_confidence - STAY_BIAS)
    
    # 3. Block/Flags are automatically valid
    if action_type in ["BLOCK", "FLAG_SCOPE_CREEP", "FLAG_ASSIGNEE_MISMATCH", "NO_TRANSITION"]:
        logger.info("routing_warning", action=action_type, correlation_id=correlation_id)
        return {
            **state,
            "selected_action": best_candidate,
            "validation_result": ValidationResult(is_valid=True),
            "status": action_type # Use the action_type explicitly for workflow passthrough
        }

    if action_type == "MOVE":
        if not to_stage_id:
            return {
                **state,
                "validation_result": ValidationResult(is_valid=False, errors=["MOVE action missing toStageId."]),
                "status": "NO_TRANSITION"
            }
            
        # 4. Global Anti-Flapping Cooldown Check
        # Cooldown is event-aware: PRs bypass it entirely (explicit human intent),
        # CI events use a shorter window, commits use the full window.
        # is_pr_event / is_ci_event already computed above

        if is_pr_event:
            # PRs are explicit intent signals — never block them with cooldown
            logger.info("cooldown_bypassed_pr_event", github_event=github_event_type)
        else:
            cooldown_minutes = 2.0 if is_ci_event else 10.0
            last_transition_str = state.get("last_transition_time")
            if last_transition_str:
                try:
                    last_time = datetime.fromisoformat(last_transition_str.replace("Z", "+00:00"))
                    diff_minutes = (datetime.now(timezone.utc) - last_time).total_seconds() / 60.0
                    if diff_minutes < cooldown_minutes:
                        logger.warning("cooldown_active", minutes=diff_minutes, required=cooldown_minutes, github_event=github_event_type)
                        return {
                            **state,
                            "validation_result": ValidationResult(
                                is_valid=False,
                                errors=[f"A transition was applied very recently — holding off to avoid rapid stage-flipping ({diff_minutes:.1f} min elapsed, {cooldown_minutes:.0f} min required)."]
                            ),
                            "status": "NO_TRANSITION"
                        }
                except Exception:
                    pass
        
        # Verify the stage actually exists in the project
        target_stage = next((s for s in workflow_stages if str(s["id"]) == str(to_stage_id)), None)
        if not target_stage:
            logger.warning("hallucinated_stage", stage_id=to_stage_id)
            return {
                **state,
                "validation_result": ValidationResult(is_valid=False, errors=[f"Stage {to_stage_id} not found in project."]),
                "status": "NO_TRANSITION"
            }
            
        # 5. Dynamic Confidence Calibration
        category = target_stage.get("systemCategory", "TODO").upper()
        if category == "DONE":
            threshold = 0.85
        elif category in ["REVIEW", "VALIDATION"]:
            threshold = 0.75
        else:
            threshold = 0.65
            
        # PR events are explicit human intent — reduce the required threshold
        # (a PR means the developer consciously declared work is ready)
        if is_pr_event:
            threshold = max(0.40, threshold - 0.15)
            logger.info("confidence_threshold_relaxed_pr", category=category, threshold=threshold)
            
        if adjusted_confidence < threshold:
            logger.warning("confidence_rejected", adjusted=adjusted_confidence, required=threshold, cat=category)
            return {
                **state,
                "validation_result": ValidationResult(
                    is_valid=False,
                    errors=[f"Not enough confidence to advance to a {category} stage — waiting for stronger evidence from the team."]
                ),
                "status": "NO_TRANSITION"
            }
            
        logger.info("routing_validated", to_stage=to_stage_id, confidence=adjusted_confidence)
        return {
            **state,
            "selected_action": best_candidate,
            "validation_result": ValidationResult(is_valid=True),
            "status": "APPROVED" # Classic move logic
        }
        
    return {
        **state,
        "validation_result": ValidationResult(is_valid=False, errors=[f"Unknown actionType: {action_type}"]),
        "status": "NO_TRANSITION"
    }
