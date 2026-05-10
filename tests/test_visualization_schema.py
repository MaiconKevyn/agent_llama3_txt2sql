import pytest

from src.visualization.schema import ChartSpec, VisualizationIntent


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
