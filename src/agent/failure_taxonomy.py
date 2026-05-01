"""Canonical failure taxonomy for the TXT2SQL agent.

Every error path in the pipeline should classify its failure into one of
the categories below.  The taxonomy is stored in ``state["failure_taxonomy"]``
as a list of strings so multiple failures can accumulate across retries.

Usage
-----
from .failure_taxonomy import TX, classify_sql_error

# in a node:
state = add_error(state, msg, "sql_execution_error", phase, taxonomy=TX.SYNTAX_ERROR)
"""

from __future__ import annotations


class TX:
    """Taxonomy string constants — use these instead of raw strings."""

    # SQL structure / DB schema
    SCHEMA_ERROR = "schema_error"          # wrong table or column name
    SYNTAX_ERROR = "syntax_error"          # SQL syntax rejected by the DB engine
    MISSING_JOIN = "missing_join"          # required JOIN omitted

    # Semantic / logic
    WRONG_TABLE_SELECTION = "wrong_table_selection"   # table selector chose wrong table
    WRONG_VALUE_MAPPING = "wrong_value_mapping"       # wrong SUS code / enum value
    WRONG_AGGREGATION = "wrong_aggregation"           # wrong agg function or GROUP BY
    WRONG_WINDOW = "wrong_window"                     # missing/wrong ROW_NUMBER OVER PARTITION
    WRONG_FILTER = "wrong_filter"                     # extra or missing WHERE clause
    NULL_SEMANTICS = "null_semantics"                 # NOT IN instead of NOT EXISTS

    # Pipeline
    COT_DRIFT = "cot_drift"          # planner produced wrong plan type
    REPAIR_LOOP = "repair_loop"      # repair budget exhausted without success

    # Infrastructure
    INFRA_ERROR = "infra_error"      # DB connection, timeout, API error


# Error-type string → default taxonomy mapping for add_error call sites
# that don't provide an explicit taxonomy.
_TYPE_TO_TAXONOMY: dict[str, str] = {
    "sql_execution_error": TX.SYNTAX_ERROR,
    "sql_validation_error": TX.WRONG_FILTER,
    "sql_generation_error": TX.SYNTAX_ERROR,
    "sql_repair_error": TX.REPAIR_LOOP,
    "table_discovery_error": TX.WRONG_TABLE_SELECTION,
    "classification_error": TX.COT_DRIFT,
}

# DB-level error substrings → more specific taxonomy
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
    """Return the most specific taxonomy category for a given error.

    Call sites may supply an explicit taxonomy to override this.
    """
    msg_lower = error_message.lower()
    for hint, category in _EXECUTION_ERROR_HINTS:
        if hint in msg_lower:
            return category
    return _TYPE_TO_TAXONOMY.get(error_type, TX.INFRA_ERROR)


__all__ = ["TX", "classify_sql_error"]
