"""Reconcile heuristic and LLM semantic plans without benchmark-specific rules."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .catalog import SemanticCatalog, load_semantic_catalog
from .plan_schema import (
    AnswerShape,
    SemanticDimension,
    SemanticFilter,
    SemanticMetric,
    SemanticPlan,
)


class PlanReconciliationResult(BaseModel):
    reconciled_plan: SemanticPlan
    conflicts: list[str] = Field(default_factory=list)
    accepted_llm_fields: list[str] = Field(default_factory=list)
    rejected_llm_fields: list[str] = Field(default_factory=list)


def reconcile_semantic_plans(
    heuristic_plan: SemanticPlan | dict,
    llm_plan: SemanticPlan | dict | None,
    *,
    catalog: SemanticCatalog | None = None,
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

    intent = heuristic.intent
    if heuristic.intent == "unknown" and candidate.intent != "unknown":
        intent = candidate.intent
        accepted.append("intent")
    elif candidate.intent != heuristic.intent and candidate.intent != "unknown":
        conflicts.append(f"intent_mismatch: heuristic={heuristic.intent}; llm={candidate.intent}")
        rejected.append("intent")

    base_grain = heuristic.base_grain
    if (
        candidate.base_grain
        and heuristic.base_grain != "unknown"
        and candidate.base_grain != heuristic.base_grain
    ):
        conflicts.append(
            f"base_grain_mismatch: heuristic={heuristic.base_grain}; llm={candidate.base_grain}"
        )
        rejected.append("base_grain")
    elif heuristic.base_grain == "unknown" and candidate.base_grain:
        base_grain = candidate.base_grain
        accepted.append("base_grain")

    metrics, metric_conflicts = _merge_metrics(heuristic.metrics, candidate.metrics, catalog)
    conflicts.extend(metric_conflicts)
    if candidate.metrics:
        accepted.append("metrics")

    dimensions = _merge_dimensions(heuristic.dimensions, candidate.dimensions)
    if len(dimensions) > len(heuristic.dimensions):
        accepted.append("dimensions")

    filters = _merge_filters(heuristic.filters, candidate.filters)
    if len(filters) > len(heuristic.filters):
        accepted.append("filters")

    answer_shape = _merge_answer_shape(
        heuristic.answer_shape,
        candidate.answer_shape,
        conflicts,
        rejected,
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
) -> list[SemanticDimension]:
    merged: dict[str, SemanticDimension] = {
        dimension.name: dimension for dimension in heuristic_dimensions
    }
    for dimension in candidate_dimensions:
        merged.setdefault(dimension.name, dimension)
    return list(merged.values())


def _merge_filters(
    heuristic_filters: list[SemanticFilter],
    candidate_filters: list[SemanticFilter],
) -> list[SemanticFilter]:
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
    heuristic: AnswerShape,
    candidate: AnswerShape,
    conflicts: list[str],
    rejected: list[str],
) -> AnswerShape:
    row_grain = heuristic.row_grain
    if candidate.row_grain != heuristic.row_grain and candidate.row_grain != "unknown":
        conflicts.append(
            f"row_grain_mismatch: heuristic={heuristic.row_grain}; llm={candidate.row_grain}"
        )
        rejected.append("answer_shape.row_grain")
    elif heuristic.row_grain == "unknown" and candidate.row_grain != "unknown":
        row_grain = candidate.row_grain

    top_n_scope = heuristic.top_n_scope
    if candidate.top_n_scope != heuristic.top_n_scope and candidate.top_n_scope != "none":
        conflicts.append(
            f"top_n_scope_mismatch: heuristic={heuristic.top_n_scope}; llm={candidate.top_n_scope}"
        )
        rejected.append("answer_shape.top_n_scope")
    elif heuristic.top_n_scope == "none" and candidate.top_n_scope != "none":
        top_n_scope = candidate.top_n_scope

    return AnswerShape(
        row_grain=row_grain,
        top_n=heuristic.top_n or candidate.top_n,
        top_n_scope=top_n_scope,
        required_dimensions=_stable_union(
            heuristic.required_dimensions,
            candidate.required_dimensions,
        ),
        requires_group_by=heuristic.requires_group_by or candidate.requires_group_by,
        include_unknown_bucket=heuristic.include_unknown_bucket or candidate.include_unknown_bucket,
    )


def _stable_union(left: list[str], right: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in left + right:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
