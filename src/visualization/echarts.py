"""Adapter that converts a ChartSpec into an Apache ECharts option."""

from __future__ import annotations

from typing import Any

from .schema import ChartSpec

ECHARTS_COLORS = [
    "#2563eb",
    "#0f766e",
    "#c2410c",
    "#7c3aed",
    "#be123c",
    "#a16207",
    "#0891b2",
    "#4d7c0f",
]


def chart_spec_to_echarts_option(spec: ChartSpec | None) -> dict[str, Any] | None:
    """Convert a validated ChartSpec into an ECharts option.

    Returns ``None`` for non-chartable specs and table specs. The frontend keeps
    table rendering in plain HTML for accessibility.
    """

    if spec is None or not spec.chartable or spec.chart_type == "table":
        return None

    if spec.chart_type == "bar":
        return _cartesian(spec, chart_type="bar")
    if spec.chart_type == "line":
        return _cartesian(spec, chart_type="line")
    if spec.chart_type == "area":
        return _cartesian(spec, chart_type="line", area=True)
    if spec.chart_type == "scatter":
        return _scatter(spec)
    if spec.chart_type in {"pie", "donut"}:
        return _pie(spec, donut=spec.chart_type == "donut")
    if spec.chart_type == "kpi":
        return _kpi(spec)
    return None


def _base(spec: ChartSpec) -> dict[str, Any]:
    return {
        "color": ECHARTS_COLORS,
        "backgroundColor": "transparent",
        "animationDuration": 450,
        "textStyle": {"fontFamily": "Inter, system-ui, sans-serif"},
        "title": {
            "show": False,
            "text": spec.title or "",
            "left": 0,
            "top": 0,
            "textStyle": {"fontSize": 14, "fontWeight": 700, "color": "#101828"},
        },
        "tooltip": {"trigger": "axis", "confine": True},
    }


def _cartesian(spec: ChartSpec, *, chart_type: str, area: bool = False) -> dict[str, Any]:
    option = _base(spec)
    rows = list(spec.data or [])
    x_values = _unique(row.get(spec.x) for row in rows)
    series_values = _unique(row.get(spec.series) for row in rows) if spec.series else [spec.y]

    option.update(
        {
            "grid": {"left": 56, "right": 18, "top": 54, "bottom": 48, "containLabel": True},
            "legend": {
                "show": bool(spec.series and len(series_values) > 1),
                "top": 26,
                "right": 0,
                "type": "scroll",
            },
            "xAxis": {
                "type": "category",
                "name": spec.x or "",
                "nameLocation": "middle",
                "nameGap": 34,
                "data": x_values,
                "axisLabel": {"color": "#667085"},
                "axisLine": {"lineStyle": {"color": "#98a2b3"}},
            },
            "yAxis": {
                "type": "value",
                "name": spec.y or "",
                "nameGap": 42,
                "axisLabel": {"color": "#667085"},
                "splitLine": {"lineStyle": {"color": "rgba(102,112,133,0.18)"}},
            },
            "series": [],
        }
    )

    for series_value in series_values:
        if spec.series:
            series_rows = [row for row in rows if row.get(spec.series) == series_value]
            name = str(series_value)
        else:
            series_rows = rows
            name = spec.y or "valor"
        value_by_x = {str(row.get(spec.x)): row.get(spec.y) for row in series_rows}
        series: dict[str, Any] = {
            "type": chart_type,
            "name": name,
            "data": [value_by_x.get(str(x_value), 0) for x_value in x_values],
            "emphasis": {"focus": "series"},
        }
        if chart_type == "bar":
            series["barMaxWidth"] = 34
            series["itemStyle"] = {"borderRadius": [5, 5, 0, 0]}
        if chart_type == "line":
            series["smooth"] = True
            series["symbolSize"] = 7
        if area:
            series["areaStyle"] = {"opacity": 0.16}
        option["series"].append(series)
    return option


def _scatter(spec: ChartSpec) -> dict[str, Any]:
    option = _base(spec)
    rows = list(spec.data or [])
    option.update(
        {
            "grid": {"left": 56, "right": 18, "top": 54, "bottom": 48, "containLabel": True},
            "tooltip": {"trigger": "item", "confine": True},
            "xAxis": {"type": "value", "name": spec.x or "", "splitLine": {"show": False}},
            "yAxis": {
                "type": "value",
                "name": spec.y or "",
                "splitLine": {"lineStyle": {"color": "rgba(102,112,133,0.18)"}},
            },
            "series": [
                {
                    "type": "scatter",
                    "name": spec.y or "valor",
                    "symbolSize": 9,
                    "data": [[row.get(spec.x), row.get(spec.y)] for row in rows],
                }
            ],
        }
    )
    return option


def _pie(spec: ChartSpec, *, donut: bool) -> dict[str, Any]:
    option = _base(spec)
    rows = list(spec.data or [])
    option.update(
        {
            "tooltip": {"trigger": "item", "confine": True},
            "legend": {"type": "scroll", "orient": "vertical", "right": 0, "top": "middle"},
            "series": [
                {
                    "type": "pie",
                    "name": spec.y or "valor",
                    "radius": ["44%", "70%"] if donut else ["0%", "70%"],
                    "center": ["40%", "56%"],
                    "avoidLabelOverlap": True,
                    "label": {"formatter": "{b}\n{d}%", "fontSize": 11},
                    "labelLine": {"smooth": True},
                    "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                    "data": [
                        {"name": str(row.get(spec.x)), "value": row.get(spec.y)}
                        for row in rows
                    ],
                }
            ],
        }
    )
    return option


def _kpi(spec: ChartSpec) -> dict[str, Any]:
    option = _base(spec)
    value = None
    if spec.data and spec.y:
        value = spec.data[0].get(spec.y)
    option.update(
        {
            "tooltip": {"show": False},
            "xAxis": {"show": False},
            "yAxis": {"show": False},
            "series": [],
            "graphic": [
                {
                    "type": "text",
                    "left": "center",
                    "top": "middle",
                    "style": {
                        "text": _format_number(value),
                        "fontSize": 42,
                        "fontWeight": 700,
                        "fill": "#0f766e",
                    },
                }
            ],
        }
    )
    return option


def _unique(values: list[Any] | Any) -> list[Any]:
    seen: set[str] = set()
    unique_values: list[Any] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        unique_values.append(value)
    return unique_values


def _format_number(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value:,.0f}".replace(",", ".")
    return "" if value is None else str(value)
