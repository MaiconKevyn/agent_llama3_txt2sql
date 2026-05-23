"""Deterministic chart planning from validated SQL results."""

from __future__ import annotations

from typing import Any

from .presentation import enrich_chart_presentation
from .schema import ChartPlan, ChartPlanningInput, ChartSpec, ChartWarning
from .text_normalization import normalize_chart_label
from .validator import validate_chart_spec

MAX_BAR_CATEGORIES = 30
MAX_PIE_CATEGORIES = 8
MAX_READABLE_BAR_CATEGORIES = 15


def plan_chart(planning_input: ChartPlanningInput | dict[str, Any]) -> ChartSpec:
    """Build a ChartSpec without accessing the database or changing SQL."""

    chart_input = (
        planning_input
        if isinstance(planning_input, ChartPlanningInput)
        else ChartPlanningInput.model_validate(planning_input)
    )

    if chart_input.row_count == 0 or not chart_input.rows:
        return ChartSpec(
            chartable=False,
            chart_type="table",
            reason="Resultado vazio; nao ha dados para visualizacao.",
            warnings=[
                ChartWarning(
                    code="empty_result",
                    message="Resultado vazio; grafico nao foi gerado.",
                    severity="info",
                )
            ],
        )

    columns = chart_input.columns or _columns_from_rows(chart_input.rows)
    column_types = {
        column: chart_input.column_types.get(column) or _infer_column_type(chart_input.rows, column)
        for column in columns
    }
    numeric_columns = [column for column in columns if column_types[column] == "number"]
    temporal_columns = [column for column in columns if column_types[column] == "temporal"]
    categorical_columns = [
        column for column in columns if column_types[column] in {"string", "boolean", "unknown"}
    ]

    planned_spec = _plan_from_chart_plan(chart_input.chart_plan, chart_input)
    if planned_spec is not None:
        return _finalize_spec(planned_spec, columns, column_types)

    if len(columns) == 1 and numeric_columns:
        spec = ChartSpec(
            chartable=True,
            chart_type="kpi",
            title=_build_title(chart_input, numeric_columns[0]),
            y=numeric_columns[0],
            encoding={"y_type": "quantitative"},
            data=chart_input.rows,
            reason="Resultado escalar numerico; usar KPI.",
        )
        return _finalize_spec(spec, columns, column_types)

    if len(chart_input.rows) == 1 and len(numeric_columns) >= 2:
        comparison_columns = _drop_total_metrics_when_breakdown_exists(numeric_columns)
        metric_rows = [
            {"metrica": _humanize(column), "valor": chart_input.rows[0].get(column)}
            for column in comparison_columns
        ]
        spec = ChartSpec(
            chartable=True,
            chart_type="bar",
            title="Comparacao de metricas",
            x="metrica",
            y="valor",
            encoding={"x_type": "nominal", "y_type": "quantitative"},
            data=metric_rows,
            reason="Resultado escalar com multiplas metricas numericas; usar barras comparativas.",
        )
        return _finalize_spec(
            spec,
            ["metrica", "valor"],
            {"metrica": "string", "valor": "number"},
        )

    if temporal_columns and len(numeric_columns) >= 2:
        temporal_column = temporal_columns[0]
        comparison_columns = _drop_domain_code_numeric_columns(
            _drop_total_metrics_when_breakdown_exists(numeric_columns)
        )
        if len(comparison_columns) < 2:
            comparison_columns = _drop_total_metrics_when_breakdown_exists(numeric_columns)
        series_rows = [
            {
                temporal_column: row.get(temporal_column),
                "serie": _humanize(column),
                "valor": row.get(column),
            }
            for row in chart_input.rows
            for column in comparison_columns
        ]
        spec = ChartSpec(
            chartable=True,
            chart_type="line" if chart_input.chart_hint != "bar" else "bar",
            title=_build_title(chart_input, "valor", temporal_column),
            x=temporal_column,
            y="valor",
            series="serie",
            encoding={
                "x_type": "temporal",
                "y_type": "quantitative",
                "series_type": "nominal",
            },
            data=series_rows,
            reason="Resultado temporal com multiplas metricas numericas; usar serie comparativa.",
        )
        return _finalize_spec(
            spec,
            [temporal_column, "serie", "valor"],
            {temporal_column: "temporal", "serie": "string", "valor": "number"},
        )

    if chart_input.chart_hint in {"pie", "donut"} and categorical_columns and numeric_columns:
        chart_type = "donut" if chart_input.chart_hint == "donut" else "pie"
        metric_column = _select_metric_column(chart_input, numeric_columns)
        prepared_data, warnings = _prepare_chart_data_for_spec(
            chart_input.rows,
            chart_type=chart_type,
            x=categorical_columns[0],
            y=metric_column,
            series=None,
        )
        spec = ChartSpec(
            chartable=True,
            chart_type=chart_type,
            title=_build_title(chart_input, metric_column, categorical_columns[0]),
            x=categorical_columns[0],
            y=metric_column,
            encoding={"x_type": "nominal", "y_type": "quantitative"},
            data=prepared_data,
            reason="Pedido explicito de grafico de proporcao.",
            warnings=warnings,
        )
        return _finalize_spec(spec, columns, column_types)

    if len(numeric_columns) >= 2 and chart_input.chart_hint == "scatter":
        spec = ChartSpec(
            chartable=True,
            chart_type="scatter",
            title=_build_title(chart_input, numeric_columns[1], numeric_columns[0]),
            x=numeric_columns[0],
            y=numeric_columns[1],
            encoding={"x_type": "quantitative", "y_type": "quantitative"},
            data=chart_input.rows,
            reason="Pedido explicito de dispersao com duas metricas numericas.",
        )
        return _finalize_spec(spec, columns, column_types)

    if temporal_columns and numeric_columns:
        series = categorical_columns[0] if categorical_columns else None
        metric_column = _select_metric_column(chart_input, numeric_columns)
        spec = ChartSpec(
            chartable=True,
            chart_type="line" if chart_input.chart_hint != "area" else "area",
            title=_build_title(chart_input, metric_column, temporal_columns[0]),
            x=temporal_columns[0],
            y=metric_column,
            series=series,
            encoding={"x_type": "temporal", "y_type": "quantitative"},
            data=chart_input.rows,
            reason="Resultado temporal com metrica numerica.",
        )
        return _finalize_spec(spec, columns, column_types)

    if categorical_columns and numeric_columns:
        metric_column = _select_metric_column(chart_input, numeric_columns)
        prepared_data, warnings = _prepare_chart_data_for_spec(
            chart_input.rows,
            chart_type="bar",
            x=categorical_columns[0],
            y=metric_column,
            series=None,
        )
        spec = ChartSpec(
            chartable=True,
            chart_type="bar",
            title=_build_title(chart_input, metric_column, categorical_columns[0]),
            x=categorical_columns[0],
            y=metric_column,
            encoding={"x_type": "nominal", "y_type": "quantitative"},
            data=prepared_data,
            reason="Resultado categorico com metrica numerica.",
            warnings=warnings,
        )
        return _finalize_spec(spec, columns, column_types)

    return ChartSpec(
        chartable=False,
        chart_type="table",
        data=chart_input.rows,
        reason="Resultado nao possui shape visual confiavel; usar tabela.",
        warnings=[
            ChartWarning(
                code="unsupported_shape",
                message="Nao foi possivel inferir eixos de grafico a partir do resultado.",
            )
        ],
    )


def _plan_from_chart_plan(
    chart_plan: ChartPlan | None,
    chart_input: ChartPlanningInput,
) -> ChartSpec | None:
    if not chart_plan or not chart_plan.requested or not chart_input.rows:
        return None

    columns = chart_input.columns or _columns_from_rows(chart_input.rows)
    column_lookup = {column.lower(): column for column in columns}
    x = _resolve_column_name(chart_plan.x_dimension, column_lookup)
    y = _resolve_column_name(chart_plan.y_column, column_lookup)
    series = _resolve_column_name(chart_plan.series_dimension, column_lookup)
    column_types = {
        column: chart_input.column_types.get(column) or _infer_column_type(chart_input.rows, column)
        for column in columns
    }
    if chart_plan.chart_type == "scatter":
        if not x or not y:
            return None
        if column_types.get(x) != "number" or column_types.get(y) != "number":
            return None
        return validate_chart_spec(
            ChartSpec(
                chartable=True,
                chart_type="scatter",
                title=_build_chart_plan_title(chart_plan),
                x=x,
                y=y,
                encoding={"x_type": "quantitative", "y_type": "quantitative"},
                data=chart_input.rows,
                reason="Grafico de dispersao planejado a partir de ChartPlan pre-SQL estruturado.",
            ),
            columns,
            column_types,
        )
    if not x or not y:
        return None
    if chart_plan.series_dimension and not series:
        return None

    chart_type = "line" if chart_plan.chart_type == "auto" else chart_plan.chart_type
    if chart_plan.expected_result_shape in {"time_series_metric", "time_metric"}:
        chart_type = "line" if chart_type not in {"area", "bar"} else chart_type

    prepared_data, warnings = _prepare_chart_data_for_spec(
        chart_input.rows,
        chart_type=chart_type,
        x=x,
        y=y,
        series=series,
    )
    return ChartSpec(
        chartable=True,
        chart_type=chart_type,
        title=_build_chart_plan_title(chart_plan),
        x=x,
        y=y,
        series=series,
        encoding={
            "x_type": "temporal" if x.lower() in {"ano", "mes"} else "nominal",
            "y_type": "quantitative",
            **({"series_type": "nominal"} if series else {}),
        },
        data=prepared_data,
        reason="Grafico planejado a partir de ChartPlan pre-SQL estruturado.",
        warnings=warnings,
    )


def _prepare_chart_plan_data(
    rows: list[dict[str, Any]],
    *,
    chart_type: str,
    x: str,
    y: str,
    series: str | None,
) -> list[dict[str, Any]]:
    rows, _ = _prepare_chart_data_for_spec(
        rows,
        chart_type=chart_type,
        x=x,
        y=y,
        series=series,
    )
    return rows


def _prepare_chart_data_for_spec(
    rows: list[dict[str, Any]],
    *,
    chart_type: str,
    x: str,
    y: str,
    series: str | None,
) -> tuple[list[dict[str, Any]], list[ChartWarning]]:
    normalized_rows = [
        {
            **row,
            x: normalize_chart_label(row.get(x)),
            **(
                {series: normalize_chart_label(_format_domain_label(series, row.get(series)))}
                if series
                else {}
            ),
        }
        for row in rows
    ]
    warnings: list[ChartWarning] = []
    if chart_type in {"bar", "pie", "donut"} and _is_clinical_missing_sensitive_dimension(x):
        filtered_rows = [row for row in normalized_rows if not _is_unfilled_category(row.get(x))]
        removed_count = len(normalized_rows) - len(filtered_rows)
        if removed_count:
            normalized_rows = filtered_rows
        warnings.append(
            ChartWarning(
                code="excluded_unfilled_category",
                message=(
                    "Este grafico desconsidera registros sem causa, diagnostico ou "
                    "motivo preenchido para evitar que categorias incompletas dominem "
                    "a visualizacao."
                ),
                severity="info",
            )
        )
    if chart_type in {"pie", "donut"}:
        normalized_rows = _limit_pie_categories(normalized_rows, x=x, y=y)
    if chart_type == "bar" and not series:
        normalized_rows, bar_warning = _limit_bar_categories(normalized_rows, x=x, y=y)
        if bar_warning:
            warnings.append(bar_warning)
    return normalized_rows, warnings


def _limit_pie_categories(
    rows: list[dict[str, Any]],
    *,
    x: str,
    y: str,
) -> list[dict[str, Any]]:
    if len({row.get(x) for row in rows}) <= MAX_PIE_CATEGORIES:
        return rows
    sorted_rows = sorted(
        rows,
        key=lambda row: row.get(y) if isinstance(row.get(y), (int, float)) else 0,
        reverse=True,
    )
    kept = sorted_rows[: MAX_PIE_CATEGORIES - 1]
    other_value = sum(
        row.get(y)
        for row in sorted_rows[MAX_PIE_CATEGORIES - 1 :]
        if isinstance(row.get(y), (int, float))
    )
    if other_value:
        kept.append({x: "Outros", y: other_value})
    return kept


def _limit_bar_categories(
    rows: list[dict[str, Any]],
    *,
    x: str,
    y: str,
) -> tuple[list[dict[str, Any]], ChartWarning | None]:
    categories = {row.get(x) for row in rows}
    if len(categories) <= MAX_READABLE_BAR_CATEGORIES:
        return rows, None
    sorted_rows = sorted(
        rows,
        key=lambda row: row.get(y) if isinstance(row.get(y), int | float) else 0,
        reverse=True,
    )
    limited = sorted_rows[:MAX_READABLE_BAR_CATEGORIES]
    return limited, ChartWarning(
        code="bar_limited_for_readability",
        message=(
            f"Exibindo os {MAX_READABLE_BAR_CATEGORIES} maiores valores "
            f"de {len(categories)} categorias."
        ),
        severity="info",
    )


def _resolve_column_name(name: str | None, column_lookup: dict[str, str]) -> str | None:
    if not name:
        return None
    return column_lookup.get(name.lower())


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    return list(rows[0].keys())


def _infer_column_type(rows: list[dict[str, Any]], column: str) -> str:
    values = [row.get(column) for row in rows if row.get(column) is not None]
    if not values:
        return "unknown"
    if all(isinstance(value, bool) for value in values):
        return "boolean"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return "number"
    if _looks_temporal(column, values):
        return "temporal"
    return "string"


def _looks_temporal(column: str, values: list[Any]) -> bool:
    lowered = column.lower()
    if any(token in lowered for token in ["data", "date", "ano", "mes", "trimestre", "dt_"]):
        return True
    return all(isinstance(value, str) and _is_date_like(value) for value in values[:20])


def _is_date_like(value: str) -> bool:
    return bool(len(value) >= 4 and (value[:4].isdigit() or "/" in value or "-" in value))


def _build_title(
    chart_input: ChartPlanningInput,
    metric: str,
    dimension: str | None = None,
) -> str:
    if dimension:
        return f"{_humanize(metric)} por {_humanize(dimension)}"
    return _humanize(metric).capitalize()


def _humanize(column_name: str) -> str:
    return column_name.replace("_", " ").strip()


def _select_metric_column(
    chart_input: ChartPlanningInput,
    numeric_columns: list[str],
) -> str:
    """Choose the metric that best matches the user's analytical intent."""

    if not numeric_columns:
        return ""
    if len(numeric_columns) == 1:
        return numeric_columns[0]

    normalized_query = _normalize_label(chart_input.user_query)
    normalized_columns = {column: _normalize_label(column) for column in numeric_columns}

    semantic_match = _metric_from_semantic_plan(chart_input.semantic_plan, normalized_columns)
    if semantic_match:
        return semantic_match

    rate_terms = {
        "taxa",
        "mortalidade",
        "letalidade",
        "percentual",
        "porcentagem",
        "proporcao",
        "proporção",
        "indice",
        "índice",
        "rate",
        "ratio",
    }
    if any(term in normalized_query for term in rate_terms):
        for token in [
            "taxa",
            "mortalidade",
            "letalidade",
            "percent",
            "proporcao",
            "indice",
            "rate",
            "ratio",
        ]:
            for column, normalized_column in normalized_columns.items():
                if token in normalized_column:
                    return column

    death_terms = {"morte", "mortes", "obito", "obitos", "óbito", "óbitos"}
    if any(_normalize_label(term) in normalized_query for term in death_terms):
        for token in ["morte", "obito"]:
            for column, normalized_column in normalized_columns.items():
                if token in normalized_column:
                    return column

    non_denominator_columns = [
        column
        for column, normalized_column in normalized_columns.items()
        if not _is_denominator_metric(normalized_column)
    ]
    return non_denominator_columns[0] if non_denominator_columns else numeric_columns[0]


def _metric_from_semantic_plan(
    semantic_plan: dict[str, Any] | None,
    normalized_columns: dict[str, str],
) -> str | None:
    if not isinstance(semantic_plan, dict):
        return None
    metrics = semantic_plan.get("metrics")
    if not isinstance(metrics, list):
        return None

    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        metric_name = _normalize_label(metric.get("name"))
        expression_type = _normalize_label(metric.get("expression_type"))
        if metric_name:
            for column, normalized_column in normalized_columns.items():
                if metric_name == normalized_column or metric_name in normalized_column:
                    return column
        if expression_type == "rate":
            for column, normalized_column in normalized_columns.items():
                if any(
                    token in normalized_column for token in ["taxa", "percent", "proporcao", "rate"]
                ):
                    return column
    return None


def _is_denominator_metric(normalized_column: str) -> bool:
    denominator_tokens = {
        "internacao",
        "internacoes",
        "populacao",
        "nascido",
        "nascidos",
        "denominador",
        "total registros",
    }
    outcome_tokens = {
        "morte",
        "mortes",
        "obito",
        "obitos",
        "taxa",
        "percent",
        "proporcao",
        "mortalidade",
    }
    return any(token in normalized_column for token in denominator_tokens) and not any(
        token in normalized_column for token in outcome_tokens
    )


def _drop_total_metrics_when_breakdown_exists(numeric_columns: list[str]) -> list[str]:
    breakdown_columns = [
        column
        for column in numeric_columns
        if not column.lower().startswith("total")
        and not column.lower().endswith("_total")
        and column.lower() != "total"
    ]
    return breakdown_columns if len(breakdown_columns) >= 2 else numeric_columns


def _drop_domain_code_numeric_columns(numeric_columns: list[str]) -> list[str]:
    domain_code_columns = {
        "sexo",
        "raca_cor",
        "etnia",
        "idade",
        "ano",
        "mes",
        "trimestre",
        "codigo",
        "co_municipio_6d",
        "co_municipio_7d",
        "cnes",
    }
    return [
        column
        for column in numeric_columns
        if column.lower().strip('"') not in domain_code_columns
        and not column.lower().startswith("cod_")
    ]


def _format_domain_label(dimension: str, value: Any) -> Any:
    if dimension.lower() == "sexo":
        text = str(value).strip().lower()
        labels = {
            "1": "Masculino",
            "3": "Feminino",
            "masculino": "Masculino",
            "feminino": "Feminino",
            "homens": "Masculino",
            "mulheres": "Feminino",
        }
        return labels.get(text, value)
    return value


def _is_clinical_missing_sensitive_dimension(dimension: str | None) -> bool:
    normalized = _normalize_label(dimension)
    return any(token in normalized for token in ["causa", "diagnostico", "doenca", "cid", "motivo"])


def _is_unfilled_category(value: Any) -> bool:
    normalized = _normalize_label(value)
    return normalized in {
        "",
        "nao preenchido",
        "nao informado",
        "sem informacao",
        "ignorado",
        "null",
        "none",
    }


def _normalize_label(value: Any) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", "" if value is None else str(value))
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(ascii_text.lower().strip().split())


def _build_chart_plan_title(chart_plan: ChartPlan) -> str:
    metric = _humanize(chart_plan.metric or chart_plan.y_column or "valor")
    if chart_plan.x_dimension:
        return f"{metric} por {_humanize(chart_plan.x_dimension)}"
    return metric.capitalize()


def _finalize_spec(
    spec: ChartSpec,
    columns: list[str],
    column_types: dict[str, str],
) -> ChartSpec:
    return enrich_chart_presentation(validate_chart_spec(spec, columns, column_types))
