"""Deterministic readability pass for chart specifications."""

from __future__ import annotations

from typing import Any

from .schema import ChartPresentation, ChartSpec, ValueFormat

LABELS = {
    "ano": "Ano",
    "mes": "Mes",
    "municipio": "Municipio",
    "estado": "Estado",
    "sexo": "Sexo",
    "raca_cor": "Raca/cor",
    "especialidade": "Especialidade",
    "causa_morte": "Causa de morte",
    "diagnostico": "Diagnostico",
    "total": "Total",
    "valor": "Valor",
    "total_internacoes": "Total de internacoes",
    "total_mortes": "Total de mortes",
    "taxa_mortalidade": "Taxa de mortalidade (%)",
    "receita_total": "Valor total",
    "valor_total": "Valor total",
    "custo_medio": "Custo medio",
    "idade_media": "Idade media",
    "permanencia_media": "Permanencia media",
}


def enrich_chart_presentation(spec: ChartSpec) -> ChartSpec:
    """Attach user-facing labels, value formatting and concise summary."""

    if not spec.chartable:
        return spec

    current = spec.presentation
    value_format = (
        current.value_format
        if "value_format" in current.model_fields_set
        else _infer_value_format(spec.y)
    )
    x_label = current.x_label or _label(spec.x)
    y_label = current.y_label or _label(spec.y)
    series_label = current.series_label or _label(spec.series)
    footnote = current.footnote
    limit_warning = next(
        (warning for warning in spec.warnings if warning.code == "bar_limited_for_readability"),
        None,
    )
    if limit_warning and not footnote:
        footnote = limit_warning.message

    spec.presentation = ChartPresentation(
        title=current.title or _build_title(spec, x_label=x_label, y_label=y_label),
        subtitle=current.subtitle or _build_subtitle(spec),
        x_label=x_label,
        y_label=y_label,
        series_label=series_label,
        value_format=value_format,
        sort_order=current.sort_order,
        footnote=footnote,
        summary=current.summary or _build_summary(spec, value_format),
    )
    return spec


def format_chart_value(value: Any, value_format: ValueFormat) -> str:
    """Format a value for pt-BR chart display."""

    if value is None:
        return "-"
    if not isinstance(value, int | float):
        return str(value)
    if value_format == "currency_brl":
        return f"R$ {_format_decimal(value, digits=2)}"
    if value_format == "percent":
        return f"{_format_decimal(value, digits=2)}%"
    if value_format == "decimal":
        return _format_decimal(value, digits=2)
    return f"{value:,.0f}".replace(",", ".")


def _infer_value_format(metric: str | None) -> ValueFormat:
    normalized = (metric or "").lower()
    if any(token in normalized for token in ["taxa", "percent", "proporcao", "ratio"]):
        return "percent"
    if any(
        token in normalized for token in ["valor", "receita", "custo", "val_", "valtot", "val_tot"]
    ):
        return "currency_brl"
    if any(token in normalized for token in ["media", "idade", "permanencia"]):
        return "decimal"
    return "integer"


def _label(column: str | None) -> str | None:
    if not column:
        return None
    normalized = column.strip().strip('"')
    return LABELS.get(normalized.lower(), normalized.replace("_", " ").capitalize())


def _build_title(spec: ChartSpec, *, x_label: str | None, y_label: str | None) -> str | None:
    if spec.chart_type == "kpi":
        return y_label
    if x_label and y_label:
        return f"{y_label} por {x_label.lower()}"
    return spec.title


def _build_subtitle(spec: ChartSpec) -> str | None:
    if spec.chart_type == "kpi":
        return "Indicador unico"
    if spec.chart_type in {"line", "area"} and spec.encoding.get("x_type") == "temporal":
        return "Serie temporal"
    if spec.chart_type in {"pie", "donut"}:
        return "Distribuicao proporcional"
    if spec.chart_type == "scatter":
        return "Comparacao entre metricas"
    if spec.chart_type == "bar":
        return "Ranking por valor"
    return None


def _build_summary(spec: ChartSpec, value_format: ValueFormat) -> str | None:
    if not spec.data or not spec.y:
        return None
    if spec.chart_type == "kpi":
        return f"{_label(spec.y)}: {format_chart_value(spec.data[0].get(spec.y), value_format)}."
    if not spec.x:
        return None
    numeric_rows = [row for row in spec.data if isinstance(row.get(spec.y), int | float)]
    if not numeric_rows:
        return None
    leader = max(numeric_rows, key=lambda row: row.get(spec.y) or 0)
    return (
        f"{leader.get(spec.x)} lidera com {format_chart_value(leader.get(spec.y), value_format)}."
    )


def _format_decimal(value: int | float, *, digits: int) -> str:
    text = f"{value:,.{digits}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")
