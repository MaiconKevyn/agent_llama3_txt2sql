import pytest

from src.visualization.schema import ChartPresentation, ChartSpec, VisualizationIntent


def test_visualization_intent_normalizes_unrequested_payload():
    intent = VisualizationIntent(
        requested=False,
        source="explicit_current_query",
        uses_last_result=True,
        chart_hint="bar",
    )

    assert intent.source == "none"
    assert intent.uses_last_result is False
    assert intent.chart_hint == "auto"


def test_chart_spec_requires_axes_for_chartable_bar():
    with pytest.raises(ValueError):
        ChartSpec(chartable=True, chart_type="bar", x="municipio")


def test_chart_spec_allows_chartable_false_without_axes():
    spec = ChartSpec(chartable=False, chart_type="table", reason="unsupported")

    assert spec.chartable is False
    assert spec.x is None
    assert spec.y is None


def test_chart_spec_includes_default_presentation_contract():
    spec = ChartSpec(chartable=False, chart_type="table", reason="unsupported")

    assert isinstance(spec.presentation, ChartPresentation)
    assert spec.presentation.value_format == "integer"
    assert spec.presentation.sort_order == "as_returned"
    assert spec.presentation.summary is None


def test_chart_presentation_serializes_display_metadata():
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        x="municipio",
        y="total_internacoes",
        data=[{"municipio": "Porto Alegre", "total_internacoes": 10}],
        presentation=ChartPresentation(
            title="Internacoes por municipio",
            subtitle="Top municipios por volume",
            x_label="Municipio",
            y_label="Total de internacoes",
            value_format="integer",
            sort_order="desc",
            footnote="Limitado aos maiores valores.",
            summary="Porto Alegre lidera com 10 internacoes.",
        ),
    )

    payload = spec.model_dump(mode="json")

    assert payload["presentation"]["title"] == "Internacoes por municipio"
    assert payload["presentation"]["y_label"] == "Total de internacoes"
    assert payload["presentation"]["value_format"] == "integer"
    assert payload["presentation"]["summary"] == "Porto Alegre lidera com 10 internacoes."
