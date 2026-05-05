"""Semantic SQL contract validation using structural SQL facts."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .catalog import SemanticCatalog, load_semantic_catalog
from .plan_schema import SemanticPlan
from .sql_ast import SQLAstSummary, parse_sql_ast


class SQLContractValidationResult(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    ast_summary: SQLAstSummary


def validate_sql_contract(
    plan: SemanticPlan | dict | None,
    sql: str,
    *,
    catalog: SemanticCatalog | None = None,
) -> SQLContractValidationResult:
    ast_summary = parse_sql_ast(sql)
    if not plan or not sql:
        return SQLContractValidationResult(passed=True, ast_summary=ast_summary)
    if isinstance(plan, dict):
        plan = SemanticPlan.model_validate(plan)

    catalog = catalog or load_semantic_catalog()
    errors: list[str] = []

    _validate_top_n_contract(plan, ast_summary, errors)
    _validate_rate_contract(plan, ast_summary, sql, errors)
    _validate_grouping_contract(plan, ast_summary, errors)
    _validate_catalog_join_paths(plan, ast_summary, catalog, errors)

    return SQLContractValidationResult(
        passed=not errors,
        errors=errors,
        ast_summary=ast_summary,
    )


def _validate_top_n_contract(
    plan: SemanticPlan,
    ast_summary: SQLAstSummary,
    errors: list[str],
) -> None:
    if plan.answer_shape.top_n_scope != "per_group":
        return
    if not ast_summary.window_functions:
        errors.append("AST CONTRACT ERROR: top-N per group requires a window ranking function.")
        return
    if not any(window.partition_by for window in ast_summary.window_functions):
        errors.append("AST CONTRACT ERROR: top-N per group window must declare PARTITION BY.")


def _validate_rate_contract(
    plan: SemanticPlan,
    ast_summary: SQLAstSummary,
    sql: str,
    errors: list[str],
) -> None:
    mortality_metric = any(metric.name == "taxa_mortalidade" for metric in plan.metrics)
    if not mortality_metric:
        return
    if re.search(r"\b\"?morte\"?\s*=\s*(?:true|1)\b", ast_summary.where, re.I):
        errors.append(
            "AST CONTRACT ERROR: mortality-rate denominator is filtered by MORTE in WHERE."
        )
    if not re.search(r"\bsum\s*\(\s*case\s+when[\s\S]*\b\"?morte\"?\b", sql, re.I):
        errors.append(
            "AST CONTRACT ERROR: mortality-rate numerator must use conditional aggregation."
        )


def _validate_grouping_contract(
    plan: SemanticPlan,
    ast_summary: SQLAstSummary,
    errors: list[str],
) -> None:
    if not plan.answer_shape.requires_group_by:
        return
    if (
        "absence_condition_requires_antijoin_or_aggregate_zero" in plan.constraints
        and _has_antijoin_entity_output(ast_summary)
    ):
        return
    group_by = ast_summary.group_by.lower()
    if not group_by:
        errors.append("AST CONTRACT ERROR: semantic plan requires GROUP BY but SQL has none.")
        return
    dimension_patterns = {
        "estado": [r"\bestado\b"],
        "sexo": [r"\bsexo\b"],
        "hospital": [r"\bcnes\b"],
        "procedimento": [r"\bnome_proc\b", r"\bproc_rea\b"],
        "ano": [r"\bano\b", r"\bextract\s*\(\s*year\b"],
    }
    for dimension in plan.answer_shape.required_dimensions:
        patterns = dimension_patterns.get(dimension)
        if patterns and not any(re.search(pattern, group_by, re.I) for pattern in patterns):
            errors.append(
                f"AST CONTRACT ERROR: GROUP BY does not include required dimension {dimension}."
            )


def _validate_catalog_join_paths(
    plan: SemanticPlan,
    ast_summary: SQLAstSummary,
    catalog: SemanticCatalog,
    errors: list[str],
) -> None:
    join_text = " ".join(join.condition or "" for join in ast_summary.joins).lower()
    if not join_text:
        return

    dimension_catalog_names = {
        "estado": ["estado_residencia", "estado_hospital"],
        "municipio": ["municipio_residencia"],
        "hospital": ["hospital"],
        "procedimento": ["procedimento"],
        "ano": ["ano_internacao"],
        "sexo": ["sexo"],
    }
    dimension_names = _stable_union(
        plan.answer_shape.required_dimensions,
        [dimension.name for dimension in plan.dimensions],
    )
    sql_tables = {table.lower() for table in ast_summary.tables}
    for dimension in dimension_names:
        catalog_names = dimension_catalog_names.get(dimension) or []
        catalog_names = _prefer_contextual_catalog_names(catalog_names, dimension_names)
        path_errors: list[str] = []
        checked_any_path = False
        for catalog_name in catalog_names:
            if catalog_name not in catalog.dimensions:
                continue
            join_path = catalog.dimensions[catalog_name].join_path
            path_tables = {_edge_table(edge, side=0) for edge in join_path} | {
                _edge_table(edge, side=1) for edge in join_path
            }
            path_tables.discard(None)
            if not path_tables.intersection(sql_tables):
                continue
            if catalog_name == "hospital" and "hospital" not in sql_tables:
                continue
            checked_any_path = True
            errors_for_path = _join_path_errors(dimension, join_path, join_text, sql_tables)
            if not errors_for_path:
                path_errors = []
                break
            path_errors.extend(errors_for_path)
        if checked_any_path and path_errors:
            errors.append(path_errors[0])


def _join_path_errors(
    dimension: str,
    join_path: list[str],
    join_text: str,
    sql_tables: set[str],
) -> list[str]:
    errors: list[str] = []
    for edge in join_path:
        left, right = _split_join_edge(edge)
        left_table = _edge_table(edge, side=0)
        right_table = _edge_table(edge, side=1)
        if not left or not right:
            continue
        left_present = left_table in sql_tables
        right_present = right_table in sql_tables
        if not left_present and not right_present:
            continue
        if not left_present or not right_present:
            errors.append(
                f"AST CONTRACT ERROR: SQL join path for {dimension} does not include catalog edge {edge}."
            )
            continue
        if not (_join_column_present(left, join_text) and _join_column_present(right, join_text)):
            errors.append(
                f"AST CONTRACT ERROR: SQL join path for {dimension} does not include catalog edge {edge}."
            )
    return errors


def _prefer_contextual_catalog_names(
    catalog_names: list[str], dimension_names: list[str]
) -> list[str]:
    if "hospital" in dimension_names and "estado_hospital" in catalog_names:
        return ["estado_hospital"] + [name for name in catalog_names if name != "estado_hospital"]
    return catalog_names


def _split_join_edge(edge: str) -> tuple[str | None, str | None]:
    if "->" not in edge:
        return None, None
    left, right = edge.split("->", 1)
    return left.strip(), right.strip()


def _join_column_present(reference: str, join_text: str) -> bool:
    column = reference.split(".")[-1].strip('"').lower()
    return bool(re.search(rf"\b\"?{re.escape(column)}\"?\b", join_text, re.I))


def _has_antijoin_entity_output(ast_summary: SQLAstSummary) -> bool:
    text = f"{ast_summary.where} {ast_summary.having}".lower()
    return (
        bool(re.search(r"\bnot\s+exists\b|\bis\s+null\b", text, re.I)) and not ast_summary.group_by
    )


def _edge_table(edge: str, side: int) -> str | None:
    left, right = _split_join_edge(edge)
    reference = left if side == 0 else right
    if not reference or "." not in reference:
        return None
    return reference.split(".", 1)[0].strip('"').lower()


def _stable_union(left: list[str], right: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in left + right:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
