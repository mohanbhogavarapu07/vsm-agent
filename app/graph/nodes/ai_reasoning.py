import logging
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

logger = logging.getLogger(__name__)
settings = get_agent_settings()

# Patch for langchain_core version mismatch
if not hasattr(langchain, 'verbose'):
    langchain.verbose = False
if not hasattr(langchain, 'debug'):
    langchain.debug = False
if not hasattr(langchain, 'llm_cache'):
    langchain.llm_cache = None


class LLMResponse(BaseModel):
    transition_id: Optional[str] = Field(None, description="The ID of the transition to take")
    reasoning: str = Field(..., description="Detailed reasoning for the decision")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")

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
    Node 4: LLM reasoning to suggest the next transition.
    """
    current_stage = state.get("current_stage")
    workflow_graph = state.get("workflow_graph", {})
    signals = state.get("interpreted_signals", [])
    violations = state.get("rule_violations", [])
    correlation_id = state["correlation_id"]

    # 1. Build prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a Senior Scrum Master Agent. Your goal is to determine the correct "
            "workflow transition based on GitHub signals and the current project state.\n\n"
            "CURRENT STAGE: {current_stage}\n"
            "WORKFLOW GRAPH: {workflow_graph}\n"
            "INTERPRETED SIGNALS: {signals}\n"
            "RULE VIOLATIONS: {violations}\n\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            '{{ "transition_id": "string|null", "reasoning": "string", "confidence": float }}'
        )),
        ("user", "Which transition should I take?")
    ])

    # 2. Call LLM
    llm = get_llm()
    chain = prompt | llm
    
    try:
        response = await chain.ainvoke({
            "current_stage": json.dumps(current_stage),
            "workflow_graph": json.dumps(workflow_graph),
            "signals": json.dumps([s.model_dump() for s in signals]),
            "violations": json.dumps(violations)
        })
        
        # 3. Parse and Validate
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        raw_json = json.loads(content)
        parsed = LLMResponse(**raw_json)
        
        logger.info("llm_reasoning_success", transition_id=parsed.transition_id, confidence=parsed.confidence)
        
        return {
            **state,
            "llm_reasoning": parsed.reasoning,
            "candidate_transitions": [{"id": parsed.transition_id, "confidence": parsed.confidence}] if parsed.transition_id else []
        }

    except Exception as e:
        logger.exception("llm_reasoning_failed", error=str(e))
        return {
            **state,
            "llm_reasoning": f"LLM Reasoning failed: {str(e)}",
            "candidate_transitions": []
        }
