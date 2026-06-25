"""Helpers to convert SQL execution output into chart-planning input."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .schema import ChartPlan, ChartPlanningInput
from .text_normalization import normalize_chart_label


def build_chart_planning_input(
    *,
    user_query: str,
    sql_query: str | None,
    results: list[dict[str, Any]],
    row_count: int,
    semantic_plan: dict[str, Any] | None = None,
    chart_hint: str = "auto",
    chart_plan: ChartPlan | dict[str, Any] | None = None,
) -> ChartPlanningInput:
    rows, columns = normalize_result_rows(results, sql_query)
    column_types = infer_column_types(rows, columns)
    parsed_chart_plan = (
        chart_plan
        if isinstance(chart_plan, ChartPlan) or chart_plan is None
        else ChartPlan.model_validate(chart_plan)
    )
    return ChartPlanningInput(
        user_query=user_query,
        last_sql_query=sql_query,
        semantic_plan=semantic_plan,
        columns=columns,
        column_types=column_types,
        rows=rows,
        row_count=row_count or len(rows),
        chart_hint=chart_hint,
        chart_plan=parsed_chart_plan,
    )


def normalize_result_rows(
    results: list[dict[str, Any]],
    sql_query: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize legacy SQL execution rows into dict rows for chart planning."""

    aliases = _extract_select_aliases(sql_query or "")
    rows: list[dict[str, Any]] = []
    for result in results or []:
        value = result.get("result") if isinstance(result, dict) and set(result.keys()) == {"result"} else result
        if isinstance(value, dict):
            normalized = {str(key): _json_safe(item) for key, item in value.items()}
        elif isinstance(value, (list, tuple)):
            keys = aliases if len(aliases) == len(value) else [f"col_{index + 1}" for index in range(len(value))]
            normalized = {keys[index]: _json_safe(item) for index, item in enumerate(value)}
        else:
            key = aliases[0] if len(aliases) == 1 else "value"
            normalized = {key: _json_safe(value)}
        rows.append(normalized)

    columns = list(rows[0].keys()) if rows else aliases
    return rows, columns


def infer_column_types(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, str]:
    return {column: _infer_type(rows, column) for column in columns}


def _infer_type(rows: list[dict[str, Any]], column: str) -> str:
    values = [row.get(column) for row in rows if row.get(column) is not None]
    if not values:
        return "unknown"
    if _looks_temporal(column, values):
        return "temporal"
    if all(isinstance(value, bool) for value in values):
        return "boolean"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return "number"
    return "string"


def _extract_select_aliases(sql_query: str) -> list[str]:
    select_clause = _select_clause(sql_query)
    if not select_clause:
        return []
    aliases: list[str] = []
    for item in _split_top_level(select_clause):
        alias = _alias_from_select_item(item)
        aliases.append(alias or f"col_{len(aliases) + 1}")
    return aliases


def _select_clause(sql_query: str) -> str:
    sql = sql_query.strip().rstrip(";")
    lower = sql.lower()
    select_start = _outer_keyword_index(sql, "select")
    if select_start < 0:
        return ""
    depth = 0
    quote: str | None = None
    for index in range(select_start + len("select"), len(sql)):
        char = sql[index]
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and lower[index:index + 6] == " from ":
            return sql[select_start + len("select"):index].strip()
    return ""


def _outer_keyword_index(sql: str, keyword: str) -> int:
    lower = sql.lower()
    depth = 0
    quote: str | None = None
    keyword_lower = keyword.lower()
    for index, char in enumerate(sql):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0 and lower.startswith(keyword_lower, index):
            before = lower[index - 1] if index > 0 else " "
            after_index = index + len(keyword_lower)
            after = lower[after_index] if after_index < len(lower) else " "
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                return index
    return -1


def _split_top_level(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        items.append("".join(current).strip())
    return items


def _alias_from_select_item(item: str) -> str | None:
    lowered = item.lower()
    if " as " in lowered:
        alias = item[lowered.rfind(" as ") + 4:].strip()
        return _clean_identifier(alias)
    parts = item.split()
    if len(parts) >= 2 and not parts[-1].endswith(")"):
        return _clean_identifier(parts[-1])
    tail = item.split(".")[-1]
    return _clean_identifier(tail)


def _clean_identifier(value: str) -> str:
    cleaned = value.strip().strip(",").strip('"')
    if "." in cleaned:
        cleaned = cleaned.split(".")[-1].strip('"')
    return cleaned


def _looks_temporal(column: str, values: list[Any]) -> bool:
    lowered = column.lower()
    if any(token in lowered for token in ["data", "date", "ano", "mes", "trimestre", "dt_"]):
        return True
    return all(isinstance(value, str) and _is_date_like(value) for value in values[:20])


def _is_date_like(value: str) -> bool:
    return bool(len(value) >= 4 and (value[:4].isdigit() or "/" in value or "-" in value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return normalize_chart_label(value)
    return value
