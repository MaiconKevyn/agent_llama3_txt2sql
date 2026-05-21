"""Explicit chart-generation helpers for the Text-to-SQL agent."""

from .chart_plan import build_chart_plan, validate_sql_against_chart_plan
from .data import build_chart_planning_input, infer_column_types, normalize_result_rows
from .echarts import chart_spec_to_echarts_option
from .intent import detect_visualization_intent
from .planner import plan_chart
from .schema import (
    ChartPlan,
    ChartPlanningInput,
    ChartPresentation,
    ChartSpec,
    ChartWarning,
    VisualizationIntent,
)
from .validator import validate_chart_spec

__all__ = [
    "ChartPlan",
    "ChartPlanningInput",
    "ChartPresentation",
    "ChartSpec",
    "ChartWarning",
    "VisualizationIntent",
    "build_chart_plan",
    "build_chart_planning_input",
    "chart_spec_to_echarts_option",
    "detect_visualization_intent",
    "infer_column_types",
    "normalize_result_rows",
    "plan_chart",
    "validate_chart_spec",
    "validate_sql_against_chart_plan",
]
