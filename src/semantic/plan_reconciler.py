"""Reconcile heuristic and LLM semantic plans without benchmark-specific rules."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, Field

from ..utils.temporal import (
    asks_single_total_across_years,
    explicit_year_list_is_temporal_dimension,
)
from .catalog import SemanticCatalog, load_semantic_catalog
from .plan_schema import (
    AnswerShape,
    SemanticDimension,
    SemanticFilter,
    SemanticMetric,
    SemanticPlan,
)

_ALLOWED_DIMENSION_NAMES = {
    "estado",
    "estado_hospital",
    "municipio",
    "municipio_hospital",
    "hospital",
    "especialidade",
    "cid_capitulo",
    "diagnostico",
    "procedimento",
    "contraceptivo",
    "sexo",
    "raca_cor",
    "instrucao",
    "idade",
    "faixa_etaria",
    "ano",
    "mes",
    "trimestre",
    "dia_semana",
    "quartil",
}


class PlanReconciliationResult(BaseModel):
    reconciled_plan: SemanticPlan
    conflicts: list[str] = Field(default_factory=list)
    accepted_llm_fields: list[str] = Field(default_factory=list)
    rejected_llm_fields: list[str] = Field(default_factory=list)
    accepted_llm_field_reasons: dict[str, str] = Field(default_factory=dict)
    rejected_llm_field_reasons: dict[str, str] = Field(default_factory=dict)


def reconcile_semantic_plans(
    heuristic_plan: SemanticPlan | dict,
    llm_plan: SemanticPlan | dict | None,
    *,
    catalog: SemanticCatalog | None = None,
    user_query: str | None = None,
    chart_plan: Any | None = None,
) -> PlanReconciliationResult:
    """Merge a candidate LLM plan into the deterministic semantic contract.

    The heuristic plan is the safety anchor. The LLM may add useful dimensions,
    filters, and ambiguities, but it cannot remove required constraints inferred
    from reusable semantic rules.
    """
    heuristic = _as_plan(heuristic_plan)
    if llm_plan is None:
        return PlanReconciliationResult(reconciled_plan=heuristic)

    candidate = _as_plan(llm_plan)
    catalog = catalog or load_semantic_catalog()
    conflicts: list[str] = []
    accepted: list[str] = []
    rejected: list[str] = []
    accepted_reasons: dict[str, str] = {}
    rejected_reasons: dict[str, str] = {}

    intent = heuristic.intent
    if heuristic.intent == "unknown" and candidate.intent != "unknown":
        intent = candidate.intent
        _record_accept(accepted, accepted_reasons, "intent", "heuristic intent was unknown")
    elif candidate.intent != heuristic.intent and candidate.intent != "unknown":
        conflicts.append(f"intent_mismatch: heuristic={heuristic.intent}; llm={candidate.intent}")
        _record_reject(rejected, rejected_reasons, "intent", "heuristic intent was already set")

    base_grain = heuristic.base_grain
    if (
        candidate.base_grain
        and heuristic.base_grain != "unknown"
        and candidate.base_grain != heuristic.base_grain
    ):
        conflicts.append(
            f"base_grain_mismatch: heuristic={heuristic.base_grain}; llm={candidate.base_grain}"
        )
        _record_reject(
            rejected,
            rejected_reasons,
            "base_grain",
            "candidate base grain conflicts with deterministic heuristic grain",
        )
    elif heuristic.base_grain == "unknown" and candidate.base_grain:
        base_grain = candidate.base_grain
        _record_accept(accepted, accepted_reasons, "base_grain", "heuristic base grain was unknown")

    metrics, metric_conflicts = _merge_metrics(heuristic.metrics, candidate.metrics, catalog)
    conflicts.extend(metric_conflicts)
    if candidate.metrics:
        _record_accept(
            accepted,
            accepted_reasons,
            "metrics",
            "candidate metrics were reconciled against the semantic catalog",
        )

    answer_shape = _merge_answer_shape(
        heuristic,
        candidate,
        conflicts,
        accepted,
        rejected,
        accepted_reasons,
        rejected_reasons,
        user_query=user_query,
        chart_plan=chart_plan,
    )

    dimensions = _merge_dimensions(
        heuristic.dimensions,
        candidate.dimensions,
        answer_shape,
    )
    if len(dimensions) > len(heuristic.dimensions):
        _record_accept(
            accepted,
            accepted_reasons,
            "dimensions",
            "candidate dimensions are allowed and match the reconciled answer shape",
        )

    filters = _merge_filters(heuristic.filters, candidate.filters)
    if len(filters) > len(heuristic.filters):
        _record_accept(
            accepted,
            accepted_reasons,
            "filters",
            "candidate added filters that do not override heuristic filters",
        )

    constraints = _stable_union(heuristic.constraints, candidate.constraints)
    null_policy = _stable_union(heuristic.null_policy, candidate.null_policy)
    ambiguities = _stable_union(heuristic.ambiguities, candidate.ambiguities)

    return PlanReconciliationResult(
        reconciled_plan=SemanticPlan(
            intent=intent,
            base_grain=base_grain,
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            answer_shape=answer_shape,
            constraints=constraints,
            null_policy=null_policy,
            ambiguities=ambiguities,
        ),
        conflicts=conflicts,
        accepted_llm_fields=_stable_union([], accepted),
        rejected_llm_fields=_stable_union([], rejected),
        accepted_llm_field_reasons=accepted_reasons,
        rejected_llm_field_reasons=rejected_reasons,
    )


def _as_plan(plan: SemanticPlan | dict) -> SemanticPlan:
    if isinstance(plan, SemanticPlan):
        return plan
    return SemanticPlan.model_validate(plan)


def _merge_metrics(
    heuristic_metrics: list[SemanticMetric],
    candidate_metrics: list[SemanticMetric],
    catalog: SemanticCatalog,
) -> tuple[list[SemanticMetric], list[str]]:
    conflicts: list[str] = []
    merged: dict[str, SemanticMetric] = {metric.name: metric for metric in heuristic_metrics}
    catalog_names = set(catalog.metrics)

    for metric in candidate_metrics:
        if metric.name in merged:
            continue
        if metric.name in catalog_names or metric.name in {
            "total",
            "proporcao",
            "media",
            "requested_metric",
            "delta_temporal",
        }:
            merged[metric.name] = metric
        else:
            conflicts.append(f"unknown_metric_ignored: {metric.name}")

    if heuristic_metrics and candidate_metrics:
        heuristic_names = {metric.name for metric in heuristic_metrics}
        candidate_names = {metric.name for metric in candidate_metrics}
        if heuristic_names != candidate_names and "requested_metric" not in heuristic_names:
            conflicts.append(
                f"metric_mismatch: heuristic={sorted(heuristic_names)}; llm={sorted(candidate_names)}"
            )

    return list(merged.values()), conflicts


def _merge_dimensions(
    heuristic_dimensions: list[SemanticDimension],
    candidate_dimensions: list[SemanticDimension],
    heuristic_shape: AnswerShape,
) -> list[SemanticDimension]:
    if heuristic_shape.row_grain == "single_scalar":
        return heuristic_dimensions
    merged: dict[str, SemanticDimension] = {
        _canonical_dimension_name(dimension.name): _canonicalize_dimension(dimension)
        for dimension in heuristic_dimensions
        if _is_allowed_dimension_name(dimension.name)
    }
    for dimension in candidate_dimensions:
        if not _is_allowed_dimension_name(dimension.name):
            continue
        canonical = _canonical_dimension_name(dimension.name)
        merged.setdefault(canonical, _canonicalize_dimension(dimension))
    return list(merged.values())


def _merge_filters(
    heuristic_filters: list[SemanticFilter],
    candidate_filters: list[SemanticFilter],
) -> list[SemanticFilter]:
    heuristic_fields = {semantic_filter.field for semantic_filter in heuristic_filters}
    if "idade" in heuristic_fields:
        candidate_filters = [
            semantic_filter for semantic_filter in candidate_filters if semantic_filter.field != "idade"
        ]

    merged: dict[tuple[str, str, tuple[str, ...]], SemanticFilter] = {}
    for semantic_filter in heuristic_filters + candidate_filters:
        key = (
            semantic_filter.field,
            semantic_filter.operator,
            tuple(str(value) for value in semantic_filter.values),
        )
        merged.setdefault(key, semantic_filter)
    return list(merged.values())


def _merge_answer_shape(
    heuristic_plan: SemanticPlan,
    candidate_plan: SemanticPlan,
    conflicts: list[str],
    accepted: list[str],
    rejected: list[str],
    accepted_reasons: dict[str, str],
    rejected_reasons: dict[str, str],
    *,
    user_query: str | None,
    chart_plan: Any | None,
) -> AnswerShape:
    heuristic = heuristic_plan.answer_shape
    candidate = candidate_plan.answer_shape
    row_grain = heuristic.row_grain
    row_grain_upgraded = False
    if heuristic.row_grain == "unknown" and candidate.row_grain != "unknown":
        row_grain = candidate.row_grain
        _record_accept(
            accepted,
            accepted_reasons,
            "answer_shape.row_grain",
            "heuristic row grain was unknown",
        )
    elif candidate.row_grain != heuristic.row_grain and candidate.row_grain != "unknown":
        upgrade_reason = _candidate_answer_shape_upgrade_reason(
            heuristic_plan,
            candidate_plan,
            user_query=user_query,
            chart_plan=chart_plan,
        )
        if upgrade_reason:
            row_grain = candidate.row_grain
            row_grain_upgraded = True
            _record_accept(
                accepted,
                accepted_reasons,
                "answer_shape.row_grain",
                upgrade_reason,
            )
        else:
            conflicts.append(
                f"row_grain_mismatch: heuristic={heuristic.row_grain}; llm={candidate.row_grain}"
            )
            _record_reject(
                rejected,
                rejected_reasons,
                "answer_shape.row_grain",
                _candidate_answer_shape_rejection_reason(
                    heuristic_plan,
                    candidate_plan,
                    user_query=user_query,
                    chart_plan=chart_plan,
                ),
            )
    elif candidate.row_grain != "unknown" and candidate.row_grain == heuristic.row_grain:
        _record_accept(
            accepted,
            accepted_reasons,
            "answer_shape.row_grain",
            "candidate row grain agrees with deterministic heuristic",
        )

    top_n_scope = heuristic.top_n_scope
    if candidate.top_n_scope != heuristic.top_n_scope and candidate.top_n_scope != "none":
        conflicts.append(
            f"top_n_scope_mismatch: heuristic={heuristic.top_n_scope}; llm={candidate.top_n_scope}"
        )
        _record_reject(
            rejected,
            rejected_reasons,
            "answer_shape.top_n_scope",
            "top-N scope remains anchored to deterministic heuristic detection",
        )
    elif heuristic.top_n_scope == "none" and candidate.top_n_scope != "none":
        top_n_scope = candidate.top_n_scope

    candidate_required_dimensions = _candidate_grouping_dimensions(candidate_plan)
    required_dimensions = _merge_required_dimensions(
        heuristic.required_dimensions,
        candidate_required_dimensions,
        row_grain=row_grain,
    )
    partition_dimensions = _merge_required_dimensions(
        heuristic.partition_dimensions,
        candidate.partition_dimensions,
        row_grain=row_grain,
    )
    ranked_dimensions = _merge_required_dimensions(
        heuristic.ranked_dimensions,
        candidate.ranked_dimensions,
        row_grain=row_grain,
    )
    return AnswerShape(
        row_grain=row_grain,
        top_n=heuristic.top_n or candidate.top_n,
        top_n_scope=top_n_scope,
        required_dimensions=required_dimensions,
        partition_dimensions=partition_dimensions,
        ranked_dimensions=ranked_dimensions,
        requires_group_by=_merge_requires_group_by(
            heuristic,
            candidate,
            row_grain=row_grain,
            required_dimensions=required_dimensions,
        ),
        include_unknown_bucket=heuristic.include_unknown_bucket or candidate.include_unknown_bucket,
        answer_kind=_merge_answer_kind(heuristic, candidate, row_grain_upgraded=row_grain_upgraded),
        expected_row_count=_merge_expected_row_count(
            heuristic,
            candidate,
            row_grain_upgraded=row_grain_upgraded,
        ),
        output_dimensions=required_dimensions,
        filter_dimensions=_merge_dimension_name_lists(
            heuristic.filter_dimensions,
            candidate.filter_dimensions,
        ),
        counted_entity=heuristic.counted_entity or candidate.counted_entity,
        forbidden_output_dimensions=_merge_dimension_name_lists(
            heuristic.forbidden_output_dimensions,
            candidate.forbidden_output_dimensions,
        ),
    )


def _merge_requires_group_by(
    heuristic: AnswerShape,
    candidate: AnswerShape,
    *,
    row_grain: str,
    required_dimensions: list[str],
) -> bool:
    if row_grain == "single_scalar":
        return False
    if heuristic.requires_group_by:
        return True
    if candidate.requires_group_by:
        return bool(required_dimensions)
    return False


def _candidate_answer_shape_upgrade_reason(
    heuristic_plan: SemanticPlan,
    candidate_plan: SemanticPlan,
    *,
    user_query: str | None,
    chart_plan: Any | None,
) -> str | None:
    heuristic = heuristic_plan.answer_shape
    candidate = candidate_plan.answer_shape
    if heuristic.row_grain != "single_scalar":
        return None
    if candidate.row_grain not in {"time_series", "one_row_per_group"}:
        return None
    if not _is_weak_scalar_heuristic(heuristic_plan, user_query):
        return None

    dimensions = _candidate_grouping_dimensions(candidate_plan)
    if not dimensions or any(not _is_allowed_dimension_name(dimension) for dimension in dimensions):
        return None

    evidence = _dimension_evidence(
        dimensions,
        heuristic_plan,
        candidate_plan,
        user_query=user_query,
        chart_plan=chart_plan,
    )
    if not evidence:
        return None

    return (
        f"weak scalar heuristic upgraded to {candidate.row_grain}; "
        + "; ".join(_stable_union([], evidence))
    )


def _candidate_answer_shape_rejection_reason(
    heuristic_plan: SemanticPlan,
    candidate_plan: SemanticPlan,
    *,
    user_query: str | None,
    chart_plan: Any | None,
) -> str:
    candidate = candidate_plan.answer_shape
    if candidate.row_grain not in {"time_series", "one_row_per_group"}:
        return f"candidate row grain {candidate.row_grain} is not a safe scalar upgrade"
    strong_reason = _strong_scalar_reason(heuristic_plan, user_query)
    if strong_reason:
        return strong_reason
    dimensions = _candidate_grouping_dimensions(candidate_plan)
    if not dimensions:
        return "candidate grouped shape did not provide required dimensions"
    disallowed = [
        dimension for dimension in dimensions if not _is_allowed_dimension_name(dimension)
    ]
    if disallowed:
        return f"candidate dimensions are not allowed: {', '.join(disallowed)}"
    return "candidate dimensions lack supporting filter, chart, or query evidence"


def _is_weak_scalar_heuristic(heuristic_plan: SemanticPlan, user_query: str | None) -> bool:
    return _strong_scalar_reason(heuristic_plan, user_query) is None


def _strong_scalar_reason(heuristic_plan: SemanticPlan, user_query: str | None) -> str | None:
    shape = heuristic_plan.answer_shape
    if shape.row_grain != "single_scalar":
        return "heuristic row grain is not a weak scalar candidate"
    if shape.required_dimensions:
        return "heuristic scalar shape already carries required dimensions"
    if shape.top_n or shape.top_n_scope != "none":
        return "heuristic top-N intent remains authoritative"
    if any(metric.expression_type == "rate" for metric in heuristic_plan.metrics):
        return "rate metrics keep the deterministic scalar shape authoritative"
    if _has_explicit_scalar_intent(user_query):
        return "query explicitly asks for a single aggregate value"
    return None


def _has_explicit_scalar_intent(user_query: str | None) -> bool:
    if not user_query:
        return False
    if asks_single_total_across_years(user_query):
        return True
    normalized = _normalize_text(user_query)
    scalar_cues = (
        "ao todo",
        "consolidado",
        "consolidada",
        "em todo o periodo",
        "no periodo inteiro",
        "no periodo todo",
        "soma total",
        "somando",
        "total acumulado",
        "total agregado",
        "total geral",
        "todos os anos juntos",
        "um unico numero",
        "valor unico",
    )
    return any(cue in normalized for cue in scalar_cues)


def _candidate_grouping_dimensions(candidate_plan: SemanticPlan) -> list[str]:
    return _merge_dimension_name_lists(
        candidate_plan.answer_shape.required_dimensions,
        [dimension.name for dimension in candidate_plan.dimensions],
    )


def _dimension_evidence(
    dimensions: list[str],
    heuristic_plan: SemanticPlan,
    candidate_plan: SemanticPlan,
    *,
    user_query: str | None,
    chart_plan: Any | None,
) -> list[str]:
    filter_dimensions = {
        _canonical_dimension_name(semantic_filter.field)
        for semantic_filter in heuristic_plan.filters + candidate_plan.filters
        if _is_allowed_dimension_name(semantic_filter.field)
    }
    chart_dimensions = _chart_plan_dimensions(chart_plan)

    evidence: list[str] = []
    for dimension in dimensions:
        if dimension in filter_dimensions:
            evidence.append(f"{dimension} is present in semantic filters")
            continue
        if dimension in chart_dimensions:
            evidence.append(f"{dimension} is required by chart plan")
            continue
        if _query_mentions_dimension(dimension, user_query):
            evidence.append(f"{dimension} is mentioned in user query")
            continue
        return []
    return evidence


def _chart_plan_dimensions(chart_plan: Any | None) -> set[str]:
    if not chart_plan:
        return set()
    if hasattr(chart_plan, "model_dump"):
        raw = chart_plan.model_dump(exclude_none=True)
    elif isinstance(chart_plan, dict):
        raw = chart_plan
    else:
        raw = {
            key: getattr(chart_plan, key, None)
            for key in ("x_dimension", "series_dimension", "grain", "required_columns")
        }

    dimensions: set[str] = set()
    for key in ("x_dimension", "series_dimension"):
        value = raw.get(key)
        if isinstance(value, str) and _is_allowed_dimension_name(value):
            dimensions.add(_canonical_dimension_name(value))
    required_columns = raw.get("required_columns") or []
    for column in required_columns:
        if isinstance(column, str) and _is_allowed_dimension_name(column):
            dimensions.add(_canonical_dimension_name(column))
    return dimensions


def _query_mentions_dimension(dimension: str, user_query: str | None) -> bool:
    if not user_query:
        return False
    normalized = _normalize_text(user_query)
    if dimension == "ano" and explicit_year_list_is_temporal_dimension(normalized):
        return True
    aliases = {
        "ano": ("ano", "anos", "anual", "evolucao", "evolucao temporal", "serie temporal"),
        "mes": ("mes", "meses", "mensal"),
        "estado": ("estado", "uf"),
        "municipio": ("municipio", "cidade"),
        "hospital": ("hospital", "hospitais"),
        "especialidade": ("especialidade", "especialidade medica"),
        "sexo": ("sexo", "genero", "homens", "mulheres", "masculino", "feminino"),
        "raca_cor": ("raca cor", "raca", "cor"),
        "faixa_etaria": ("faixa etaria", "idade"),
        "idade": ("idade",),
        "diagnostico": ("diagnostico", "cid"),
        "procedimento": ("procedimento",),
    }.get(dimension, (dimension.replace("_", " "),))
    return any(
        f"por {alias}" in normalized
        or f"por cada {alias}" in normalized
        or f"segundo {alias}" in normalized
        for alias in aliases
    )


def _merge_answer_kind(
    heuristic: AnswerShape,
    candidate: AnswerShape,
    *,
    row_grain_upgraded: bool,
) -> str:
    if row_grain_upgraded and candidate.answer_kind != "unknown":
        return candidate.answer_kind
    if heuristic.answer_kind != "unknown":
        return heuristic.answer_kind
    return candidate.answer_kind


def _merge_expected_row_count(
    heuristic: AnswerShape,
    candidate: AnswerShape,
    *,
    row_grain_upgraded: bool,
) -> str:
    if row_grain_upgraded and candidate.expected_row_count != "unknown":
        return candidate.expected_row_count
    if heuristic.expected_row_count != "unknown":
        return heuristic.expected_row_count
    return candidate.expected_row_count


def _merge_required_dimensions(
    heuristic_dimensions: list[str],
    candidate_dimensions: list[str],
    *,
    row_grain: str,
) -> list[str]:
    if row_grain == "single_scalar":
        return []
    merged: dict[str, str] = {}
    for dimension in heuristic_dimensions + candidate_dimensions:
        if not _is_allowed_dimension_name(dimension):
            continue
        canonical = _canonical_dimension_name(dimension)
        merged.setdefault(canonical, canonical)
    return list(merged.values())


def _canonical_dimension_name(name: str) -> str:
    aliases = {
        "estado_residencia": "estado",
        "ano_internacao": "ano",
        "cid": "diagnostico",
        "codigo_cid": "diagnostico",
        "diagnostico_principal": "diagnostico",
        "diagnostico_secundario": "diagnostico",
    }
    return aliases.get(name, name)


def _is_allowed_dimension_name(name: str) -> bool:
    return _canonical_dimension_name(name) in _ALLOWED_DIMENSION_NAMES


def _canonicalize_dimension(dimension: SemanticDimension) -> SemanticDimension:
    canonical = _canonical_dimension_name(dimension.name)
    if canonical == dimension.name:
        return dimension
    return dimension.model_copy(update={"name": canonical})


def _merge_dimension_name_lists(left: list[str], right: list[str]) -> list[str]:
    merged: list[str] = []
    for dimension in left + right:
        if not _is_allowed_dimension_name(dimension):
            continue
        canonical = _canonical_dimension_name(dimension)
        if canonical not in merged:
            merged.append(canonical)
    return merged


def _record_accept(
    accepted: list[str],
    reasons: dict[str, str],
    field: str,
    reason: str,
) -> None:
    if field not in accepted:
        accepted.append(field)
    reasons.setdefault(field, reason)


def _record_reject(
    rejected: list[str],
    reasons: dict[str, str],
    field: str,
    reason: str,
) -> None:
    if field not in rejected:
        rejected.append(field)
    reasons.setdefault(field, reason)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _stable_union(left: list[str], right: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in left + right:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
