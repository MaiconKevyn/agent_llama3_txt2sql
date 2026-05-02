"""
nodes.py — thin re-export facade.

All logic lives in focused sub-modules. This module re-exports every public
symbol so that workflow.py and orchestrator.py continue to work unchanged.

Pipeline execution order (see workflow.py for the full graph):
  1. classification.py   — classify query (DATABASE / CONVERSATIONAL / SCHEMA)
  2. table_selection.py  — discover and select tables (heuristic → embedding → LLM)
  3. schema_node.py      — fetch schema for selected tables (cached)
  4. sql_generation.py   — CoT planning and SQL generation
  5. validation.py       — validate SQL (DB EXPLAIN + semantic checks)
  6. execution.py        — execute SQL; repair_sql_node corrects on error
  7. response.py         — format final response in natural Portuguese

Shared utilities (not pipeline nodes):
  schema_utils.py        — schema parsing, column checks, suggestions
  table_selector.py      — EmbeddingTableSelector (Stage 2 of table selection)
  llm_manager.py         — OpenAILLMManager + get/set_global_llm_manager singleton
"""

# LLM manager singleton (used by orchestrator)
from .llm_manager import get_llm_manager, set_global_llm_manager, OpenAILLMManager  # noqa: F401

# Node functions — in pipeline order
from .classification import query_classification_node  # noqa: F401  # step 1
from .table_selection import list_tables_node          # noqa: F401  # step 2
from .schema_node import get_schema_node               # noqa: F401  # step 3
from .sql_generation import (                          # noqa: F401  # step 4
    generate_sql_node,
    reasoning_node,
    SQLOutput,
)
from .validation import validate_sql_node              # noqa: F401  # step 5
from .execution import execute_sql_node, repair_sql_node  # noqa: F401  # step 6
from .response import generate_response_node, clarification_node  # noqa: F401  # step 7
from .plan_gate import plan_gate_node                  # noqa: F401

# Internal helpers exposed for backward compatibility (tests, evaluation scripts)
from .schema_utils import (  # noqa: F401
    _parse_schema_columns,
    _extract_alias_map,
    _extract_alias_columns,
    _best_column_suggestions,
    _check_columns_against_schema,
)
from .schema_node import (  # noqa: F401
    _schema_cache,
    _should_refresh_schema,
    _refresh_schema_context,
    _enhance_sus_schema_context,
)
from .table_selection import (  # noqa: F401
    _heuristic_table_selection,
    _select_relevant_tables,
    _parse_llm_table_selection,
    _validate_table_selection,
    _get_intelligent_fallback,
)
from .sql_generation import _build_pregeneration_hints  # noqa: F401
from .response import _generate_formatted_response, _generate_fallback_response  # noqa: F401
from .query_planner import query_planner_node  # noqa: F401
from .multi_executor import multi_sql_executor_node  # noqa: F401
from .multi_verifier import multi_verifier_node  # noqa: F401
from .result_synthesizer import result_synthesizer_node  # noqa: F401

__all__ = [
    "query_classification_node",
    "list_tables_node",
    "get_schema_node",
    "reasoning_node",
    "generate_sql_node",
    "repair_sql_node",
    "validate_sql_node",
    "execute_sql_node",
    "generate_response_node",
    "clarification_node",
    "plan_gate_node",
    "get_llm_manager",
    "set_global_llm_manager",
    "query_planner_node",
    "multi_sql_executor_node",
    "multi_verifier_node",
    "result_synthesizer_node",
]
