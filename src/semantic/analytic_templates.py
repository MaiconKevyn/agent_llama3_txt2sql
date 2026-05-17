"""Catalog of reusable analytic response templates."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .plan_schema import SemanticPlan


class AnalyticTemplate(BaseModel):
    """Declarative contract for one analytic answer family."""

    id: str
    description: str
    intent: str
    factor_dimensions: list[str] = Field(default_factory=list)
    condition_fields: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    required_sections: list[str] = Field(default_factory=list)
    sql_shape: str
    denominator_policy: str


ANALYTIC_TEMPLATES: dict[str, AnalyticTemplate] = {
    "numeric_factor_by_condition": AnalyticTemplate(
        id="numeric_factor_by_condition",
        description="Numeric factor, especially age, crossed with a diagnosis or outcome.",
        intent="association",
        factor_dimensions=["idade", "faixa_etaria"],
        condition_fields=[
            "diagnostico_principal_codigo",
            "diagnostico_principal_prefix",
            "diagnostico_principal_descricao",
        ],
        required_metrics=[
            "total_internacoes",
            "taxa_por_denominador",
            "razao_taxas",
            "idade_media",
            "idade_mediana",
        ],
        required_sections=[
            "direct_answer",
            "scope",
            "denominator",
            "group_distribution",
            "effect_summary",
            "limitations",
        ],
        sql_shape="one_row_cte_package",
        denominator_policy="same_scope_without_target_condition_by_age_band",
    ),
    "categorical_factor_by_outcome": AnalyticTemplate(
        id="categorical_factor_by_outcome",
        description="Categorical demographic factor crossed with an observed outcome, optionally within a resolved clinical cohort.",
        intent="association",
        factor_dimensions=["sexo", "raca_cor", "instrucao"],
        condition_fields=[
            "desfecho",
            "diagnostico_principal_codigo",
            "diagnostico_principal_prefix",
            "diagnostico_principal_descricao",
        ],
        required_metrics=["total_internacoes", "total_mortes", "taxa_mortalidade"],
        required_sections=[
            "direct_answer",
            "scope",
            "denominator",
            "group_distribution",
            "effect_summary",
            "limitations",
        ],
        sql_shape="grouped_distribution_with_rate",
        denominator_policy="all_rows_matching_non_outcome_filters_per_category",
    ),
    "geographic_factor_by_condition": AnalyticTemplate(
        id="geographic_factor_by_condition",
        description="Geographic grouping crossed with a diagnosis or outcome.",
        intent="comparison",
        factor_dimensions=["estado", "estado_hospital", "municipio", "municipio_hospital"],
        condition_fields=[
            "diagnostico_principal_codigo",
            "diagnostico_principal_prefix",
            "diagnostico_principal_descricao",
            "desfecho",
        ],
        required_metrics=["total_internacoes", "taxa_por_denominador"],
        required_sections=["direct_answer", "scope", "denominator", "group_distribution"],
        sql_shape="grouped_distribution_with_support",
        denominator_policy="same_geographic_scope_per_group",
    ),
    "temporal_trend_by_condition": AnalyticTemplate(
        id="temporal_trend_by_condition",
        description="Temporal evolution of a diagnosis, outcome, or filtered cohort.",
        intent="trend",
        factor_dimensions=["ano", "mes"],
        condition_fields=[
            "diagnostico_principal_codigo",
            "diagnostico_principal_prefix",
            "diagnostico_principal_descricao",
            "desfecho",
        ],
        required_metrics=["total_internacoes", "delta_temporal"],
        required_sections=["direct_answer", "scope", "time_series", "trend_summary", "limitations"],
        sql_shape="time_series",
        denominator_policy="period_rows_matching_same_condition",
    ),
}


def select_analytic_template(plan: SemanticPlan | dict | None) -> AnalyticTemplate | None:
    """Select the best analytic template for a semantic plan."""
    if not plan:
        return None
    parsed = plan if isinstance(plan, SemanticPlan) else SemanticPlan.model_validate(plan)
    constraints = set(parsed.constraints)
    required_dimensions = set(parsed.answer_shape.required_dimensions)
    filter_fields = {semantic_filter.field for semantic_filter in parsed.filters}

    if "age_diagnosis_association_required" in constraints:
        return ANALYTIC_TEMPLATES["numeric_factor_by_condition"]
    if "categorical_outcome_association_required" in constraints:
        return ANALYTIC_TEMPLATES["categorical_factor_by_outcome"]
    diagnosis_filter_fields = {
        "diagnostico_principal_codigo",
        "diagnostico_principal_prefix",
        "diagnostico_principal_descricao",
    }
    if parsed.intent == "trend" and required_dimensions & {"ano", "mes"} and (
        filter_fields & (diagnosis_filter_fields | {"desfecho"})
    ):
        return ANALYTIC_TEMPLATES["temporal_trend_by_condition"]
    if required_dimensions & {
        "estado",
        "estado_hospital",
        "municipio",
        "municipio_hospital",
    } and filter_fields & (diagnosis_filter_fields | {"desfecho"}):
        return ANALYTIC_TEMPLATES["geographic_factor_by_condition"]
    return None


def analytic_metadata_for_plan(plan: SemanticPlan | dict | None) -> dict[str, object]:
    """Return compact trace metadata for analytic plans."""
    if not plan:
        return {}
    parsed = plan if isinstance(plan, SemanticPlan) else SemanticPlan.model_validate(plan)
    template = select_analytic_template(parsed)
    if template is None:
        return {}
    concept_resolution = _concept_resolution_metadata(parsed)
    return {
        "analytic_intent": parsed.intent,
        "analytic_template": template.id,
        "denominator_policy": template.denominator_policy,
        "analytic_sections_present": list(template.required_sections),
        "concept_resolution": concept_resolution,
    }


def _concept_resolution_metadata(plan: SemanticPlan) -> dict[str, object]:
    codes: list[str] = []
    prefixes: list[str] = []
    labels: list[str] = []
    description_terms: list[str] = []
    for semantic_filter in plan.filters:
        if semantic_filter.field == "diagnostico_principal_codigo":
            codes.extend(str(value) for value in semantic_filter.values)
        elif semantic_filter.field == "diagnostico_principal_prefix":
            prefixes.extend(str(value) for value in semantic_filter.values)
        elif semantic_filter.field == "diagnostico_conceito_label":
            labels.extend(str(value) for value in semantic_filter.values)
        elif semantic_filter.field == "diagnostico_principal_descricao":
            description_terms.extend(str(value) for value in semantic_filter.values)
    return {
        "diagnosis_codes": codes,
        "diagnosis_prefixes": prefixes,
        "diagnosis_description_terms": description_terms,
        "labels": labels,
        "resolved": bool(codes or prefixes or labels or description_terms),
    }
