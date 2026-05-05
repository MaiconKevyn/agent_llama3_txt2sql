"""Semantic planning and validation utilities for Text-to-SQL robustness."""

from .catalog import (
    load_semantic_catalog,
    render_catalog_context_for_plan,
    render_catalog_prompt_context,
)
from .catalog_schema import assert_valid_semantic_catalog, validate_semantic_catalog
from .contract_validator import SQLContractValidationResult, validate_sql_contract
from .data_profile import (
    ColumnProfile,
    ColumnProfileSpec,
    SemanticProfile,
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
from .plan_reconciler import PlanReconciliationResult, reconcile_semantic_plans
from .plan_schema import (
    AnswerShape,
    SemanticDimension,
    SemanticFilter,
    SemanticMetric,
    SemanticPlan,
)
from .planner import build_semantic_plan
from .profile_store import SemanticProfileStore, load_profile_store, load_semantic_profile
from .sql_ast import SQLAstSummary, SQLJoinEdge, SQLWindowFunction, parse_sql_ast
from .validators import validate_sql_against_semantic_plan

__all__ = [
    "AnswerShape",
    "SemanticDimension",
    "SemanticFilter",
    "SemanticMetric",
    "SemanticPlan",
    "PlanReconciliationResult",
    "ColumnProfile",
    "ColumnProfileSpec",
    "SemanticProfile",
    "SemanticErrorCategory",
    "SemanticErrorRecord",
    "SemanticProfileStore",
    "TableProfile",
    "SQLSemanticSignature",
    "SQLAstSummary",
    "SQLContractValidationResult",
    "SQLJoinEdge",
    "SQLWindowFunction",
    "assert_valid_semantic_catalog",
    "build_semantic_error_record",
    "build_semantic_plan",
    "build_column_profile_queries",
    "build_default_profile_query_sets",
    "classify_semantic_error",
    "load_semantic_catalog",
    "load_semantic_profile",
    "load_profile_store",
    "parse_sql_ast",
    "render_catalog_context_for_plan",
    "render_catalog_prompt_context",
    "reconcile_semantic_plans",
    "same_semantic_pattern",
    "semantic_sql_signature",
    "validate_sql_contract",
    "validate_semantic_catalog",
    "validate_sql_against_semantic_plan",
]
