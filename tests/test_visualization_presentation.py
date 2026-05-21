from src.visualization.presentation import enrich_chart_presentation, format_chart_value
from src.visualization.schema import ChartSpec


def test_enriches_bar_with_human_labels_summary_and_integer_format():
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        title="total_internacoes por municipio",
        x="municipio",
        y="total_internacoes",
        data=[
            {"municipio": "Porto Alegre", "total_internacoes": 1569537},
            {"municipio": "Canoas", "total_internacoes": 422780},
        ],
        encoding={"x_type": "nominal", "y_type": "quantitative"},
    )

    enriched = enrich_chart_presentation(spec)

    assert enriched.presentation.title == "Total de internacoes por municipio"
    assert enriched.presentation.x_label == "Municipio"
    assert enriched.presentation.y_label == "Total de internacoes"
    assert enriched.presentation.value_format == "integer"
    assert enriched.presentation.summary == "Porto Alegre lidera com 1.569.537."


def test_detects_percent_format_for_rate_metric():
    spec = ChartSpec(
        chartable=True,
        chart_type="line",
        x="ano",
        y="taxa_mortalidade",
        data=[{"ano": 2022, "taxa_mortalidade": 4.31}],
        encoding={"x_type": "temporal", "y_type": "quantitative"},
    )

    enriched = enrich_chart_presentation(spec)

    assert enriched.presentation.value_format == "percent"
    assert enriched.presentation.y_label == "Taxa de mortalidade (%)"


def test_detects_currency_format_for_value_metric():
    spec = ChartSpec(
        chartable=True,
        chart_type="kpi",
        y="receita_total",
        data=[{"receita_total": 1234567.89}],
    )

    enriched = enrich_chart_presentation(spec)

    assert enriched.presentation.value_format == "currency_brl"
    assert enriched.presentation.summary == "Valor total: R$ 1.234.567,89."


def test_format_chart_value_uses_pt_br_styles():
    assert format_chart_value(1569537, "integer") == "1.569.537"
    assert format_chart_value(4.31, "percent") == "4,31%"
    assert format_chart_value(1234567.89, "currency_brl") == "R$ 1.234.567,89"
    assert format_chart_value(12.345, "decimal") == "12,35"
