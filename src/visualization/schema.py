"""Typed contracts for explicit chart generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ChartType = Literal["bar", "line", "scatter", "area", "pie", "donut", "table", "kpi"]
ChartHint = Literal["bar", "line", "scatter", "area", "pie", "donut", "table", "kpi", "auto"]
ColumnType = Literal["string", "number", "temporal", "boolean", "unknown"]
IntentSource = Literal["none", "explicit_current_query", "explicit_followup"]
WarningSeverity = Literal["info", "warning", "error"]
ExpectedResultShape = Literal[
    "single_metric",
    "category_metric",
    "time_metric",
    "time_series_metric",
    "wide_metric_comparison",
    "unknown",
]


class VisualizationIntent(BaseModel):
    """User intent to generate a chart.

    This is intentionally opt-in: ``requested`` must only be true when the user
    explicitly asks for a chart or plot.
    """

    requested: bool = False
    source: IntentSource = "none"
    uses_last_result: bool = False
    chart_hint: ChartHint = "auto"
    reason: str = ""

    @model_validator(mode="after")
    def _normalize_unrequested(self) -> VisualizationIntent:
        if not self.requested:
            self.source = "none"
            self.uses_last_result = False
            self.chart_hint = "auto"
        return self


class ChartWarning(BaseModel):
    """Validation or planning warning returned with a chart spec."""

    code: str
    message: str
    severity: WarningSeverity = "warning"


class ChartFilter(BaseModel):
    """Structured filter needed to produce a chart-compatible result."""

    field: str
    operator: str = "="
    values: list[Any] = Field(default_factory=list)
    semantic: str | None = None


class ChartTimeWindow(BaseModel):
    """Structured temporal window for chart SQL generation."""

    type: Literal["none", "last_n_available_years", "year_range"] = "none"
    n: int | None = None
    start_year: int | None = None
    end_year: int | None = None
    date_column: str = "DT_INTER"


class ChartPlan(BaseModel):
    """Pre-SQL visual contract used to generate chart-compatible SQL."""

    requested: bool = False
    chart_type: ChartHint = "auto"
    metric: str | None = None
    metric_expression: str | None = None
    x_dimension: str | None = None
    series_dimension: str | None = None
    y_column: str | None = None
    grain: str = "unknown"
    expected_result_shape: ExpectedResultShape = "unknown"
    filters: list[ChartFilter] = Field(default_factory=list)
    time_window: ChartTimeWindow = Field(default_factory=ChartTimeWindow)
    required_columns: list[str] = Field(default_factory=list)
    sql_shape_guidance: str = ""
    reason: str = ""

    def to_prompt_block(self) -> str:
        """Render compact SQL-generation guidance."""

        if not self.requested:
            return "[CHART PLAN]\nrequested: false"
        return "\n".join(
            [
                "[CHART PLAN - SQL RESULT MUST SUPPORT THIS VISUALIZATION]",
                f"chart_type: {self.chart_type}",
                f"metric: {self.metric}",
                f"x_dimension: {self.x_dimension}",
                f"series_dimension: {self.series_dimension}",
                f"y_column: {self.y_column}",
                f"grain: {self.grain}",
                f"expected_result_shape: {self.expected_result_shape}",
                f"time_window: {self.time_window.model_dump(exclude_none=True)}",
                f"filters: {[item.model_dump(exclude_none=True) for item in self.filters]}",
                f"required_columns: {self.required_columns}",
                f"sql_shape_guidance: {self.sql_shape_guidance}",
            ]
        )


class ChartPlanningInput(BaseModel):
    """Input contract consumed by the deterministic chart planner."""

    user_query: str
    last_sql_query: str | None = None
    semantic_plan: dict[str, Any] | None = None
    columns: list[str] = Field(default_factory=list)
    column_types: dict[str, ColumnType] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    chart_hint: ChartHint = "auto"
    chart_plan: ChartPlan | None = None


class ChartSpec(BaseModel):
    """Serializable chart contract returned to API/CLI/UI."""

    chartable: bool
    chart_type: ChartType = "table"
    title: str | None = None
    x: str | None = None
    y: str | None = None
    series: str | None = None
    encoding: dict[str, str] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    warnings: list[ChartWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape(self) -> ChartSpec:
        if not self.chartable:
            return self
        if self.chart_type in {"bar", "line", "area", "scatter", "pie", "donut"}:
            if not self.x or not self.y:
                raise ValueError(f"{self.chart_type} charts require x and y")
        return self
