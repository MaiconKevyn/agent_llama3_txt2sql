from dataclasses import asdict
from datetime import datetime
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from .state_models import (
    ExecutionPhase,
    MessagesStateTXT2SQL,
    QueryPlan,
    SQLExecutionResult,
    ToolCallResult,
)


def create_initial_messages_state(
    user_query: str,
    session_id: str,
    max_retries: int = 5,
    force_single_query: bool = False,
    ablation_flags: dict[str, bool] | None = None,
    visualization_intent: dict[str, Any] | None = None,
    chart_plan: dict[str, Any] | None = None,
) -> MessagesStateTXT2SQL:
    """Create the initial LangGraph messages state."""
    initial_message = HumanMessage(content=user_query)

    return MessagesStateTXT2SQL(
        messages=[initial_message],
        user_query=user_query,
        session_id=session_id,
        timestamp=datetime.now(),
        query_route=None,
        classification=None,
        requires_sql=False,
        current_phase=ExecutionPhase.INITIALIZATION,
        completed_phases=[],
        available_tables=[],
        selected_tables=[],
        schema_context="",
        reasoning_plan=None,
        generated_sql=None,
        validated_sql=None,
        sql_execution_result=None,
        tool_calls=[],
        pending_tool_calls=[],
        final_response=None,
        response_metadata={},
        errors=[],
        current_error=None,
        retry_count=0,
        max_retries=max_retries,
        total_workflow_cycles=0,
        generation_retry_count=0,
        validation_retry_count=0,
        execution_retry_count=0,
        execution_time_total=0.0,
        phase_timings={},
        success=False,
        completed=False,
        needs_clarification=False,
        clarification_question=None,
        query_plan=None,
        sub_query_results=[],
        is_multi_query=False,
        force_single_query=force_single_query,
        plan_type=None,
        execution_mode="single",
        multi_query_allowed=False,
        allowed_multi_plan_types=[],
        merged_rows=None,
        merged_rows_source=None,
        verifier_outcome=None,
        single_fallback_active=False,
        single_fallback_reason=None,
        final_sql_query=None,
        failure_taxonomy=[],
        final_result_rows=None,
        ablation_flags=ablation_flags or {},
        llamaindex_context=None,
        intent_plan=None,
        tool_plan=[],
        plan_audit=None,
        result_audit=None,
        structured_error=None,
        domain_caveats=[],
        semantic_plan=None,
        visualization_intent=visualization_intent,
        chart_plan=chart_plan,
        chart_spec=None,
    )


def serialize_query_plan(query_plan: QueryPlan | None) -> dict[str, Any] | None:
    """Convert QueryPlan dataclasses into a JSON-serializable dict."""
    if not query_plan:
        return None
    return asdict(query_plan)


def add_system_message(state: MessagesStateTXT2SQL, content: str) -> MessagesStateTXT2SQL:
    """Add a system message to the state."""
    system_message = SystemMessage(content=content)
    state["messages"] = add_messages(state["messages"], [system_message])
    return state


def add_ai_message(
    state: MessagesStateTXT2SQL,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> MessagesStateTXT2SQL:
    """Add an AI message to the state."""
    ai_message = AIMessage(content=content)
    if tool_calls:
        ai_message.tool_calls = tool_calls
    state["messages"] = add_messages(state["messages"], [ai_message])
    return state


def add_tool_message(
    state: MessagesStateTXT2SQL,
    tool_call_id: str,
    content: str,
    tool_name: str,
) -> MessagesStateTXT2SQL:
    """Add a tool message to the state."""
    tool_message = ToolMessage(
        content=content,
        tool_call_id=tool_call_id,
        name=tool_name,
    )
    state["messages"] = add_messages(state["messages"], [tool_message])
    return state


def update_phase(
    state: MessagesStateTXT2SQL,
    new_phase: ExecutionPhase,
    execution_time: float | None = None,
) -> MessagesStateTXT2SQL:
    """Update the current phase and accumulate timing."""
    if state["current_phase"] not in state["completed_phases"]:
        state["completed_phases"].append(state["current_phase"])

    state["current_phase"] = new_phase

    if execution_time is not None:
        phase_name = new_phase.value
        state["phase_timings"][phase_name] = execution_time
        state["execution_time_total"] += execution_time

    return state


def add_error(
    state: MessagesStateTXT2SQL,
    error_message: str,
    error_type: str,
    phase: ExecutionPhase,
    taxonomy: str | None = None,
) -> MessagesStateTXT2SQL:
    """Add an error entry to the state with context.

    If *taxonomy* is None the category is inferred from *error_type* and
    *error_message* via ``classify_sql_error``.
    """
    from .state_models import classify_sql_error

    resolved_taxonomy = taxonomy or classify_sql_error(error_type, error_message)

    error_entry = {
        "message": error_message,
        "type": error_type,
        "phase": phase.value,
        "timestamp": datetime.now().isoformat(),
        "retry_count": state["retry_count"],
        "taxonomy": resolved_taxonomy,
    }
    state["errors"].append(error_entry)
    state["current_error"] = error_message
    state["total_workflow_cycles"] = state.get("total_workflow_cycles", 0) + 1

    taxonomy_list: list[str] = list(state.get("failure_taxonomy") or [])
    if resolved_taxonomy not in taxonomy_list:
        taxonomy_list.append(resolved_taxonomy)
    state["failure_taxonomy"] = taxonomy_list

    return state


def add_tool_call_result(
    state: MessagesStateTXT2SQL,
    tool_result: ToolCallResult,
) -> MessagesStateTXT2SQL:
    """Add a tool call result and mirror it into message history."""
    state["tool_calls"].append(tool_result)
    return add_tool_message(
        state,
        tool_call_id=f"call_{len(state['tool_calls'])}",
        content=str(tool_result.tool_output),
        tool_name=tool_result.tool_name,
    )


def should_retry(state: MessagesStateTXT2SQL, error_type: str) -> bool:
    """Determine whether an operation should be retried."""
    current_retry = state["retry_count"]
    max_retries = state["max_retries"]
    retry_limits = {
        "sql_syntax_error": 3,
        "sql_validation_error": 3,
        "sql_execution_error": 2,
        "sql_generation_error": 2,
        "sql_repair_error": 2,
        "tool_execution_error": 5,
        "llm_timeout": 1,
        "database_connection_error": 3,
        "classification_error": 1,
        "schema_error": 3,
    }
    specific_limit = retry_limits.get(error_type, max_retries)
    return current_retry < min(specific_limit, max_retries)


def get_conversation_history(
    state: MessagesStateTXT2SQL,
    include_system: bool = False,
) -> list[BaseMessage]:
    """Get conversation history for LLM context."""
    messages = state["messages"]
    if not include_system:
        messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
    return messages


def format_for_llm_input(
    state: MessagesStateTXT2SQL,
    system_prompt: str | None = None,
) -> list[BaseMessage]:
    """Format the state for LLM input."""
    messages: list[BaseMessage] = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.extend(get_conversation_history(state, include_system=False))
    return messages


def extract_sql_from_messages(state: MessagesStateTXT2SQL) -> str | None:
    """Extract SQL from the latest relevant AI message."""
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage):
            content = message.content
            if any(
                keyword in content.lower() for keyword in ["select", "insert", "update", "delete"]
            ):
                sql = content.strip()
                if "```sql" in sql:
                    sql = sql.split("```sql")[1].split("```")[0].strip()
                elif "```" in sql:
                    sql = sql.split("```")[1].split("```")[0].strip()
                return sql
    return None


def get_latest_ai_response(state: MessagesStateTXT2SQL) -> str | None:
    """Get the latest AI response from messages."""
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage):
            return message.content
    return None


def calculate_success_metrics(state: MessagesStateTXT2SQL) -> dict[str, Any]:
    """Calculate workflow success metrics."""
    total_phases = len(ExecutionPhase)
    completed_phases = len(state["completed_phases"])
    success_rate = completed_phases / total_phases if total_phases > 0 else 0

    tool_success_rate = 0
    if state["tool_calls"]:
        successful_tools = sum(1 for tool in state["tool_calls"] if tool.success)
        tool_success_rate = successful_tools / len(state["tool_calls"])

    return {
        "overall_success": state["success"],
        "completion_rate": success_rate,
        "phases_completed": completed_phases,
        "total_phases": total_phases,
        "tool_success_rate": tool_success_rate,
        "total_tools_used": len(state["tool_calls"]),
        "retry_count": state["retry_count"],
        "error_count": len(state["errors"]),
        "execution_time": state["execution_time_total"],
    }


def state_to_legacy_format(state: MessagesStateTXT2SQL) -> dict[str, Any]:
    """Convert MessagesState into the legacy QueryResult format."""
    sql_query = (
        state.get("final_sql_query") or state.get("validated_sql") or state.get("generated_sql", "")
    )
    results = []
    row_count = 0
    execution_time = state.get("execution_time_total", 0.0)

    if state.get("sql_execution_result"):
        exec_result: SQLExecutionResult = state["sql_execution_result"]
        results = exec_result.results
        row_count = exec_result.row_count
        execution_time = exec_result.execution_time
    elif state.get("final_result_rows") is not None:
        final_rows = state.get("final_result_rows") or []
        results = [{"result": list(row) if isinstance(row, tuple) else row} for row in final_rows]
        row_count = len(final_rows)

    response_text = state.get("final_response") or get_latest_ai_response(state) or ""
    metrics = calculate_success_metrics(state)
    answerability = _derive_answerability(state, sql_query)
    technical_success = _derive_technical_success(state, answerability)

    return {
        "success": state["success"],
        "technical_success": technical_success,
        "answerability": answerability,
        "question": state["user_query"],
        "sql_query": sql_query,
        "results": results,
        "row_count": row_count,
        "execution_time": execution_time,
        "error_message": state.get("current_error"),
        "response": response_text,
        "timestamp": state["timestamp"].isoformat(),
        "final_result_rows": state.get("final_result_rows"),
        "chart": state.get("chart_spec"),
        "metadata": {
            "langgraph_v3": True,
            "messages_state": True,
            "query_route": state.get("query_route", {}).value if state.get("query_route") else None,
            "classification": {
                "route": state.get("classification", {}).route.value
                if state.get("classification")
                else None,
                "confidence": state.get("classification", {}).confidence_score
                if state.get("classification")
                else None,
                "requires_tools": state.get("classification", {}).requires_tools
                if state.get("classification")
                else False,
            },
            "workflow_metrics": metrics,
            "phases_completed": [phase.value for phase in state.get("completed_phases", [])],
            "current_phase": state.get("current_phase", {}).value
            if state.get("current_phase")
            else None,
            "tool_calls": [
                {
                    "name": tool.tool_name,
                    "success": tool.success,
                    "execution_time": tool.execution_time,
                }
                for tool in state.get("tool_calls", [])
            ],
            "message_count": len(state.get("messages", [])),
            "retry_count": state.get("retry_count", 0),
            "error_count": len(state.get("errors", [])),
            "tables_used": state.get("selected_tables", []),
            "schema_context_length": len(state.get("schema_context", "")),
            "latency_by_component": dict(state.get("phase_timings", {}) or {}),
            "multi_query": {
                "is_multi_query": state.get("is_multi_query", False),
                "plan_type": state.get("plan_type"),
                "execution_mode": state.get("execution_mode"),
                "multi_query_allowed": state.get("multi_query_allowed", False),
                "allowed_multi_plan_types": state.get("allowed_multi_plan_types", []),
                "query_plan": serialize_query_plan(state.get("query_plan")),
                "sub_query_results": state.get("sub_query_results", []),
                "merged_rows": state.get("merged_rows"),
                "merged_rows_source": state.get("merged_rows_source"),
                "merge_strategy": state.get("query_plan").merge_strategy
                if state.get("query_plan")
                else None,
                "verifier_outcome": state.get("verifier_outcome"),
                "single_fallback_active": state.get("single_fallback_active", False),
                "single_fallback_reason": state.get("single_fallback_reason"),
                "final_sql_query": state.get("final_sql_query"),
                "failure_taxonomy": state.get("failure_taxonomy", []),
            },
            "semantic_plan": state.get("semantic_plan"),
            "intent_plan": state.get("intent_plan"),
            "tool_plan": state.get("tool_plan", []),
            "plan_audit": state.get("plan_audit"),
            "result_audit": state.get("result_audit"),
            "structured_error": state.get("structured_error"),
            "answerability": answerability,
            "technical_success": technical_success,
            "domain_caveats": state.get("domain_caveats", []),
            "visualization_intent": state.get("visualization_intent"),
            "chart_plan": state.get("chart_plan"),
            "chart_spec": state.get("chart_spec"),
            **state.get("response_metadata", {}),
        },
    }


def _derive_answerability(state: MessagesStateTXT2SQL, sql_query: str) -> str:
    response_metadata = state.get("response_metadata", {}) or {}
    if response_metadata.get("unsupported_schema_metric"):
        return "unanswerable_schema"
    if state.get("needs_clarification") or response_metadata.get("critical_ambiguity"):
        return "requires_clarification"
    if state.get("current_error"):
        return "technical_error"
    if sql_query:
        return "answerable"
    return "unknown"


def _derive_technical_success(state: MessagesStateTXT2SQL, answerability: str) -> bool:
    if answerability in {"requires_clarification", "unanswerable_schema"}:
        return bool(state.get("final_response") or get_latest_ai_response(state))
    return bool(state.get("success")) and not bool(state.get("current_error"))


def validate_messages_state(state: MessagesStateTXT2SQL) -> list[str]:
    """Validate MessagesState consistency."""
    issues = []
    if not state.get("user_query"):
        issues.append("Missing user_query")
    if not state.get("session_id"):
        issues.append("Missing session_id")
    if not state.get("messages"):
        issues.append("Missing messages (MessagesState primary field)")

    messages = state.get("messages", [])
    if messages and not isinstance(messages[0], HumanMessage):
        issues.append("First message should be HumanMessage")

    current_phase = state.get("current_phase")
    completed_phases = state.get("completed_phases", [])
    if current_phase in completed_phases:
        issues.append("Current phase is marked as completed")

    tool_calls = state.get("tool_calls", [])
    tool_messages = [msg for msg in messages if isinstance(msg, ToolMessage)]
    if len(tool_calls) != len(tool_messages):
        issues.append("Tool calls and tool messages count mismatch")

    if state.get("retry_count", 0) > state.get("max_retries", 3):
        issues.append("Retry count exceeds maximum retries")

    return issues


_WORKFLOW_MSG_PREFIXES = ("Query classified as",)
MAX_CONVERSATION_TURNS = 10


def clean_conversation_messages(
    messages: list[BaseMessage],
    max_turns: int = MAX_CONVERSATION_TURNS,
) -> list[BaseMessage]:
    """Keep only conversation-relevant messages with a sliding window."""
    clean: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            clean.append(msg)
        elif isinstance(msg, AIMessage):
            content = msg.content
            if not any(content.startswith(prefix) for prefix in _WORKFLOW_MSG_PREFIXES):
                clean.append(msg)

    if len(clean) > max_turns * 2:
        clean = clean[-(max_turns * 2) :]

    return clean


create_txt2sql_messages_state = create_initial_messages_state


__all__ = [
    "MAX_CONVERSATION_TURNS",
    "add_ai_message",
    "add_error",
    "add_system_message",
    "add_tool_call_result",
    "add_tool_message",
    "calculate_success_metrics",
    "clean_conversation_messages",
    "create_initial_messages_state",
    "create_txt2sql_messages_state",
    "extract_sql_from_messages",
    "format_for_llm_input",
    "get_conversation_history",
    "get_latest_ai_response",
    "serialize_query_plan",
    "should_retry",
    "state_to_legacy_format",
    "update_phase",
    "validate_messages_state",
]
