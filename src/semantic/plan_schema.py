"""Typed semantic plan models used between NL understanding and SQL generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Intent = Literal[
    "count",
    "ranking",
    "distribution",
    "rate",
    "trend",
    "comparison",
    "lookup",
    "unknown",
]

TopNScope = Literal["none", "global", "per_group"]


class SemanticDimension(BaseModel):
    """A grouping/filtering/output dimension inferred from the question."""

    name: str
    source: str | None = None
    role: Literal["group", "filter", "output", "join"] = "group"


class SemanticMetric(BaseModel):
    """A canonical metric requested or implied by the question."""

    name: str
    expression_type: Literal["count", "sum", "avg", "rate", "delta", "ratio", "unknown"] = "unknown"
    numerator_condition: str | None = None
    denominator_scope: str | None = None
    required_filters: list[str] = Field(default_factory=list)


class SemanticFilter(BaseModel):
    """A semantic filter, kept abstract enough to avoid benchmark-specific SQL."""

    field: str
    values: list[str] = Field(default_factory=list)
    operator: str = "="


class AnswerShape(BaseModel):
    """Expected result shape constraints derived from user intent."""

    row_grain: Literal[
        "single_scalar",
        "one_row_per_group",
        "top_n_global",
        "top_n_per_group",
        "time_series",
        "unknown",
    ] = "unknown"
    top_n: int | None = None
    top_n_scope: TopNScope = "none"
    required_dimensions: list[str] = Field(default_factory=list)
    requires_group_by: bool = False
    include_unknown_bucket: bool = False


class SemanticPlan(BaseModel):
    """Structured semantic contract that generated SQL should satisfy."""

    intent: Intent = "unknown"
    base_grain: str = "unknown"
    metrics: list[SemanticMetric] = Field(default_factory=list)
    dimensions: list[SemanticDimension] = Field(default_factory=list)
    filters: list[SemanticFilter] = Field(default_factory=list)
    answer_shape: AnswerShape = Field(default_factory=AnswerShape)
    constraints: list[str] = Field(default_factory=list)
    null_policy: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Render a concise prompt block for SQL generation."""
        data: dict[str, Any] = self.model_dump(exclude_none=True)
        lines = [
            "[SEMANTIC PLAN - SQL MUST SATISFY]",
            f"intent: {data.get('intent')}",
            f"base_grain: {data.get('base_grain')}",
            f"metrics: {data.get('metrics', [])}",
            f"dimensions: {data.get('dimensions', [])}",
            f"filters: {data.get('filters', [])}",
            f"answer_shape: {data.get('answer_shape', {})}",
            f"constraints: {data.get('constraints', [])}",
            f"null_policy: {data.get('null_policy', [])}",
        ]
        if self.ambiguities:
            lines.append(f"ambiguities: {self.ambiguities}")
        return "\n".join(lines)
