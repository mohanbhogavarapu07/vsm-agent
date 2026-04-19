import structlog
import json
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from app.graph.state import AgentState
from app.graph.nodes.ai_reasoning import get_llm

logger = structlog.get_logger(__name__)

class IntentScore(BaseModel):
    review_readiness_score: float = Field(..., description="0.0 to 1.0 probability that the task is ready for review based on the context and signals.")
    completion_score: float = Field(..., description="0.0 to 1.0 probability that the task is completely finished and ready to be closed.")
    risk_score: float = Field(..., description="0.0 to 1.0 probability that the current signals present a risk or blocker (e.g. CI failure).")

async def intent_analyzer_node(state: AgentState) -> AgentState:
    """
    Node 2.5: Intent Analyzer
    Evaluates the historical context and fused signals to determine quantitative intent scores.
    """
    historical_context = state.get("historical_context", {})
    signals = state.get("interpreted_signals", [])
    fused_score = state.get("fused_signal_score", 0.0)
    task_data = state.get("task_data", {})
    
    # Fast path if no major signals to analyze
    if not signals:
        return {
            **state,
            "intent_scores": {"review_readiness_score": 0.0, "completion_score": 0.0, "risk_score": 0.0}
        }

    # 1. Build prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an Intent Analysis Engine. Your goal is to evaluate GitHub events and Task Activity history "
            "to output continuous probability scores.\n\n"
            "CONTEXT:\n"
            "Signals: {signals}\n"
            "Fused Signal Gravity: {fused_score}\n"
            "History: {history}\n\n"
            "INSTRUCTIONS:\n"
            "Calculate quantitative intent scores based on the context.\n"
            "- ACTIVITY BIAS: If multiple commits exist in history for this task and Fused Gravity is high (>0.5), review_readiness_score should trend toward 0.6+ unless commit messages imply 'WIP'.\n"
            "- COMPLETION: Only score above 0.8 if a PR is merged or the message explicitly says 'completed' or 'fixed'.\n"
            "- RISK: If CI failed or history shows recent reverts, raise the risk_score.\n\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            '{{ "review_readiness_score": float, "completion_score": float, "risk_score": float }}'
        )),
        ("user", "Analyze the intent signatures.")
    ])

    llm = get_llm()
    chain = prompt | llm
    
    try:
        response = await chain.ainvoke({
            "signals": json.dumps([s.model_dump() for s in signals]),
            "fused_score": fused_score,
            "history": json.dumps(historical_context)
        })
        
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        raw_json = json.loads(content)
        parsed = IntentScore(**raw_json)
        
        logger.info("intent_analyzed", 
                    review=parsed.review_readiness_score, 
                    completion=parsed.completion_score, 
                    risk=parsed.risk_score)
                    
        return {
            **state,
            "intent_scores": parsed.model_dump()
        }
    except Exception as e:
        logger.warning("intent_analyzer_failed", error=str(e))
        # Fallback to heuristics if LLM fails
        return {
            **state,
            "intent_scores": {
                "review_readiness_score": 1.0 if any(s.type == "PR_OPENED" for s in signals) else 0.0,
                "completion_score": 1.0 if any(s.type == "PR_MERGED" for s in signals) else 0.0,
                "risk_score": 0.0
            }
        }
