"""Generic semantic SQL validators.

Validators operate on a SemanticPlan, not on benchmark question IDs. They catch
common semantic failures that still produce syntactically valid SQL.
"""

from __future__ import annotations

import re

from .contract_validator import validate_sql_contract
from .plan_schema import SemanticPlan
from .sql_inspector import SQLInspector


def _has_group_by_dimension(inspector: SQLInspector, dimension: str) -> bool:
    group_by_lower = inspector.clause_lower("GROUP BY")
    patterns = {
        "estado": [r"\bestado\b", r"\bmu\.estado\b", r"\bm\.estado\b"],
        "estado_hospital": [r"\bestado\b", r"\bmu\.estado\b", r"\bm\.estado\b"],
        "municipio": [r"\b(?:nome|municipio|município)\b"],
        "municipio_hospital": [r"\b(?:nome|municipio|município)\b"],
        "hospital": [r"\b(?:cnes|\"cnes\")\b"],
        "especialidade": [r"\bdescri[cç][aã]o\b", r"\bespec\b"],
        "diagnostico": [r"\b(?:cd_descricao|\"cd_descricao\"|diag_princ|cid)\b"],
        "procedimento": [r"\b(?:nome_proc|\"nome_proc\"|proc_rea)\b"],
        "sexo": [r"\bsexo\b"],
        "raca_cor": [r"\b(?:raca_cor|ra[cç]a|cor)\b"],
        "instrucao": [r"\b(?:instru|instrucao|instru[cç][aã]o|descri[cç][aã]o)\b"],
        "ano": [r"\b(?:extract\s*\(\s*year|ano)\b"],
    }
    return any(re.search(pattern, group_by_lower, re.I) for pattern in patterns.get(dimension, []))


def validate_sql_against_semantic_plan(
    plan: SemanticPlan | dict | None,
    sql: str,
    *,
    enable_contract_validation: bool = True,
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
        absence_antijoin = (
            "absence_condition_requires_antijoin_or_aggregate_zero" in plan.constraints
            and inspector.has_absence_pattern()
            and not inspector.has_group_by()
        )
        if not absence_antijoin:
            for dim in answer_shape.required_dimensions:
                if dim in {"faixa_etaria", "mes"}:
                    continue
                if dim in {
                    "estado",
                    "estado_hospital",
                    "municipio",
                    "municipio_hospital",
                    "hospital",
                    "especialidade",
                    "diagnostico",
                    "procedimento",
                    "sexo",
                    "raca_cor",
                    "instrucao",
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

    filter_passed, filter_message = _validate_required_filters(plan, inspector)
    if not filter_passed:
        return False, filter_message

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

    constraint_passed, constraint_message = _validate_additional_semantic_constraints(
        plan, inspector
    )
    if not constraint_passed:
        return False, constraint_message

    if answer_shape.row_grain == "time_series":
        if not any(dim in answer_shape.required_dimensions for dim in ["ano", "mes"]):
            return False, "SEMANTIC PLAN ERROR: Time-series plan lacks a temporal output dimension."
        if not inspector.has_group_by():
            return False, "SEMANTIC PLAN ERROR: Time-series SQL must group by a temporal dimension."
        if _has_unrequested_nonzero_metric_filter(inspector):
            return False, (
                "SEMANTIC PLAN ERROR: Time-series SQL filters metric values to non-zero rows, "
                "but the plan does not request dropping zero-valued periods or groups."
            )

    if enable_contract_validation:
        contract_result = validate_sql_contract(plan, sql)
        if not contract_result.passed:
            return False, contract_result.errors[0]

    return True, None


def _validate_additional_semantic_constraints(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    text = inspector.text_lower
    if "join_path_hospital_location_required" in plan.constraints:
        if not (
            re.search(r"\bhospital\b", text)
            and re.search(r"\bmunic_mov\b", text)
            and re.search(r"\bcnes\b", text)
        ):
            return False, (
                "SEMANTIC PLAN ERROR: The question refers to municipality/state of care or hospital location, "
                "but SQL does not use internacoes.CNES -> hospital.CNES -> hospital.MUNIC_MOV -> municipios.codigo_6d."
            )
        if re.search(r"\bmunic_res\b", text) and not re.search(r"\bmunic_mov\b", text):
            return False, (
                "SEMANTIC PLAN ERROR: SQL uses patient residence municipality (MUNIC_RES), but the question asks for care/hospital location."
            )

    if "domain_instrucao_valid_required" in plan.constraints:
        if "instrucao" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: The plan requires education-level labels, but SQL does not join/use instrucao."
            )
        if not re.search(r"\binstru\b[\s\S]{0,80}\bis\s+not\s+null\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Education-level analysis must exclude NULL INSTRU values."
            )
        if not re.search(r"\binstru\b\"?\s*(?:!=|<>)\s*0\b", text, re.I):
            return False, (
                "SEMANTIC PLAN ERROR: Education-level analysis must exclude INSTRU=0 unless unknown bucket is requested."
            )

    if "socioeconomico_metric_filter_required" in plan.constraints:
        expected_metrics = [
            value
            for semantic_filter in plan.filters
            if semantic_filter.field == "metrica"
            for value in semantic_filter.values
        ]
        if "socioeconomico" not in text:
            return False, (
                "SEMANTIC PLAN ERROR: The requested metric belongs to socioeconomico, but SQL does not use socioeconomico."
            )
        for expected_metric in expected_metrics:
            if expected_metric.lower() not in text:
                return False, (
                    f"SEMANTIC PLAN ERROR: SQL does not filter socioeconomico.metrica='{expected_metric}'."
                )

    if "top_n_average_high_cardinality_requires_minimum_group_size" in plan.constraints:
        min_counts = [
            int(value)
            for semantic_filter in plan.filters
            if semantic_filter.field == "minimum_group_count"
            for value in semantic_filter.values
            if str(value).isdigit()
        ]
        min_count = min_counts[0] if min_counts else 100
        having = inspector.clause_lower("HAVING") or text
        if not re.search(
            rf"\bcount\s*\([^)]*\)\s*(?:>|>=)\s*{min_count}\b", having, re.I
        ):
            return False, (
                "SEMANTIC PLAN ERROR: Top-N ranking by average/rate over high-cardinality entities "
                f"must apply HAVING COUNT(*) > {min_count} or an equivalent group-support threshold."
            )

    return True, None


def _validate_required_filters(
    plan: SemanticPlan,
    inspector: SQLInspector,
) -> tuple[bool, str | None]:
    text = inspector.text_lower
    where = inspector.clause_lower("WHERE")
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).lower() for value in semantic_filter.values]
        if field in {"estado", "estado_residencia"} and values:
            if not all(
                re.search(rf"['\"]?{re.escape(value.lower())}['\"]?", text) for value in values
            ):
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested estado filter."
                )
        elif field in {"ano", "ano_internacao"} and values:
            if not all(value in text for value in values):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested year filter."
        elif field == "sexo" and values:
            if "sexo" not in text or not any(value in text for value in values):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested sex filter."
        elif field == "uti":
            if "val_uti" not in text:
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested UTI filter."
        elif field == "desfecho" and any("morte" in value for value in values):
            if not re.search(r"\bmorte\b", where or text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not apply the requested death filter."
        elif field == "metrica" and values:
            if "metrica" not in text or not all(value in text for value in values):
                expected = ", ".join(values)
                return False, (
                    "SEMANTIC PLAN ERROR: SQL does not apply the requested metrica "
                    f"filter ({expected})."
                )
        elif field == "instrucao_valid":
            if not re.search(r"\binstru\b[\s\S]{0,80}\bis\s+not\s+null\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not exclude NULL INSTRU values."
            if not re.search(r"\binstru\b\"?\s*(?:!=|<>)\s*0\b", text, re.I):
                return False, "SEMANTIC PLAN ERROR: SQL does not exclude INSTRU=0."
    return True, None


def _has_unrequested_nonzero_metric_filter(inspector: SQLInspector) -> bool:
    predicate_text = " ".join(
        [
            inspector.clause_lower("WHERE"),
            inspector.clause_lower("HAVING"),
            inspector.clause_lower("QUALIFY"),
        ]
    )
    if not predicate_text:
        return False
    return bool(
        re.search(
            r"\b(?:[a-z_][\w]*\.)?(?:taxa|taxa_mortalidade|metric_value)\b\s*(?:>|>=)\s*0(?:\.0+)?\b",
            predicate_text,
            re.I,
        )
    )
