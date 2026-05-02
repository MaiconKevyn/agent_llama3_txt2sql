from typing import TypedDict, Optional, List, Dict, Any, Annotated, Sequence
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


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
    tool_input: Dict[str, Any]
    tool_output: Any
    success: bool
    execution_time: float
    error_message: Optional[str] = None


@dataclass
class SubQuery:
    """A single SQL sub-query as part of a multi-query plan."""

    id: str
    description: str
    purpose: str = "final_output"
    output_role: str = "output"
    expected_result_kind: str = "rowset"
    expected_max_rows: Optional[int] = None
    required_constraints: List[str] = field(default_factory=list)
    selected_tables: List[str] = field(default_factory=list)
    bind_keys: List[str] = field(default_factory=list)
    sql: Optional[str] = None
    validated_sql: Optional[str] = None
    result_raw: Optional[str] = None
    parsed_rows: Optional[List[Any]] = None
    success: bool = False
    error: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    repair_attempts: int = 0


@dataclass
class QueryPlan:
    """Execution plan decided by the query planner node."""

    strategy: str
    reasoning: str
    plan_type: str = "single_default"
    merge_strategy: str = "none"
    output_nodes: List[str] = field(default_factory=list)
    required_constraints: List[Dict[str, Any]] = field(default_factory=list)
    expected_output_shape: Dict[str, Any] = field(default_factory=dict)
    verifier_checks: List[str] = field(default_factory=list)
    fallback_policy: Dict[str, Any] = field(default_factory=dict)
    sub_queries: List[SubQuery] = field(default_factory=list)


@dataclass
class SQLExecutionResult:
    """Enhanced SQL execution result."""

    success: bool
    sql_query: str
    results: List[Dict[str, Any]]
    row_count: int
    execution_time: float
    validation_passed: bool
    error_message: Optional[str] = None
    warnings: List[str] = None


class MessagesStateTXT2SQL(TypedDict):
    """Primary state following the LangGraph MessagesState pattern."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_query: str
    session_id: str
    timestamp: datetime
    query_route: Optional[QueryRoute]
    classification: Optional[QueryClassification]
    requires_sql: bool
    current_phase: ExecutionPhase
    completed_phases: List[ExecutionPhase]
    available_tables: List[str]
    selected_tables: List[str]
    schema_context: str
    reasoning_plan: Optional[str]
    generated_sql: Optional[str]
    validated_sql: Optional[str]
    sql_execution_result: Optional[SQLExecutionResult]
    sql_candidates: Optional[List[Dict[str, Any]]]
    tool_calls: List[ToolCallResult]
    pending_tool_calls: List[Dict[str, Any]]
    final_response: Optional[str]
    response_metadata: Dict[str, Any]
    errors: List[Dict[str, Any]]
    current_error: Optional[str]
    retry_count: int
    max_retries: int
    total_workflow_cycles: int
    generation_retry_count: int
    validation_retry_count: int
    execution_retry_count: int
    execution_time_total: float
    phase_timings: Dict[str, float]
    success: bool
    completed: bool
    needs_clarification: bool
    clarification_question: Optional[str]
    query_plan: Optional[QueryPlan]
    sub_query_results: List[Dict[str, Any]]
    is_multi_query: bool
    force_single_query: bool
    plan_type: Optional[str]
    execution_mode: str
    multi_query_allowed: bool
    allowed_multi_plan_types: List[str]
    merged_rows: Optional[List]
    merged_rows_source: Optional[str]
    verifier_outcome: Optional[Dict[str, Any]]
    single_fallback_active: bool
    single_fallback_reason: Optional[str]
    final_sql_query: Optional[str]
    failure_taxonomy: List[str]
    final_result_rows: Optional[List]
    ablation_flags: Dict[str, bool]


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
