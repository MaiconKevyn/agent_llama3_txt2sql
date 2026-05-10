"""ChartSpec validation against real result columns and types."""

from __future__ import annotations

from typing import Any

from .schema import ChartSpec, ChartWarning

MAX_BAR_CATEGORIES = 30
MAX_PIE_CATEGORIES = 8


def validate_chart_spec(
    spec: ChartSpec | dict[str, Any],
    columns: list[str],
    column_types: dict[str, str],
) -> ChartSpec:
    """Validate a chart spec and attach warnings for risky visual shapes."""

    chart_spec = spec if isinstance(spec, ChartSpec) else ChartSpec.model_validate(spec)
    if not chart_spec.chartable:
        return chart_spec

    available_columns = set(columns)
    referenced = [
        column
        for column in [chart_spec.x, chart_spec.y, chart_spec.series]
        if column is not None
    ]
    missing = [column for column in referenced if column not in available_columns]
    if missing:
        raise ValueError(f"ChartSpec references missing columns: {missing}")

    if chart_spec.y and column_types.get(chart_spec.y) != "number":
        raise ValueError(f"ChartSpec y axis must be numeric: {chart_spec.y}")

    if chart_spec.chart_type in {"line", "area"} and chart_spec.x:
        if column_types.get(chart_spec.x) not in {"temporal", "number"}:
            chart_spec.warnings.append(
                ChartWarning(
                    code="line_x_not_temporal",
                    message="Grafico temporal usa eixo X sem tipo temporal confirmado.",
                )
            )

    if chart_spec.chart_type in {"pie", "donut"}:
        categories = _distinct_values(chart_spec.data, chart_spec.x)
        if len(categories) > MAX_PIE_CATEGORIES:
            raise ValueError(
                f"{chart_spec.chart_type} supports at most {MAX_PIE_CATEGORIES} categories"
            )

    if chart_spec.chart_type == "bar":
        categories = _distinct_values(chart_spec.data, chart_spec.x)
        if len(categories) > MAX_BAR_CATEGORIES:
            chart_spec.warnings.append(
                ChartWarning(
                    code="high_cardinality",
                    message=(
                        f"Grafico de barras possui {len(categories)} categorias; "
                        "considere filtrar ou usar tabela."
                    ),
                )
            )

    return chart_spec


def _distinct_values(rows: list[dict[str, Any]], column: str | None) -> set[Any]:
    if not column:
        return set()
    return {row.get(column) for row in rows if row.get(column) is not None}
