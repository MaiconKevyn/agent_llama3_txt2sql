"""Stable semantic error taxonomy for evaluation and telemetry."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class SemanticErrorCategory(StrEnum):
    TOP_N_SCOPE = "top_n_scope"
    RATE_DENOMINATOR = "rate_denominator"
    ABSENCE_CONDITION = "absence_condition"
    UNKNOWN_BUCKET = "unknown_bucket"
    GROUPING_DIMENSION = "grouping_dimension"
    TEMPORAL_GRAIN = "temporal_grain"
    SQL_VALIDITY = "sql_validity"
    UNKNOWN = "unknown"


class SemanticErrorRecord(BaseModel):
    category: SemanticErrorCategory
    message: str
    severity: str = "error"


_CATEGORY_MARKERS: list[tuple[SemanticErrorCategory, tuple[str, ...]]] = [
    (SemanticErrorCategory.TOP_N_SCOPE, ("top-n per group", "partition by", "rank")),
    (
        SemanticErrorCategory.RATE_DENOMINATOR,
        ("denominator", "mortality-rate", "conditional aggregation"),
    ),
    (
        SemanticErrorCategory.ABSENCE_CONDITION,
        ("absence", "non-occurrence", "not exists", "aggregate-zero"),
    ),
    (
        SemanticErrorCategory.UNKNOWN_BUCKET,
        ("unknown/no-information", "coalesce", "unmatched rows"),
    ),
    (SemanticErrorCategory.GROUPING_DIMENSION, ("grouping by", "group by does not include")),
    (SemanticErrorCategory.TEMPORAL_GRAIN, ("time-series", "temporal dimension")),
    (SemanticErrorCategory.SQL_VALIDITY, ("syntax", "invalid sql", "sql execution blocked")),
]


def classify_semantic_error(message: str | None) -> SemanticErrorCategory:
    if not message:
        return SemanticErrorCategory.UNKNOWN

    lowered = message.lower()
    for category, markers in _CATEGORY_MARKERS:
        if any(marker in lowered for marker in markers):
            return category
    return SemanticErrorCategory.UNKNOWN


def build_semantic_error_record(message: str | None) -> SemanticErrorRecord:
    normalized_message = message or "Unknown semantic error"
    return SemanticErrorRecord(
        category=classify_semantic_error(normalized_message),
        message=normalized_message,
    )
