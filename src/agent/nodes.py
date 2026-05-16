"""
nodes.py — thin re-export facade.

All logic lives in focused sub-modules. This module re-exports every public
symbol so that workflow.py and orchestrator.py continue to work unchanged.

Pipeline execution order (see workflow.py for the full graph):
  1. classification.py   — classify query (DATABASE / CONVERSATIONAL / SCHEMA)
  2. table_selection.py  — discover and select tables with LlamaIndex schema retrieval
  3. schema_node.py      — fetch schema for selected tables (cached)
  4. semantic_planner.py — reconcile heuristic and structured semantic plans
  5. sql_generation.py   — CoT planning and SQL generation
  5. validation.py       — validate SQL (DB EXPLAIN + semantic checks)
  6. execution.py        — execute SQL; repair_sql_node corrects on error
  7. response.py         — format final response in natural Portuguese

Shared utilities (not pipeline nodes):
  schema_utils.py        — schema parsing, column checks, suggestions
  llm_manager.py         — OpenAILLMManager + get/set_global_llm_manager singleton
"""

# LLM manager singleton (used by orchestrator)
# Node functions — in pipeline order
from .classification import query_classification_node  # noqa: F401  # step 1
from .execution import execute_sql_node, repair_sql_node  # noqa: F401  # step 6
from .llm_manager import OpenAILLMManager, get_llm_manager, set_global_llm_manager  # noqa: F401
from .multi_executor import multi_sql_executor_node  # noqa: F401
from .multi_verifier import multi_verifier_node  # noqa: F401
from .plan_gate import plan_gate_node  # noqa: F401
from .query_planner import query_planner_node  # noqa: F401
from .response import (  # noqa: F401  # step 7  # noqa: F401
    _generate_fallback_response,
    _generate_formatted_response,
    clarification_node,
    generate_response_node,
)
from .result_synthesizer import result_synthesizer_node  # noqa: F401
from .schema_node import (  # noqa: F401
    _enhance_sus_schema_context,
    _refresh_schema_context,
    _schema_cache,
    _should_refresh_schema,
    get_schema_node,  # noqa: F401  # step 3
)

# Internal helpers exposed for backward compatibility (tests, evaluation scripts)
from .schema_utils import (  # noqa: F401
    _best_column_suggestions,
    _check_columns_against_schema,
    _extract_alias_columns,
    _extract_alias_map,
    _parse_schema_columns,
)
from .semantic_planner import semantic_planner_node  # noqa: F401
from .sql_generation import (  # noqa: F401  # step 4
    SQLOutput,
    _build_pregeneration_hints,  # noqa: F401
    generate_sql_node,
    reasoning_node,
)
from .table_selection import (  # noqa: F401
    _validate_table_selection,
    list_tables_node,  # noqa: F401  # step 2
    select_tables_with_llamaindex,
)
from .validation import validate_sql_node  # noqa: F401  # step 5

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
    "semantic_planner_node",
    "get_llm_manager",
    "set_global_llm_manager",
    "query_planner_node",
    "multi_sql_executor_node",
    "multi_verifier_node",
    "result_synthesizer_node",
]
