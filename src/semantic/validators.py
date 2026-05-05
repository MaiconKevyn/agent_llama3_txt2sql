"""Generic semantic SQL validators.

Validators operate on a SemanticPlan, not on benchmark question IDs. They catch
common semantic failures that still produce syntactically valid SQL.
"""

from __future__ import annotations

import re

from .plan_schema import SemanticPlan
from .sql_inspector import SQLInspector


def _has_group_by_dimension(inspector: SQLInspector, dimension: str) -> bool:
    group_by_lower = inspector.clause_lower("GROUP BY")
    patterns = {
        "estado": [r"\bestado\b", r"\bmu\.estado\b", r"\bm\.estado\b"],
        "municipio": [r"\b(?:nome|municipio|município)\b"],
        "hospital": [r"\b(?:cnes|\"cnes\")\b"],
        "especialidade": [r"\bdescri[cç][aã]o\b", r"\bespec\b"],
        "diagnostico": [r"\b(?:cd_descricao|\"cd_descricao\"|diag_princ|cid)\b"],
        "procedimento": [r"\b(?:nome_proc|\"nome_proc\"|proc_rea)\b"],
        "sexo": [r"\bsexo\b"],
        "ano": [r"\b(?:extract\s*\(\s*year|ano)\b"],
    }
    return any(re.search(pattern, group_by_lower, re.I) for pattern in patterns.get(dimension, []))


def validate_sql_against_semantic_plan(
    plan: SemanticPlan | dict | None, sql: str
) -> tuple[bool, str | None]:
    """Return whether SQL satisfies the generic semantic plan constraints."""
    if not plan or not sql:
        return True, None

    if isinstance(plan, dict):
        plan = SemanticPlan.model_validate(plan)

    inspector = SQLInspector.from_sql(sql)
    sql_lower = inspector.text_lower
    answer_shape = plan.answer_shape

    if answer_shape.top_n_scope == "per_group":
        if not re.search(
            r"\b(?:row_number|rank|dense_rank)\s*\(\s*\)\s+over\s*\(", sql_lower, re.I
        ):
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires top-N per group, but SQL does not use "
                "ROW_NUMBER()/RANK() OVER (...). Use a window function partitioned by the group dimension."
            )
        if not inspector.has_window_partition():
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires top-N per group, but SQL has no PARTITION BY."
            )
        if not inspector.constrains_rank(answer_shape.top_n):
            return False, (
                "SEMANTIC PLAN ERROR: SQL uses a per-group window but does not constrain the "
                f"rank to the requested top_n={answer_shape.top_n}."
            )

    if answer_shape.requires_group_by:
        for dim in answer_shape.required_dimensions:
            if dim in {"faixa_etaria", "mes"}:
                continue
            if dim in {
                "estado",
                "municipio",
                "hospital",
                "especialidade",
                "diagnostico",
                "procedimento",
                "sexo",
                "ano",
            }:
                if not inspector.has_group_by():
                    return False, (
                        f"SEMANTIC PLAN ERROR: The plan requires grouping by {dim}, but SQL has no GROUP BY."
                    )
                if not _has_group_by_dimension(inspector, dim):
                    return False, (
                        f"SEMANTIC PLAN ERROR: The plan requires grouping by {dim}, but SQL GROUP BY does not include that dimension."
                    )

    if "rate_denominator_must_preserve_full_scope" in plan.constraints:
        mortality_metric = any(metric.name == "taxa_mortalidade" for metric in plan.metrics)
        if mortality_metric and inspector.where_filters_outcome("morte", "true"):
            return False, (
                "SEMANTIC PLAN ERROR: Mortality-rate SQL filters MORTE=true in WHERE, which removes "
                "non-death rows from the denominator. Use conditional aggregation for the numerator."
            )
        if mortality_metric and not inspector.has_conditional_aggregation_for("morte"):
            return False, (
                "SEMANTIC PLAN ERROR: Mortality-rate SQL should compute deaths with conditional "
                "aggregation in the numerator."
            )

    if "absence_condition_requires_antijoin_or_aggregate_zero" in plan.constraints:
        if not inspector.has_absence_pattern():
            return False, (
                "SEMANTIC PLAN ERROR: The question asks for absence/non-occurrence, but SQL does not "
                "use NOT EXISTS, LEFT JOIN ... IS NULL, or an aggregate-zero HAVING condition."
            )

    if "include_unknown_bucket_with_left_join_or_coalesce" in plan.null_policy:
        if not inspector.has_unknown_bucket_expression():
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires an explicit unknown/no-information bucket, "
                "but SQL does not use COALESCE or CASE for null/unmatched labels."
            )
        if not inspector.joins_preserve_unknowns():
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires preserving unknown/unmatched rows, but SQL "
                "does not use LEFT JOIN for the lookup."
            )

    if answer_shape.row_grain == "time_series":
        if not any(dim in answer_shape.required_dimensions for dim in ["ano", "mes"]):
            return False, "SEMANTIC PLAN ERROR: Time-series plan lacks a temporal output dimension."
        if not inspector.has_group_by():
            return False, "SEMANTIC PLAN ERROR: Time-series SQL must group by a temporal dimension."

    return True, None
