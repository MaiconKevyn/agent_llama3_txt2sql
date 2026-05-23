"""Structured audits for intent, semantic, SQL and result contracts."""

from __future__ import annotations

from typing import Any

from src.semantic.plan_schema import SemanticPlan
from src.visualization.schema import ChartPlan


def audit_pre_sql_plan(
    *,
    user_query: str,
    semantic_plan: dict[str, Any] | SemanticPlan | None,
    chart_plan: dict[str, Any] | ChartPlan | None,
) -> dict[str, Any]:
    """Validate that high-level user concepts were resolved before SQL generation."""

    plan = _coerce_semantic_plan(semantic_plan)
    chart = _coerce_chart_plan(chart_plan)
    filters = {item.field: item for item in plan.filters}
    normalized = (user_query or "").lower()
    resolved: list[str] = []
    errors: list[dict[str, str]] = []

    if _mentions_child(normalized):
        if "idade" in filters:
            resolved.append("child_age_policy")
        else:
            errors.append(
                {
                    "layer": "semantic_resolution",
                    "code": "missing_child_age_policy",
                    "message": "Child/pediatric query must resolve an IDADE filter.",
                }
            )

    if _mentions_respiratory(normalized):
        respiratory_filter = filters.get("diagnostico_principal_prefix")
        if respiratory_filter and any(
            str(value).upper() == "J%" for value in respiratory_filter.values
        ):
            resolved.append("respiratory_cid")
        else:
            errors.append(
                {
                    "layer": "semantic_resolution",
                    "code": "missing_respiratory_cid_resolution",
                    "message": "Respiratory query must resolve to a diagnosis prefix such as J%.",
                }
            )

    if any(item.field == "desfecho" for item in plan.filters):
        resolved.append("death_outcome")
    if any(item.field == "recent_years_available" for item in plan.filters):
        resolved.append("last_n_available_years")

    if chart.requested:
        metric_names = {metric.name for metric in plan.metrics}
        dimensions = set(plan.answer_shape.required_dimensions)
        chart_dimensions = {value for value in [chart.x_dimension, chart.series_dimension] if value}
        missing_columns = [
            column
            for column in chart.required_columns
            if column
            and column not in dimensions
            and column not in chart_dimensions
            and column not in metric_names
            and column != chart.y_column
        ]
        if missing_columns:
            errors.append(
                {
                    "layer": "chart_contract",
                    "code": "chart_required_columns_not_planned",
                    "message": ", ".join(missing_columns),
                }
            )

    return {
        "passed": not errors,
        "errors": errors,
        "resolved_concepts": list(dict.fromkeys(resolved)),
    }


def audit_result_contract(
    *,
    chart_plan: dict[str, Any] | ChartPlan | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate result rows against chart shape requirements."""

    chart = _coerce_chart_plan(chart_plan)
    errors: list[dict[str, str]] = []
    if chart.requested:
        if not rows:
            errors.append(
                {
                    "layer": "result_contract",
                    "code": "empty_chart_result",
                    "message": "Chart request produced no rows.",
                }
            )
        else:
            first_row = rows[0]
            if _result_tuple_matches_required_columns(first_row, chart.required_columns):
                return {
                    "passed": True,
                    "errors": [],
                    "warnings": [
                        {
                            "layer": "result_contract",
                            "code": "unlabeled_tuple_result",
                            "message": "Result parser returned positional tuples; column count matches chart contract.",
                        }
                    ],
                }
            row_columns = set(first_row) if isinstance(first_row, dict) else set()
            missing = [column for column in chart.required_columns if column not in row_columns]
            if missing:
                errors.append(
                    {
                        "layer": "result_contract",
                        "code": "missing_chart_result_columns",
                        "message": ", ".join(missing),
                    }
                )
    return {"passed": not errors, "errors": errors, "warnings": []}


def _coerce_semantic_plan(plan: dict[str, Any] | SemanticPlan | None) -> SemanticPlan:
    if isinstance(plan, SemanticPlan):
        return plan
    return SemanticPlan.model_validate(plan or {})


def _coerce_chart_plan(plan: dict[str, Any] | ChartPlan | None) -> ChartPlan:
    if isinstance(plan, ChartPlan):
        return plan
    return ChartPlan.model_validate(plan or {})


def _mentions_child(normalized_query: str) -> bool:
    return any(
        token in normalized_query
        for token in ["crianca", "criança", "criancas", "crianças", "pediatric"]
    )


def _mentions_respiratory(normalized_query: str) -> bool:
    return "respirat" in normalized_query or "cid j" in normalized_query


def _result_tuple_matches_required_columns(row: Any, required_columns: list[str]) -> bool:
    if not isinstance(row, dict) or set(row) != {"result"}:
        return False
    value = row.get("result")
    return isinstance(value, (tuple, list)) and len(value) >= len(required_columns)
