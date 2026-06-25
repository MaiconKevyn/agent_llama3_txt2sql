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
    "#9333ea",
    "#0284c7",
    "#b45309",
    "#047857",
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
    x_type = spec.encoding.get("x_type")

    # Color each bar differently when there's no series dimension; avoids uniform blue.
    # Legend is rendered as HTML below the chart (not inside ECharts canvas) for better UX.
    per_item_color = chart_type == "bar" and not spec.series and len(x_values) > 1
    multi_series_legend = bool(spec.series and len(series_values) > 1)
    horizontal_bar = chart_type == "bar" and not spec.series and x_type != "temporal"

    option.update(
        {
            "grid": {"left": 56, "right": 18, "top": 54, "bottom": 48, "containLabel": True},
            "legend": {
                "show": multi_series_legend,
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
    if horizontal_bar:
        option["grid"] = {"left": 14, "right": 28, "top": 24, "bottom": 22, "containLabel": True}
        option["xAxis"] = {
            "type": "value",
            "name": spec.y or "",
            "nameGap": 30,
            "axisLabel": {"color": "#667085"},
            "splitLine": {"lineStyle": {"color": "rgba(102,112,133,0.18)"}},
        }
        option["yAxis"] = {
            "type": "category",
            "name": spec.x or "",
            "nameGap": 46,
            "inverse": True,
            "data": x_values,
            "axisLabel": {
                "color": "#667085",
                "width": 142,
                "overflow": "truncate",
            },
            "axisLine": {"lineStyle": {"color": "#98a2b3"}},
        }

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
            "emphasis": {"focus": "series"},
        }
        if per_item_color:
            series["data"] = [
                {
                    "value": value_by_x.get(str(x_value), 0),
                    "itemStyle": {
                        "color": ECHARTS_COLORS[i % len(ECHARTS_COLORS)],
                        "borderRadius": [5, 5, 0, 0],
                    },
                }
                for i, x_value in enumerate(x_values)
            ]
            option["_legend"] = [
                {"name": str(x_value), "color": ECHARTS_COLORS[i % len(ECHARTS_COLORS)]}
                for i, x_value in enumerate(x_values)
            ]
        else:
            series["data"] = [value_by_x.get(str(x_value), 0) for x_value in x_values]
        if chart_type == "bar":
            series["barMaxWidth"] = 26 if horizontal_bar else 34
            if not per_item_color:
                series["itemStyle"] = {"borderRadius": [0, 5, 5, 0] if horizontal_bar else [5, 5, 0, 0]}
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
    total = sum(row.get(spec.y) for row in rows if isinstance(row.get(spec.y), int | float))
    legend_data = [
        {
            "name": str(row.get(spec.x)),
            "color": ECHARTS_COLORS[i % len(ECHARTS_COLORS)],
            "value": row.get(spec.y),
            "percent": round((row.get(spec.y) or 0) * 100 / total, 2) if total else 0,
        }
        for i, row in enumerate(rows)
    ]
    option.update(
        {
            "tooltip": {"trigger": "item", "confine": True},
            "legend": {"show": False},
            "_legend": legend_data,
            "series": [
                {
                    "type": "pie",
                    "name": spec.y or "valor",
                    "radius": ["44%", "70%"] if donut else ["0%", "70%"],
                    "center": ["50%", "48%"],
                    "avoidLabelOverlap": True,
                    "label": {"show": False},
                    "labelLine": {"show": False},
                    "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                    "data": [
                        {
                            "name": str(row.get(spec.x)),
                            "value": row.get(spec.y),
                            "itemStyle": {"color": ECHARTS_COLORS[i % len(ECHARTS_COLORS)]},
                        }
                        for i, row in enumerate(rows)
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
