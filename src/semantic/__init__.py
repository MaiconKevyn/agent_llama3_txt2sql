"""Semantic planning and validation utilities for Text-to-SQL robustness."""

from .catalog import (
    load_semantic_catalog,
    render_catalog_context_for_plan,
    render_catalog_prompt_context,
)
from .data_profile import (
    ColumnProfile,
    ColumnProfileSpec,
    TableProfile,
    build_column_profile_queries,
    build_default_profile_query_sets,
)
from .equivalence import SQLSemanticSignature, same_semantic_pattern, semantic_sql_signature
from .error_taxonomy import (
    SemanticErrorCategory,
    SemanticErrorRecord,
    build_semantic_error_record,
    classify_semantic_error,
)
from .plan_schema import (
    AnswerShape,
    SemanticDimension,
    SemanticFilter,
    SemanticMetric,
    SemanticPlan,
)
from .planner import build_semantic_plan
from .validators import validate_sql_against_semantic_plan

__all__ = [
    "AnswerShape",
    "SemanticDimension",
    "SemanticFilter",
    "SemanticMetric",
    "SemanticPlan",
    "ColumnProfile",
    "ColumnProfileSpec",
    "SemanticErrorCategory",
    "SemanticErrorRecord",
    "TableProfile",
    "SQLSemanticSignature",
    "build_semantic_error_record",
    "build_semantic_plan",
    "build_column_profile_queries",
    "build_default_profile_query_sets",
    "classify_semantic_error",
    "load_semantic_catalog",
    "render_catalog_context_for_plan",
    "render_catalog_prompt_context",
    "same_semantic_pattern",
    "semantic_sql_signature",
    "validate_sql_against_semantic_plan",
]
