import logging
from typing import Literal

from .state_models import ExecutionPhase, MessagesStateTXT2SQL, QueryRoute
from .state_helpers import should_retry


COMPLEX_PLAN_TYPES_FOR_COT = {
    "global_local_avg",
    "single_cte",
    "set_intersection",
    "pivot_compare",
    "single_window",
}


def route_after_classification(
    state: MessagesStateTXT2SQL,
) -> Literal["database", "conversational", "schema", "clarification", "error"]:
    """Route after query classification."""
    if state.get("current_error") or not state.get("query_route"):
        return "error"

    query_route = state["query_route"]
    classification = state.get("classification")

    if state.get("needs_clarification"):
        return "clarification"

    if query_route == QueryRoute.CONVERSATIONAL:
        if classification and classification.confidence_score >= 0.7:
            return "conversational"
        return "database"

    if query_route == QueryRoute.SCHEMA:
        return "schema"

    if query_route == QueryRoute.DATABASE:
        return "database"

    return "database"


def route_after_schema(
    state: MessagesStateTXT2SQL,
) -> Literal["plan_gate", "generate_response"]:
    """Route after schema analysis."""
    if state.get("query_route") == QueryRoute.SCHEMA:
        return "generate_response"
    return "plan_gate"


def route_after_plan_gate(
    state: MessagesStateTXT2SQL,
) -> Literal["query_planner", "reasoning", "generate_sql"]:
    """Route after deterministic plan gate."""
    if state.get("multi_query_allowed") and not state.get("force_single_query"):
        return "query_planner"
    if state.get("plan_type") in COMPLEX_PLAN_TYPES_FOR_COT:
        return "reasoning"
    return "generate_sql"


def route_after_query_planner(
    state: MessagesStateTXT2SQL,
) -> Literal["generate_sql", "reasoning", "multi"]:
    """Route after query planner based on strategy decision."""
    if state.get("is_multi_query") and not state.get("force_single_query"):
        return "multi"
    if state.get("plan_type") in COMPLEX_PLAN_TYPES_FOR_COT:
        return "reasoning"
    return "generate_sql"


def route_after_multi_verifier(
    state: MessagesStateTXT2SQL,
) -> Literal["result_synthesizer", "generate_sql"]:
    """Fallback to single-query when multi verification fails."""
    if state.get("single_fallback_active"):
        return "generate_sql"
    return "result_synthesizer"


def route_after_sql_generation(
    state: MessagesStateTXT2SQL,
) -> Literal["validate", "retry", "error"]:
    """Route after SQL generation with retry logic."""
    if state.get("total_workflow_cycles", 0) > 15 or state.get("generation_retry_count", 0) >= 2:
        return "error"

    generated_sql = state.get("generated_sql")
    current_error = state.get("current_error")

    if generated_sql and not current_error:
        return "validate"

    if current_error and should_retry(state, "sql_generation_error"):
        return "retry"

    return "error"


def route_after_sql_validation(
    state: MessagesStateTXT2SQL,
) -> Literal["execute", "retry_generation", "retry_validation", "error"]:
    """Route after SQL validation with comprehensive retry logic."""
    if state.get("total_workflow_cycles", 0) > 15 or state.get("validation_retry_count", 0) >= 3:
        return "error"

    validated_sql = state.get("validated_sql")
    current_error = state.get("current_error")

    if validated_sql and not current_error:
        return "execute"

    if current_error and should_retry(state, "sql_validation_error"):
        error_message = current_error.lower()
        if any(keyword in error_message for keyword in ["syntax", "parse", "invalid"]):
            return "retry_generation"
        if any(keyword in error_message for keyword in ["table", "column", "field"]):
            return "retry_generation"
        return "retry_validation"

    return "error"


def route_after_repair(
    state: MessagesStateTXT2SQL,
) -> Literal["reasoning", "validate_sql"]:
    """Route after SQL repair."""
    if state.get("schema_refreshed"):
        return "reasoning"
    return "validate_sql"


def route_after_sql_execution(
    state: MessagesStateTXT2SQL,
) -> Literal["response", "retry_generation", "retry_validation", "retry_execution", "error"]:
    """Route after SQL execution with comprehensive retry logic."""
    total_cycles = state.get("total_workflow_cycles", 0)
    if total_cycles > 15:
        logger = logging.getLogger("txt2sql.workflow")
        logger.error("EMERGENCY STOP: Workflow exceeded 15 cycles. Forcing error exit.")
        return "error"

    sql_execution_result = state.get("sql_execution_result")
    if sql_execution_result and sql_execution_result.success:
        return "response"

    current_error = state.get("current_error")
    if current_error and should_retry(state, "sql_execution_error"):
        from src.utils.logging_config import get_logger

        logger = get_logger(__name__)
        logger.warning(
            f"RETRY: count={state.get('retry_count', 0)}/{state.get('max_retries', 3)}, "
            f"cycles={state.get('total_workflow_cycles', 0)}"
        )

        error_message = current_error.lower()
        if any(keyword in error_message for keyword in ["syntax", "parse", "invalid sql"]):
            return "retry_generation"
        if any(
            keyword in error_message
            for keyword in [
                "table",
                "column",
                "not found",
                "no such",
                "undefined function",
                "função",
                "operator does not exist",
                "cannot cast",
                "type mismatch",
            ]
        ):
            return "retry_generation"
        if any(keyword in error_message for keyword in ["timeout", "connection", "database"]):
            return "retry_execution"
        if any(keyword in error_message for keyword in ["constraint", "validation"]):
            return "retry_validation"
        return "retry_generation"

    return "error"


__all__ = [
    "COMPLEX_PLAN_TYPES_FOR_COT",
    "route_after_classification",
    "route_after_multi_verifier",
    "route_after_plan_gate",
    "route_after_query_planner",
    "route_after_repair",
    "route_after_schema",
    "route_after_sql_execution",
    "route_after_sql_generation",
    "route_after_sql_validation",
]
