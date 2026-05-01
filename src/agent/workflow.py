from langgraph.graph import StateGraph, START, END

from .state import (
    MessagesStateTXT2SQL,
)
from .nodes import (
    query_classification_node,
    list_tables_node,
    get_schema_node,
    generate_sql_node,
    reasoning_node,
    repair_sql_node,
    validate_sql_node,
    execute_sql_node,
    generate_response_node,
    clarification_node,
    vote_sql_node,
)
from .query_planner import query_planner_node
from .plan_gate import plan_gate_node
from .multi_executor import multi_sql_executor_node
from .multi_verifier import multi_verifier_node
from .result_synthesizer import result_synthesizer_node
from .routing import (
    route_after_classification,
    route_after_multi_verifier,
    route_after_plan_gate,
    route_after_query_planner,
    route_after_repair,
    route_after_schema,
    route_after_sql_execution,
    route_after_sql_generation,
    route_after_sql_validation,
)


def create_langgraph_sql_workflow():
    """
    Create LangGraph SQL workflow following official tutorial patterns
    
    This implements the exact structure recommended in the LangGraph SQL Agent tutorial:
    - MessagesState as primary state
    - Tool-based conditional routing
    - Proper error handling and retries
    - Memory checkpointing support
    
    Workflow Structure:
    START → classify → [route based on classification]
    
    Routes:
    1. DATABASE: classify → list_tables → get_schema → generate_sql → validate_sql → execute_sql → response
    2. CONVERSATIONAL: classify → response (direct)
    3. SCHEMA: classify → list_tables → response
    
    With retry mechanisms and error handling at each step.
    """
    
    # Create StateGraph with MessagesState
    workflow = StateGraph(MessagesStateTXT2SQL)
    
    # Add all nodes
    workflow.add_node("classify_query", query_classification_node)
    workflow.add_node("list_tables", list_tables_node)
    workflow.add_node("get_schema", get_schema_node)
    workflow.add_node("plan_gate", plan_gate_node)
    workflow.add_node("query_planner", query_planner_node)
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("vote_sql", vote_sql_node)
    workflow.add_node("repair_sql", repair_sql_node)
    workflow.add_node("validate_sql", validate_sql_node)
    workflow.add_node("execute_sql", execute_sql_node)
    workflow.add_node("generate_response", generate_response_node)
    workflow.add_node("clarification", clarification_node)
    # Multi-query path
    workflow.add_node("multi_sql_executor", multi_sql_executor_node)
    workflow.add_node("multi_verifier", multi_verifier_node)
    workflow.add_node("result_synthesizer", result_synthesizer_node)
    
    # Entry point
    workflow.add_edge(START, "classify_query")
    
    # Classification routing (official LangGraph pattern)
    workflow.add_conditional_edges(
        "classify_query",
        route_after_classification,
        {
            "database": "list_tables",
            "conversational": "generate_response",
            "schema": "list_tables",
            "clarification": "clarification",
            "error": "generate_response"
        }
    )
    
    # Database workflow path
    workflow.add_edge("list_tables", "get_schema")

    # After schema: go to query planner or direct response (SCHEMA queries)
    workflow.add_conditional_edges(
        "get_schema",
        route_after_schema,
        {
            "plan_gate": "plan_gate",
            "generate_response": "generate_response",
        }
    )

    workflow.add_conditional_edges(
        "plan_gate",
        route_after_plan_gate,
        {
            "query_planner": "query_planner",
            "reasoning": "reasoning",
            "generate_sql": "generate_sql",
        }
    )

    # Query planner decides single vs multi path
    workflow.add_conditional_edges(
        "query_planner",
        route_after_query_planner,
        {
            "generate_sql": "generate_sql",      # single-query: existing pipeline
            "reasoning": "reasoning",             # complex single-query: CoT before generation
            "multi": "multi_sql_executor",        # multi-query: new path
        }
    )

    # Multi-query path
    workflow.add_edge("multi_sql_executor", "multi_verifier")
    workflow.add_conditional_edges(
        "multi_verifier",
        route_after_multi_verifier,
        {
            "result_synthesizer": "result_synthesizer",
            "generate_sql": "generate_sql",
        }
    )
    workflow.add_edge("result_synthesizer", END)

    workflow.add_edge("reasoning", "generate_sql")
    
    # Conditional repair routing (re-planning support)
    workflow.add_conditional_edges(
        "repair_sql",
        route_after_repair,
        {
            "reasoning": "reasoning",
            "validate_sql": "validate_sql"
        }
    )

    # SQL generation with retry (LangGraph pattern)
    # On success: generate_sql → vote_sql (majority voting) → validate_sql
    workflow.add_conditional_edges(
        "generate_sql",
        route_after_sql_generation,
        {
            "validate": "vote_sql",
            "retry": "generate_sql",
            "error": "generate_response"
        }
    )
    workflow.add_edge("vote_sql", "validate_sql")
    
    # SQL validation with retry (LangGraph pattern)
    workflow.add_conditional_edges(
        "validate_sql",
        route_after_sql_validation,
        {
            "execute": "execute_sql",
            # Route regeneration requests through repair_sql to leverage error context
            "retry_generation": "repair_sql",
            "retry_validation": "validate_sql",
            "error": "generate_response"
        }
    )
    
    # SQL execution with retry (LangGraph pattern)
    workflow.add_conditional_edges(
        "execute_sql",
        route_after_sql_execution,
        {
            "response": "generate_response",
            "retry_generation": "repair_sql",
            "retry_validation": "validate_sql", 
            "retry_execution": "execute_sql",
            "error": "generate_response"
        }
    )
    
    # Final response
    workflow.add_edge("generate_response", END)
    workflow.add_edge("clarification", END)
    
    return workflow


# =============================================================================
# WORKFLOW FACTORY FUNCTIONS - Official LangGraph Patterns
# =============================================================================

def create_sql_agent_workflow(checkpointer=None):
    """Create SQL Agent workflow following official LangGraph tutorial"""
    workflow = create_langgraph_sql_workflow()
    return workflow.compile(checkpointer=checkpointer)


def create_production_sql_agent(checkpointer=None):
    """Create production-ready SQL agent workflow"""
    return create_sql_agent_workflow(checkpointer=checkpointer)


def create_development_sql_agent(checkpointer=None):
    """Create development SQL agent workflow with debugging"""
    return create_sql_agent_workflow(checkpointer=checkpointer)


def create_testing_sql_agent(checkpointer=None):
    """Create testing SQL agent workflow"""
    return create_sql_agent_workflow(checkpointer=checkpointer)


# =============================================================================
# WORKFLOW EXECUTION HELPERS
# =============================================================================

def _estimate_query_complexity(user_query: str) -> str:
    """
    Estimate query complexity based on keywords and patterns

    Args:
        user_query: User's natural language question

    Returns:
        Complexity level: "simple", "medium", "hard", or "complex"
    """
    query_lower = user_query.lower()

    # Complex indicators
    complex_indicators = [
        "taxa de mortalidade",
        "top 10",
        "top 5",
        "ranking",
        "por município",
        "por cidade",
        "múltiplos",
        "comparar",
        "evolução",
        "tendência",
        "proporção",
        "percentual"
    ]

    # Hard indicators
    hard_indicators = [
        "join",
        "múltiplas tabelas",
        "habitantes",
        "população",
        "taxa",
        "cálculo",
        "agregação"
    ]

    # Medium indicators
    medium_indicators = [
        "ano",
        "data",
        "período",
        "filtrar",
        "grupo"
    ]

    # Count indicators
    complex_count = sum(1 for indicator in complex_indicators if indicator in query_lower)
    hard_count = sum(1 for indicator in hard_indicators if indicator in query_lower)
    medium_count = sum(1 for indicator in medium_indicators if indicator in query_lower)

    # Determine complexity
    if complex_count >= 2 or "taxa de mortalidade por município" in query_lower:
        return "complex"
    elif complex_count >= 1 or hard_count >= 2:
        return "hard"
    elif hard_count >= 1 or medium_count >= 2:
        return "medium"
    else:
        return "simple"


def execute_sql_workflow(
    workflow,
    user_query: str,
    session_id: str = None,
    config: dict = None,
    max_retries: int = 3,
    llm_manager = None,
    force_single_query: bool = True,
) -> dict:
    """
    Execute SQL workflow with proper error handling and adaptive recursion limit

    Args:
        workflow: Compiled LangGraph workflow
        user_query: User's natural language question
        session_id: Session identifier for checkpointing
        config: Additional configuration
        max_retries: Maximum retry attempts (default: 3)

    Returns:
        Execution result dictionary
    """

    try:
        # Import here to avoid circular dependencies
        from .state import create_initial_messages_state, state_to_legacy_format

        # Create initial state
        if session_id is None:
            session_id = f"session_{hash(user_query) % 10000}"

        initial_state = create_initial_messages_state(
            user_query=user_query,
            session_id=session_id,
            force_single_query=force_single_query,
        )

        config = config or {}

        # Inject LLM manager into config if provided
        if llm_manager:
            if "configurable" not in config:
                config["configurable"] = {}
            config["configurable"]["llm_manager"] = llm_manager

        # PHASE 1 IMPROVEMENT: Adaptive Recursion Limit
        # Estimate query complexity and set appropriate recursion limit
        if "recursion_limit" not in config:
            complexity = _estimate_query_complexity(user_query)
            recursion_limit_map = {
                "simple": 50,
                "medium": 75,
                "hard": 150,      # Increased from 100
                "complex": 200    # Increased from 150
            }
            config["recursion_limit"] = recursion_limit_map.get(complexity, 50)

            # Store complexity in config for debugging
            if "metadata" not in config:
                config["metadata"] = {}
            config["metadata"]["estimated_complexity"] = complexity
            config["metadata"]["recursion_limit"] = config["recursion_limit"]

        # Set max_retries for early stopping
        initial_state["max_retries"] = max_retries

        # Execute workflow
        final_state = workflow.invoke(initial_state, config=config)
        
        # Convert to legacy format for API compatibility
        result = state_to_legacy_format(final_state)
        
        return result
        
    except Exception as e:
        # Handle workflow execution errors
        return {
            "success": False,
            "question": user_query,
            "sql_query": None,
            "results": [],
            "row_count": 0,
            "execution_time": 0.0,
            "error_message": f"Workflow execution failed: {str(e)}",
            "response": f"Erro interno: {str(e)}",
            "timestamp": "2024-01-01T00:00:00",
            "metadata": {
                "langgraph_v3": True,
                "workflow_error": True,
                "error_type": "workflow_execution_error"
            }
        }


def stream_sql_workflow(
    workflow,
    user_query: str,
    session_id: str = None,
    config: dict = None,
    llm_manager = None
):
    """
    Stream SQL workflow execution for real-time updates
    
    Args:
        workflow: Compiled LangGraph workflow
        user_query: User's natural language question
        session_id: Session identifier
        config: Additional configuration
        
    Yields:
        State updates during workflow execution
    """
    
    try:
        # Import here to avoid circular dependencies
        from .state import create_initial_messages_state
        
        # Create initial state
        if session_id is None:
            session_id = f"session_{hash(user_query) % 10000}"
        
        initial_state = create_initial_messages_state(
            user_query=user_query,
            session_id=session_id
        )
        
        config = config or {}

        # Inject LLM manager into config if provided
        if llm_manager:
            if "configurable" not in config:
                config["configurable"] = {}
            config["configurable"]["llm_manager"] = llm_manager

        # Stream workflow execution
        for state_update in workflow.stream(initial_state, config=config):
            yield state_update
            
    except Exception as e:
        # Yield error state
        yield {
            "error": f"Workflow streaming failed: {str(e)}",
            "success": False
        }


# Export main factory functions
__all__ = [
    "create_langgraph_sql_workflow",
    "create_sql_agent_workflow", 
    "create_production_sql_agent",
    "create_development_sql_agent",
    "create_testing_sql_agent",
    "execute_sql_workflow",
    "stream_sql_workflow"
]
