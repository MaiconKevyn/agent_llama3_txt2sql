import json

from src.visualization.echarts import ECHARTS_COLORS, chart_spec_to_echarts_option
from src.visualization.schema import ChartSpec


def _bar_spec() -> ChartSpec:
    return ChartSpec(
        chartable=True,
        chart_type="bar",
        title="Top municipios",
        x="municipio",
        y="total",
        encoding={"x_type": "nominal", "y_type": "quantitative"},
        data=[{"municipio": "Porto Alegre", "total": 10}, {"municipio": "Canoas", "total": 8}],
    )


def test_returns_none_when_not_chartable():
    spec = ChartSpec(chartable=False, chart_type="table", reason="empty")

    assert chart_spec_to_echarts_option(spec) is None


def test_table_returns_none_so_frontend_renders_html_table():
    spec = ChartSpec(chartable=True, chart_type="table", data=[{"a": 1}])

    assert chart_spec_to_echarts_option(spec) is None


def test_bar_chart_emits_echarts_option():
    option = chart_spec_to_echarts_option(_bar_spec())

    assert option["series"][0]["type"] == "bar"
    assert option["xAxis"]["type"] == "value"
    assert option["yAxis"]["type"] == "category"
    assert option["yAxis"]["data"] == ["Porto Alegre", "Canoas"]
    assert option["yAxis"]["inverse"] is True
    assert option["series"][0]["data"][0]["value"] == 10
    assert option["series"][0]["data"][1]["value"] == 8
    assert option["title"]["text"] == "Top municipios"


def test_simple_bar_uses_per_item_color_with_html_legend():
    option = chart_spec_to_echarts_option(_bar_spec())

    # Each bar gets its own color via inline itemStyle; no colorBy to avoid native legend.
    assert option["series"][0]["data"][0]["itemStyle"]["color"] == ECHARTS_COLORS[0]
    assert option["series"][0]["data"][1]["itemStyle"]["color"] == ECHARTS_COLORS[1]
    assert option["legend"]["show"] is False
    # _legend drives the HTML legend rendered by app.js.
    assert option["_legend"][0] == {"name": "Porto Alegre", "color": ECHARTS_COLORS[0]}
    assert option["_legend"][1] == {"name": "Canoas", "color": ECHARTS_COLORS[1]}


def test_temporal_bar_keeps_vertical_axis():
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        x="ano",
        y="total_mortes",
        encoding={"x_type": "temporal", "y_type": "quantitative"},
        data=[{"ano": 2021, "total_mortes": 10}, {"ano": 2022, "total_mortes": 8}],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["xAxis"]["type"] == "category"
    assert option["xAxis"]["data"] == [2021, 2022]
    assert option["yAxis"]["type"] == "value"


def test_grouped_bar_chart_creates_one_series_per_group():
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        x="ano",
        y="total_mortes",
        series="sexo",
        encoding={"x_type": "nominal", "y_type": "quantitative", "series_type": "nominal"},
        data=[
            {"ano": 2022, "sexo": "Masculino", "total_mortes": 10},
            {"ano": 2022, "sexo": "Feminino", "total_mortes": 8},
        ],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["legend"]["show"] is True
    assert [series["name"] for series in option["series"]] == ["Masculino", "Feminino"]
    assert option["series"][0]["data"] == [10]
    assert option["series"][1]["data"] == [8]


def test_line_chart_uses_line_series():
    spec = ChartSpec(
        chartable=True,
        chart_type="line",
        x="ano",
        y="valor",
        encoding={"x_type": "temporal", "y_type": "quantitative"},
        data=[{"ano": 2021, "valor": 1}, {"ano": 2022, "valor": 2}],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["series"][0]["type"] == "line"
    assert option["series"][0]["smooth"] is True
    assert option["xAxis"]["data"] == [2021, 2022]


def test_area_chart_uses_line_series_with_area_style():
    spec = ChartSpec(
        chartable=True,
        chart_type="area",
        x="ano",
        y="valor",
        encoding={"x_type": "temporal"},
        data=[{"ano": 2022, "valor": 5}],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["series"][0]["type"] == "line"
    assert option["series"][0]["areaStyle"]["opacity"] > 0


def test_pie_chart_uses_pie_series():
    spec = ChartSpec(
        chartable=True,
        chart_type="pie",
        x="sexo",
        y="total_mortes",
        encoding={"x_type": "nominal", "y_type": "quantitative"},
        data=[
            {"sexo": "Masculino", "total_mortes": 404208},
            {"sexo": "Feminino", "total_mortes": 358813},
        ],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["series"][0]["type"] == "pie"
    assert option["series"][0]["radius"] == ["0%", "70%"]
    assert option["series"][0]["center"] == ["50%", "48%"]
    assert option["series"][0]["label"]["show"] is False
    assert option["legend"]["show"] is False
    assert option["series"][0]["data"] == [
        {"name": "Masculino", "value": 404208, "itemStyle": {"color": ECHARTS_COLORS[0]}},
        {"name": "Feminino", "value": 358813, "itemStyle": {"color": ECHARTS_COLORS[1]}},
    ]
    assert option["_legend"] == [
        {"name": "Masculino", "color": ECHARTS_COLORS[0], "value": 404208, "percent": 52.97},
        {"name": "Feminino", "color": ECHARTS_COLORS[1], "value": 358813, "percent": 47.03},
    ]


def test_donut_chart_sets_inner_radius():
    spec = ChartSpec(
        chartable=True,
        chart_type="donut",
        x="categoria",
        y="valor",
        encoding={"x_type": "nominal"},
        data=[{"categoria": "A", "valor": 1}],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["series"][0]["type"] == "pie"
    assert option["series"][0]["radius"][0] != "0%"


def test_kpi_renders_graphic_text():
    spec = ChartSpec(
        chartable=True,
        chart_type="kpi",
        y="total_internacoes",
        encoding={"y_type": "quantitative"},
        data=[{"total_internacoes": 18443084}],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["graphic"][0]["type"] == "text"
    assert option["graphic"][0]["style"]["text"] == "18.443.084"


def test_scatter_returns_scatter_series():
    spec = ChartSpec(
        chartable=True,
        chart_type="scatter",
        x="x_metric",
        y="y_metric",
        encoding={"x_type": "quantitative", "y_type": "quantitative"},
        data=[{"x_metric": 1, "y_metric": 2}],
    )

    option = chart_spec_to_echarts_option(spec)

    assert option["series"][0]["type"] == "scatter"
    assert option["series"][0]["data"] == [[1, 2]]


def test_option_is_json_serializable():
    option = chart_spec_to_echarts_option(_bar_spec())

    json.dumps(option)


def test_echarts_uses_presentation_labels_on_axes_and_tooltip_metadata():
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        x="municipio",
        y="total_internacoes",
        encoding={"x_type": "nominal", "y_type": "quantitative"},
        data=[{"municipio": "Porto Alegre", "total_internacoes": 1569537}],
    )
    from src.visualization.presentation import enrich_chart_presentation

    option = chart_spec_to_echarts_option(enrich_chart_presentation(spec))

    assert option["xAxis"]["name"] == "Total de internacoes"
    assert option["yAxis"]["name"] == "Municipio"
    assert option["_valueFormat"] == "integer"
    assert option["_summary"] == "Porto Alegre lidera com 1.569.537."


def test_echarts_percent_metric_exposes_percent_format():
    spec = ChartSpec(
        chartable=True,
        chart_type="line",
        x="ano",
        y="taxa_mortalidade",
        encoding={"x_type": "temporal", "y_type": "quantitative"},
        data=[{"ano": 2022, "taxa_mortalidade": 4.31}],
    )
    from src.visualization.presentation import enrich_chart_presentation

    option = chart_spec_to_echarts_option(enrich_chart_presentation(spec))

    assert option["yAxis"]["name"] == "Taxa de mortalidade (%)"
    assert option["_valueFormat"] == "percent"
