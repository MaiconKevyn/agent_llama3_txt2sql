"""Lightweight SQL semantic-equivalence helpers.

These helpers are not a replacement for execution-based evaluation. They provide
a stable structural fingerprint so evaluation can distinguish "same semantic
pattern, different formatting/aliases" from truly different query strategies.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .sql_inspector import SQLInspector


class SQLSemanticSignature(BaseModel):
    tables: set[str] = Field(default_factory=set)
    group_by: str = ""
    where: str = ""
    having: str = ""
    has_window_partition: bool = False
    has_conditional_mortality_numerator: bool = False
    has_absence_pattern: bool = False
    has_unknown_bucket_expression: bool = False


def semantic_sql_signature(sql: str) -> SQLSemanticSignature:
    inspector = SQLInspector.from_sql(sql)
    return SQLSemanticSignature(
        tables=_extract_table_names(inspector.text_lower),
        group_by=_canonical_clause(inspector.clause_lower("GROUP BY")),
        where=_canonical_clause(inspector.clause_lower("WHERE")),
        having=_canonical_clause(inspector.clause_lower("HAVING")),
        has_window_partition=inspector.has_window_partition(),
        has_conditional_mortality_numerator=inspector.has_conditional_aggregation_for("morte"),
        has_absence_pattern=inspector.has_absence_pattern(),
        has_unknown_bucket_expression=inspector.has_unknown_bucket_expression(),
    )


def same_semantic_pattern(left_sql: str, right_sql: str) -> bool:
    """Return whether two SQL strings share the same structural semantic pattern."""
    left = semantic_sql_signature(left_sql)
    right = semantic_sql_signature(right_sql)
    return left == right


def _extract_table_names(sql_lower: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"\b(?:from|join)\s+\"?([a-z_][\w]*)\"?", sql_lower, re.I):
        names.add(match.group(1).lower())
    return names


def _canonical_clause(clause: str) -> str:
    text = re.sub(r"\b[a-z_][\w]*\s*\.\s*", "", clause.lower())
    text = re.sub(r"\"([a-z_][\w]*)\"", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
