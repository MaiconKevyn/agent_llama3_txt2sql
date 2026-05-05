"""SQL inspection helpers for semantic validators.

The inspector uses sqlparse when available to split clauses and strip comments,
then falls back to conservative text inspection. It intentionally keeps a small
surface area so semantic validation can improve without depending on one SQL
dialect or mutating generated SQL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

try:  # pragma: no cover - exercised indirectly when dependency is installed
    import sqlparse
    from sqlparse import tokens as T
except Exception:  # pragma: no cover - fallback path for minimal environments
    sqlparse = None
    T = None


_CLAUSE_KEYWORDS = {
    "SELECT",
    "FROM",
    "WHERE",
    "GROUP BY",
    "HAVING",
    "ORDER BY",
    "LIMIT",
    "QUALIFY",
    "WINDOW",
    "UNION",
    "EXCEPT",
    "INTERSECT",
}


@dataclass(frozen=True)
class SQLInspector:
    """Normalized SQL facts used by semantic validators."""

    original_sql: str
    normalized_sql: str
    clauses: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_sql(cls, sql: str) -> SQLInspector:
        normalized = _normalize_sql(sql)
        clauses = _extract_clauses(normalized)
        return cls(original_sql=sql, normalized_sql=normalized, clauses=clauses)

    @property
    def text_lower(self) -> str:
        return self.normalized_sql.lower()

    def clause_text(self, keyword: str) -> str:
        normalized_keyword = keyword.upper()
        values = self.clauses.get(normalized_keyword)
        if values:
            return " ".join(values).strip()
        fallback = _extract_clauses_by_regex(self.normalized_sql).get(normalized_keyword, [])
        return " ".join(fallback).strip()

    def clause_lower(self, keyword: str) -> str:
        return self.clause_text(keyword).lower()

    def has_group_by(self) -> bool:
        return bool(self.clause_text("GROUP BY"))

    def has_window_partition(self) -> bool:
        return bool(
            re.search(
                r"\b(?:row_number|rank|dense_rank)\s*\(\s*\)\s+over\s*\([^)]*\bpartition\s+by\b",
                self.text_lower,
                re.I,
            )
        )

    def window_rank_aliases(self) -> set[str]:
        aliases: set[str] = set()
        for match in re.finditer(
            r"\b(?:row_number|rank|dense_rank)\s*\(\s*\)\s+over\s*\([^)]*\)\s+as\s+\"?([a-z_][\w]*)\"?",
            self.text_lower,
            re.I,
        ):
            aliases.add(match.group(1).lower())
        return aliases

    def constrains_rank(self, top_n: int | None) -> bool:
        aliases = self.window_rank_aliases() or {"rn", "rank", "rk", "rank_num", "ranking"}
        predicate_text = " ".join(
            [
                self.clause_lower("WHERE"),
                self.clause_lower("HAVING"),
                self.clause_lower("QUALIFY"),
                self.text_lower,
            ]
        )
        for alias in aliases:
            if top_n is None:
                if re.search(rf"\b\"?{re.escape(alias)}\"?\s*(?:<=|<|=)\s*\d+\b", predicate_text):
                    return True
                continue

            patterns = [
                rf"\b\"?{re.escape(alias)}\"?\s*<=\s*{top_n}\b",
                rf"\b\"?{re.escape(alias)}\"?\s*<\s*{top_n + 1}\b",
                rf"\b\"?{re.escape(alias)}\"?\s*=\s*1\b" if top_n == 1 else "",
            ]
            if any(pattern and re.search(pattern, predicate_text, re.I) for pattern in patterns):
                return True
        return False

    def where_filters_outcome(self, outcome_column: str, true_value: str = "true") -> bool:
        where = self.clause_lower("WHERE")
        if not where:
            return False
        return bool(
            re.search(
                rf"\b\"?{re.escape(outcome_column.lower())}\"?\s*=\s*{re.escape(true_value.lower())}\b",
                where,
                re.I,
            )
        )

    def has_conditional_aggregation_for(self, column: str) -> bool:
        return bool(
            re.search(
                rf"\bsum\s*\(\s*case\s+when[\s\S]*\b\"?{re.escape(column.lower())}\"?\b",
                self.text_lower,
                re.I,
            )
        )

    def has_absence_pattern(self) -> bool:
        has_not_exists = bool(re.search(r"\bnot\s+exists\b", self.text_lower, re.I))
        has_left_join_null = bool(
            re.search(r"\bleft\s+join\b[\s\S]*\bis\s+null\b", self.text_lower, re.I)
        )
        has_aggregate_zero = bool(
            re.search(
                r"\bsum\s*\(\s*case\s+when[\s\S]*\)\s*(?:=|<=)\s*0\b",
                self.clause_lower("HAVING") or self.text_lower,
                re.I,
            )
        )
        return has_not_exists or has_left_join_null or has_aggregate_zero

    def has_unknown_bucket_expression(self) -> bool:
        text = self.text_lower
        return "coalesce" in text or bool(
            re.search(r"\bcase\s+when[\s\S]*(?:is\s+null|sem\s+informa)", text, re.I)
        )

    def joins_preserve_unknowns(self) -> bool:
        text = self.text_lower
        return " join " not in text or "left join" in text


def _normalize_sql(sql: str) -> str:
    if sqlparse is None:
        return " ".join(sql.split())
    return sqlparse.format(
        sql,
        keyword_case="upper",
        identifier_case=None,
        strip_comments=True,
        reindent=False,
        strip_whitespace=True,
    )


def _extract_clauses(sql: str) -> dict[str, list[str]]:
    if sqlparse is None:
        return _extract_clauses_by_regex(sql)

    clauses: dict[str, list[str]] = {}
    for statement in sqlparse.parse(sql):
        current_keyword: str | None = None
        current_parts: list[str] = []
        paren_depth = 0

        for token in statement.flatten():
            value = token.value
            upper = token.normalized.upper()
            if value == "(":
                paren_depth += 1
            elif value == ")":
                paren_depth = max(paren_depth - 1, 0)

            is_clause = paren_depth == 0 and _is_clause_keyword(token, upper)
            if is_clause:
                if current_keyword and current_parts:
                    clauses.setdefault(current_keyword, []).append(" ".join(current_parts).strip())
                current_keyword = upper
                current_parts = []
                continue

            if current_keyword and not token.is_whitespace:
                current_parts.append(value)

        if current_keyword and current_parts:
            clauses.setdefault(current_keyword, []).append(" ".join(current_parts).strip())

    if not clauses:
        return _extract_clauses_by_regex(sql)
    return clauses


def _is_clause_keyword(token: object, upper: str) -> bool:
    if upper not in _CLAUSE_KEYWORDS:
        return False
    if T is None:
        return True
    token_type = getattr(token, "ttype", None)
    return bool(token_type in T.Keyword or token_type in T.DML)


def _extract_clauses_by_regex(sql: str) -> dict[str, list[str]]:
    clauses: dict[str, list[str]] = {}
    pattern = re.compile(
        r"\b(SELECT|FROM|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|QUALIFY|WINDOW)\b",
        re.I,
    )
    matches = list(pattern.finditer(sql))
    for idx, match in enumerate(matches):
        key = " ".join(match.group(1).upper().split())
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(sql)
        clauses.setdefault(key, []).append(sql[start:end].strip())
    return clauses
