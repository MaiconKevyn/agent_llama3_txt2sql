import pytest

from src.visualization.schema import ChartSpec
from src.visualization.validator import validate_chart_spec


def test_validator_rejects_missing_columns():
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        x="municipio",
        y="total",
        data=[{"municipio": "A", "total": 1}],
    )

    with pytest.raises(ValueError):
        validate_chart_spec(spec, ["municipio"], {"municipio": "string"})


def test_validator_rejects_non_numeric_y_axis():
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        x="municipio",
        y="total",
        data=[{"municipio": "A", "total": "um"}],
    )

    with pytest.raises(ValueError):
        validate_chart_spec(
            spec,
            ["municipio", "total"],
            {"municipio": "string", "total": "string"},
        )


def test_validator_warns_for_high_cardinality_bar():
    rows = [{"municipio": f"M{i}", "total": i} for i in range(35)]
    spec = ChartSpec(
        chartable=True,
        chart_type="bar",
        x="municipio",
        y="total",
        data=rows,
    )

    validated = validate_chart_spec(
        spec,
        ["municipio", "total"],
        {"municipio": "string", "total": "number"},
    )

    assert any(warning.code == "high_cardinality" for warning in validated.warnings)


def test_validator_blocks_pie_with_too_many_categories():
    rows = [{"municipio": f"M{i}", "total": i} for i in range(10)]
    spec = ChartSpec(
        chartable=True,
        chart_type="pie",
        x="municipio",
        y="total",
        data=rows,
    )

    with pytest.raises(ValueError):
        validate_chart_spec(
            spec,
            ["municipio", "total"],
            {"municipio": "string", "total": "number"},
        )
