from typing import Any, Optional, List, TypedDict
from pydantic import BaseModel

class Signal(BaseModel):
    type: str
    confidence: float
    weight: float = 1.0
    metadata: dict

class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = []

class DecisionProposal(BaseModel):
    status: str # "APPROVED"|"BLOCKED"|"NO_TRANSITION"|"FUZZY_LINK"|"PENDING_CONFIRMATION"
    toStageId: Optional[int] = None
    actionType: str = "MOVE"
    confidenceScore: float
    reasoning: str
    postActions: List[dict] = []
    correlationId: str

class AgentState(TypedDict, total=False):
    project_id: int
    team_id: int
    task_id: Optional[int]
    github_event_type: str
    actor_login: str
    raw_payload: dict
    aggregated_events: List[dict]
    correlation_id: str
    window_start: str
    window_end: str
    
    # Context
    workflow_stages: List[dict]
    current_stage: Optional[dict]
    task_data: Optional[dict]
    historical_context: Optional[dict]
    last_transition_time: Optional[str]
    
    # Processing
    interpreted_signals: List[Signal]
    fused_signal_score: float
    intent_scores: Optional[dict]
    allowed_next_stages: List[dict]
    rule_violations: List[str]
    llm_reasoning: Optional[str]
    candidate_actions: List[dict]
    selected_action: Optional[dict]
    status: str
    
    # Results
    validation_result: ValidationResult
    decision_proposal: DecisionProposal
