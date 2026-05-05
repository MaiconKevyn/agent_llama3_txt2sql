"""Generic semantic SQL validators.

Validators operate on a SemanticPlan, not on benchmark question IDs. They catch
common semantic failures that still produce syntactically valid SQL.
"""

from __future__ import annotations

import re

from .plan_schema import SemanticPlan


def _has_group_by_dimension(sql_lower: str, dimension: str) -> bool:
    patterns = {
        "estado": [r"group\s+by[\s\S]*estado", r"group\s+by[\s\S]*mu\.estado", r"group\s+by[\s\S]*m\.estado"],
        "municipio": [r"group\s+by[\s\S]*(?:nome|municipio|município)"],
        "hospital": [r"group\s+by[\s\S]*(?:cnes|\"CNES\")".lower()],
        "especialidade": [r"group\s+by[\s\S]*descri[cç][aã]o", r"group\s+by[\s\S]*espec"],
        "diagnostico": [r"group\s+by[\s\S]*(?:cd_descricao|\"CD_DESCRICAO\"|diag_princ|cid)".lower()],
        "procedimento": [r"group\s+by[\s\S]*(?:nome_proc|\"NOME_PROC\"|proc_rea)".lower()],
        "sexo": [r"group\s+by[\s\S]*sexo"],
        "ano": [r"group\s+by[\s\S]*(?:extract\s*\(\s*year|ano)"],
    }
    return any(re.search(pattern, sql_lower, re.I) for pattern in patterns.get(dimension, []))


def validate_sql_against_semantic_plan(plan: SemanticPlan | dict | None, sql: str) -> tuple[bool, str | None]:
    """Return whether SQL satisfies the generic semantic plan constraints."""
    if not plan or not sql:
        return True, None

    if isinstance(plan, dict):
        plan = SemanticPlan.model_validate(plan)

    sql_lower = sql.lower()
    answer_shape = plan.answer_shape

    if answer_shape.top_n_scope == "per_group":
        if not re.search(r"\brow_number\s*\(\s*\)\s+over\s*\(", sql_lower, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires top-N per group, but SQL does not use "
                "ROW_NUMBER() OVER (...). Use a window function partitioned by the group dimension."
            )
        if not re.search(r"\bpartition\s+by\b", sql_lower, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires top-N per group, but SQL has no PARTITION BY."
            )
        if answer_shape.top_n is not None:
            rn_pattern = rf"\brn\s*(?:<=|<)\s*{answer_shape.top_n + 1 if answer_shape.top_n else answer_shape.top_n}\b|\brn\s*<=\s*{answer_shape.top_n}\b|\brn\s*=\s*1\b"
            if not re.search(rn_pattern, sql_lower, re.I):
                return False, (
                    "SEMANTIC PLAN ERROR: SQL uses a per-group window but does not constrain the "
                    f"rank to the requested top_n={answer_shape.top_n}."
                )

    if answer_shape.requires_group_by:
        for dim in answer_shape.required_dimensions:
            if dim in {"faixa_etaria", "mes"}:
                continue
            if dim in {"estado", "municipio", "hospital", "especialidade", "diagnostico", "procedimento", "sexo", "ano"}:
                if "group by" not in sql_lower:
                    return False, (
                        f"SEMANTIC PLAN ERROR: The plan requires grouping by {dim}, but SQL has no GROUP BY."
                    )

    if "rate_denominator_must_preserve_full_scope" in plan.constraints:
        mortality_metric = any(metric.name == "taxa_mortalidade" for metric in plan.metrics)
        if mortality_metric and re.search(r"\bwhere\b[\s\S]*\"?morte\"?\s*=\s*true", sql_lower, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Mortality-rate SQL filters MORTE=true in WHERE, which removes "
                "non-death rows from the denominator. Use conditional aggregation for the numerator."
            )
        if mortality_metric and not re.search(r"sum\s*\(\s*case\s+when[\s\S]*morte", sql_lower, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Mortality-rate SQL should compute deaths with conditional "
                "aggregation in the numerator."
            )

    if "absence_condition_requires_antijoin_or_aggregate_zero" in plan.constraints:
        has_antijoin = bool(re.search(r"\bnot\s+exists\b|\bleft\s+join\b[\s\S]*\bis\s+null\b", sql_lower, re.I))
        has_aggregate_zero = bool(re.search(r"sum\s*\(\s*case\s+when[\s\S]*(?:=\s*0|<=\s*0)", sql_lower, re.I))
        if not (has_antijoin or has_aggregate_zero):
            return False, (
                "SEMANTIC PLAN ERROR: The question asks for absence/non-occurrence, but SQL does not "
                "use NOT EXISTS, LEFT JOIN ... IS NULL, or an aggregate-zero HAVING condition."
            )

    if "include_unknown_bucket_with_left_join_or_coalesce" in plan.null_policy:
        if "coalesce" not in sql_lower:
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires an explicit unknown/no-information bucket, "
                "but SQL does not use COALESCE for null/unmatched labels."
            )
        if " join " in sql_lower and "left join" not in sql_lower:
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires preserving unknown/unmatched rows, but SQL "
                "does not use LEFT JOIN for the lookup."
            )

    if answer_shape.row_grain == "time_series":
        if not any(dim in answer_shape.required_dimensions for dim in ["ano", "mes"]):
            return False, "SEMANTIC PLAN ERROR: Time-series plan lacks a temporal output dimension."
        if "group by" not in sql_lower:
            return False, "SEMANTIC PLAN ERROR: Time-series SQL must group by a temporal dimension."

    return True, None
