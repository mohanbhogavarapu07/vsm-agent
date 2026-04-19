import logging
from langgraph.graph import StateGraph, END

from app.graph.state import AgentState
from app.graph.nodes.context_builder import context_builder_node
from app.graph.nodes.signal_interpreter import signal_interpreter_node
from app.graph.nodes.intent_analyzer import intent_analyzer_node
from app.graph.nodes.rule_engine import rule_engine_node
from app.graph.nodes.ai_reasoning import ai_reasoning_node
from app.graph.nodes.decision_validator import decision_validator_node
from app.graph.nodes.action_executor import action_executor_node

logger = logging.getLogger(__name__)

def _route_after_context(state: AgentState) -> str:
    if state.get("decision_proposal") and state["decision_proposal"].status == "BLOCKED":
        return "action_executor"
    return "signal_interpreter"

def _route_after_signals(state: AgentState) -> str:
    if state.get("decision_proposal") and state["decision_proposal"].status == "FUZZY_LINK":
        return "action_executor"
    return "intent_analyzer"

def _route_after_rules(state: AgentState) -> str:
    if state.get("decision_proposal") and state["decision_proposal"].status == "BLOCKED":
        return "action_executor"
    return "ai_reasoning"

def build_workflow_graph() -> StateGraph:
    """
    Step 5: Assemble the 6-node StateGraph following the defined DAG and routing rules.
    """
    builder = StateGraph(AgentState)
    
    # 1. Add Nodes
    builder.add_node("context_builder", context_builder_node)
    builder.add_node("signal_interpreter", signal_interpreter_node)
    builder.add_node("intent_analyzer", intent_analyzer_node)
    builder.add_node("rule_engine", rule_engine_node)
    builder.add_node("ai_reasoning", ai_reasoning_node)
    builder.add_node("decision_validator", decision_validator_node)
    builder.add_node("action_executor", action_executor_node)
    
    # 2. Set Entry
    builder.set_entry_point("context_builder")
    
    # 3. Add Edges with routing logic
    builder.add_conditional_edges(
        "context_builder",
        _route_after_context,
        {
            "action_executor": "action_executor",
            "signal_interpreter": "signal_interpreter"
        }
    )
    
    builder.add_conditional_edges(
        "signal_interpreter",
        _route_after_signals,
        {
            "action_executor": "action_executor",
            "intent_analyzer": "intent_analyzer"
        }
    )
    
    builder.add_edge("intent_analyzer", "rule_engine")
    
    builder.add_conditional_edges(
        "rule_engine",
        _route_after_rules,
        {
            "action_executor": "action_executor",
            "ai_reasoning": "ai_reasoning"
        }
    )
    
    builder.add_edge("ai_reasoning", "decision_validator")
    builder.add_edge("decision_validator", "action_executor")
    builder.add_edge("action_executor", END)
    
    return builder.compile()

# Accessor for FastAPI
_compiled_graph = None

def get_agent_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_workflow_graph()
        logger.info("LangGraph workflow graph compiled.")
    return _compiled_graph
