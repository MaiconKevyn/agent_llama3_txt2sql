"""Serialization helpers for frontend chart rendering."""

from __future__ import annotations

from .echarts import chart_spec_to_echarts_option
from .schema import ChartSpec, VisualizationIntent


def build_chart_response(
    *,
    intent: VisualizationIntent,
    spec: ChartSpec | None,
) -> dict:
    """Build the stable API/UI chart payload.

    The payload carries both the typed ``spec`` (used by tests/eval and as a
    contract) and ``echarts`` (consumed by the frontend renderer).
    """

    return {
        "requested": intent.requested,
        "source": intent.source,
        "uses_last_result": intent.uses_last_result,
        "chart_hint": intent.chart_hint,
        "spec": spec.model_dump(mode="json") if spec else None,
        "echarts": chart_spec_to_echarts_option(spec),
        "reason": intent.reason,
    }
