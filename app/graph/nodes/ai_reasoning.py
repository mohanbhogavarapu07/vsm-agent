import re
import structlog
import json
import langchain
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
# from langchain_google_genai import ChatGoogleGenerativeAI # Uncomment if gemini is added to requirements

from app.config import get_agent_settings
from app.graph.state import AgentState

logger = structlog.get_logger(__name__)
settings = get_agent_settings()

# Patch for langchain_core version mismatch
if not hasattr(langchain, 'verbose'):
    langchain.verbose = False
if not hasattr(langchain, 'debug'):
    langchain.debug = False
if not hasattr(langchain, 'llm_cache'):
    langchain.llm_cache = None


from typing import Optional, Literal
from pydantic import BaseModel, Field
# ... lines ...
class LLMResponse(BaseModel):
    to_stage_id: Optional[int] = Field(None, description="The ID of the stage to move to. Null if NO move should be made.")
    action_type: Literal["MOVE", "NO_TRANSITION", "BLOCK", "FLAG_SCOPE_CREEP", "FLAG_ASSIGNEE_MISMATCH"] = Field(..., description="The type of action to take.")
    reasoning: str = Field(..., description="Detailed explanation for your routing decision or blocks.")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0.")

def get_llm():
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=settings.llm_temperature)
    elif provider == "anthropic":
        return ChatAnthropic(model=settings.anthropic_model, api_key=settings.anthropic_api_key, temperature=settings.llm_temperature)
    # Default to Groq using ChatOpenAI (since Groq is OpenAI compatible)
    elif provider == "groq":
        return ChatOpenAI(
            model=settings.groq_model, 
            api_key=settings.groq_api_key, 
            base_url="https://api.groq.com/openai/v1", 
            temperature=settings.llm_temperature
        )
    else:
        # Fallback to OpenAI if unknown
        return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key)

async def ai_reasoning_node(state: AgentState) -> AgentState:
    """
    Node 4: Semantic LLM routing to proactively manage the Scrum Board.
    """
    current_stage = state.get("current_stage")  # may legitimately be None
    allowed_next_stages = state.get("allowed_next_stages") or []
    task_data = state.get("task_data") or {}        # guard: key may exist but be None
    actor_login = state.get("actor_login") or "unknown"
    signals = state.get("interpreted_signals") or []
    violations = state.get("rule_violations") or []
    intent_scores = state.get("intent_scores") or {}
    history = state.get("historical_context") or {}  # guard: may be None

    # 1. Build prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a Senior Virtual Scrum Master operating within a strict, deterministic workflow engine.\n"
            "The rule engine has pre-calculated the allowed next stages. Your only job is to decide IF and WHERE to move.\n\n"
            "MANDATORY RULES:\n"
            "1. NO FORCED MOVEMENT: If work is simply continuing on an already-active task, or if 'ALLOWED STAGES' is empty, return action_type 'NO_TRANSITION' with to_stage_id null.\n"
            "2. Assignee Bounds: If the 'github_actor' clearly diverges from the Task Assignee, return 'FLAG_ASSIGNEE_MISMATCH'.\n"
            "3. Hallucination Block: You are FORBIDDEN from providing a 'to_stage_id' not present in the 'ALLOWED STAGES' list.\n"
            "4. REASONING MUST MATCH THE ACTION:\n"
            "   - If action_type is 'MOVE': Explain WHAT activity triggered the move (e.g., 'Moving to Review as a PR was opened indicating the work is complete').\n"
            "   - If action_type is 'NO_TRANSITION': Explain WHY the task is STAYING. NEVER say 'ready for review' in a NO_TRANSITION.\n"
            "   - If action_type is 'BLOCK': Explain the specific risk or conflict.\n"
            "   DO NOT describe readiness for a stage you are NOT moving to.\n"
            "   DO NOT include any numeric values, percentages, or score names in your reasoning. Speak like a human Scrum Master, not a data pipeline.\n\n"
            "5. SPRINT ACTIVATION (HIGHEST PRIORITY RULE): If the current stage is a 'not started' stage (e.g. TODO, BACKLOG, To Do) "
            "AND commit signals are present in the intent signals, the developer has ALREADY started working. "
            "You MUST move to the first ACTIVE stage in the ALLOWED STAGES list. "
            "A developer writing code is unambiguous proof work has begun — do not second-guess this.\n\n"
            "CONTEXT:\n"
            "Current Stage: {current_stage}\n"
            "Task Assignee: {task_data}\n"
            "Actor: {actor}\n"
            "Intent Signals: {intent}\n"
            "History: {history}\n\n"
            "ALLOWED STAGES (Choose ONLY from these, or return NO_TRANSITION):\n"
            "{allowed_stages}\n\n"
            "OUTPUT FORMAT:\n"
            '{{ "to_stage_id": int|null, "action_type": "MOVE"|"NO_TRANSITION"|"BLOCK"|"FLAG_SCOPE_CREEP"|"FLAG_ASSIGNEE_MISMATCH", "reasoning": "string", "confidence": float }}\n'
            "CRITICAL: Output ONLY the raw JSON object above. No preamble, no explanation, no markdown fences. Begin with {{ and end with }}."
        )),
        ("user", "Evaluate the signals and select the best action for this task.")
    ])


    # 2. Call LLM
    llm = get_llm()
    chain = prompt | llm
    
    try:
        response = await chain.ainvoke({
            "task_data": json.dumps(task_data.get("assignee") or "N/A", default=str),
            "current_stage": json.dumps(current_stage or "Unknown", default=str),
            "allowed_stages": json.dumps(allowed_next_stages, default=str),
            "actor": actor_login,
            "intent": json.dumps(intent_scores, default=str),
            "history": json.dumps(history, default=str)
        })

        # ── 3-Tier JSON Extraction ────────────────────────────────────────────
        content = response.content.strip()

        # Tier 1: Fenced ```json ... ``` block
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        # Tier 2: Plain fenced ``` ... ``` block
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        else:
            # Tier 3: Regex — find the first {...} JSON object anywhere in prose
            match = re.search(r'\{[^{}]*"action_type"[^{}]*\}', content, re.DOTALL)
            if not match:
                # Broaden: find ANY {...} object
                match = re.search(r'\{.*?\}', content, re.DOTALL)
            if match:
                content = match.group(0).strip()
            # else: let json.loads fail with a useful error below

        raw_json = json.loads(content)
        parsed = LLMResponse(**raw_json)
        
        logger.info("llm_semantic_routing_success", action=parsed.action_type, to_stage=parsed.to_stage_id)
        
        return {
            **state,
            "llm_reasoning": parsed.reasoning,
            "candidate_actions": [{
                "toStageId": parsed.to_stage_id,
                "actionType": parsed.action_type,
                "confidence": parsed.confidence
            }]
        }

    except Exception as e:
        logger.exception("llm_reasoning_failed", error=str(e))
        return {
            **state,
            "llm_reasoning": f"LLM Routing failed: {str(e)}",
            "candidate_actions": [{
                "toStageId": None,
                "actionType": "BLOCK",
                "confidence": 0.0
            }]
        }
