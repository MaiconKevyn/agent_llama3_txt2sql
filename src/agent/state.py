"""Compatibility facade for state models and helper functions.

This module preserves the historical import surface while delegating the actual
implementation to `state_models.py` and `state_helpers.py`.
"""

from .state_models import (
    ExecutionPhase,
    MessagesStateTXT2SQL,
    QueryClassification,
    QueryPlan,
    QueryRoute,
    SQLExecutionResult,
    SubQuery,
    ToolCallResult,
)
from .state_helpers import (
    MAX_CONVERSATION_TURNS,
    add_ai_message,
    add_error,
    add_system_message,
    add_tool_call_result,
    add_tool_message,
    calculate_success_metrics,
    clean_conversation_messages,
    create_initial_messages_state,
    create_txt2sql_messages_state,
    extract_sql_from_messages,
    format_for_llm_input,
    get_conversation_history,
    get_latest_ai_response,
    serialize_query_plan,
    should_retry,
    state_to_legacy_format,
    update_phase,
    validate_messages_state,
)

__all__ = [
    "ExecutionPhase",
    "MAX_CONVERSATION_TURNS",
    "MessagesStateTXT2SQL",
    "QueryClassification",
    "QueryPlan",
    "QueryRoute",
    "SQLExecutionResult",
    "SubQuery",
    "ToolCallResult",
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
