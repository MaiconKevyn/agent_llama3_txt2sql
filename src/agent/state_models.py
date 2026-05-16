from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class QueryRoute(Enum):
    """Query routing options following LangGraph patterns."""

    DATABASE = "database"
    CONVERSATIONAL = "conversational"
    SCHEMA = "schema"
    TOOL_CALL = "tool_call"


class ExecutionPhase(Enum):
    """Enhanced execution phases for LangGraph workflow."""

    INITIALIZATION = "initialization"
    QUERY_CLASSIFICATION = "query_classification"
    TABLE_DISCOVERY = "table_discovery"
    SCHEMA_ANALYSIS = "schema_analysis"
    REASONING = "reasoning"
    SQL_GENERATION = "sql_generation"
    SQL_VALIDATION = "sql_validation"
    SQL_EXECUTION = "sql_execution"
    SQL_REPAIR = "sql_repair"
    TOOL_EXECUTION = "tool_execution"
    RESULT_INTERPRETATION = "result_interpretation"
    RESPONSE_FORMATTING = "response_formatting"
    ERROR_HANDLING = "error_handling"
    COMPLETED = "completed"


@dataclass
class QueryClassification:
    """Enhanced query classification following LangGraph patterns."""

    route: QueryRoute
    confidence_score: float
    reasoning: str
    requires_tools: bool
    estimated_complexity: float
    suggested_approach: str


@dataclass
class ToolCallResult:
    """Result from tool execution."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_output: Any
    success: bool
    execution_time: float
    error_message: str | None = None


@dataclass
class SubQuery:
    """A single SQL sub-query as part of a multi-query plan."""

    id: str
    description: str
    purpose: str = "final_output"
    output_role: str = "output"
    expected_result_kind: str = "rowset"
    expected_max_rows: int | None = None
    required_constraints: list[str] = field(default_factory=list)
    selected_tables: list[str] = field(default_factory=list)
    bind_keys: list[str] = field(default_factory=list)
    sql: str | None = None
    validated_sql: str | None = None
    result_raw: str | None = None
    parsed_rows: list[Any] | None = None
    success: bool = False
    error: str | None = None
    depends_on: list[str] = field(default_factory=list)
    repair_attempts: int = 0


@dataclass
class QueryPlan:
    """Execution plan decided by the query planner node."""

    strategy: str
    reasoning: str
    plan_type: str = "single_default"
    merge_strategy: str = "none"
    output_nodes: list[str] = field(default_factory=list)
    required_constraints: list[dict[str, Any]] = field(default_factory=list)
    expected_output_shape: dict[str, Any] = field(default_factory=dict)
    verifier_checks: list[str] = field(default_factory=list)
    fallback_policy: dict[str, Any] = field(default_factory=dict)
    sub_queries: list[SubQuery] = field(default_factory=list)


@dataclass
class SQLExecutionResult:
    """Enhanced SQL execution result."""

    success: bool
    sql_query: str
    results: list[dict[str, Any]]
    row_count: int
    execution_time: float
    validation_passed: bool
    error_message: str | None = None
    warnings: list[str] = None


class MessagesStateTXT2SQL(TypedDict):
    """Primary state following the LangGraph MessagesState pattern."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_query: str
    session_id: str
    timestamp: datetime
    query_route: QueryRoute | None
    classification: QueryClassification | None
    requires_sql: bool
    current_phase: ExecutionPhase
    completed_phases: list[ExecutionPhase]
    available_tables: list[str]
    selected_tables: list[str]
    schema_context: str
    reasoning_plan: str | None
    generated_sql: str | None
    validated_sql: str | None
    sql_execution_result: SQLExecutionResult | None
    tool_calls: list[ToolCallResult]
    pending_tool_calls: list[dict[str, Any]]
    final_response: str | None
    response_metadata: dict[str, Any]
    errors: list[dict[str, Any]]
    current_error: str | None
    retry_count: int
    max_retries: int
    total_workflow_cycles: int
    generation_retry_count: int
    validation_retry_count: int
    execution_retry_count: int
    execution_time_total: float
    phase_timings: dict[str, float]
    success: bool
    completed: bool
    needs_clarification: bool
    clarification_question: str | None
    query_plan: QueryPlan | None
    sub_query_results: list[dict[str, Any]]
    is_multi_query: bool
    force_single_query: bool
    plan_type: str | None
    execution_mode: str
    multi_query_allowed: bool
    allowed_multi_plan_types: list[str]
    merged_rows: list | None
    merged_rows_source: str | None
    verifier_outcome: dict[str, Any] | None
    single_fallback_active: bool
    single_fallback_reason: str | None
    final_sql_query: str | None
    failure_taxonomy: list[str]
    final_result_rows: list | None
    ablation_flags: dict[str, Any]
    llamaindex_context: dict[str, Any] | None
    semantic_plan: dict[str, Any] | None
    visualization_intent: dict[str, Any] | None
    chart_plan: dict[str, Any] | None
    chart_spec: dict[str, Any] | None


class TX:
    """Taxonomy string constants for SQL error classification."""

    SCHEMA_ERROR = "schema_error"
    SYNTAX_ERROR = "syntax_error"
    MISSING_JOIN = "missing_join"
    WRONG_TABLE_SELECTION = "wrong_table_selection"
    WRONG_VALUE_MAPPING = "wrong_value_mapping"
    WRONG_AGGREGATION = "wrong_aggregation"
    WRONG_WINDOW = "wrong_window"
    WRONG_FILTER = "wrong_filter"
    NULL_SEMANTICS = "null_semantics"
    COT_DRIFT = "cot_drift"
    REPAIR_LOOP = "repair_loop"
    INFRA_ERROR = "infra_error"


_TYPE_TO_TAXONOMY: dict[str, str] = {
    "sql_execution_error": TX.SYNTAX_ERROR,
    "sql_validation_error": TX.WRONG_FILTER,
    "sql_generation_error": TX.SYNTAX_ERROR,
    "sql_repair_error": TX.REPAIR_LOOP,
    "table_discovery_error": TX.WRONG_TABLE_SELECTION,
    "classification_error": TX.COT_DRIFT,
}

_EXECUTION_ERROR_HINTS: list[tuple[str, str]] = [
    ("does not exist", TX.SCHEMA_ERROR),
    ("não existe", TX.SCHEMA_ERROR),
    ("column", TX.SCHEMA_ERROR),
    ("coluna", TX.SCHEMA_ERROR),
    ("relation", TX.SCHEMA_ERROR),
    ("syntax error", TX.SYNTAX_ERROR),
    ("parse error", TX.SYNTAX_ERROR),
    ("blocked", TX.WRONG_FILTER),
]


def classify_sql_error(error_type: str, error_message: str = "") -> str:
    """Return the most specific taxonomy category for a given error."""
    msg_lower = error_message.lower()
    for hint, category in _EXECUTION_ERROR_HINTS:
        if hint in msg_lower:
            return category
    return _TYPE_TO_TAXONOMY.get(error_type, TX.INFRA_ERROR)


__all__ = [
    "ExecutionPhase",
    "MessagesStateTXT2SQL",
    "QueryClassification",
    "QueryPlan",
    "QueryRoute",
    "SQLExecutionResult",
    "SubQuery",
    "ToolCallResult",
    "TX",
    "classify_sql_error",
]
