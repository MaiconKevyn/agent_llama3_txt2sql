"""Lightweight SQL structural parser used by semantic contract validation."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .sql_inspector import SQLInspector


class SQLJoinEdge(BaseModel):
    join_type: str = "JOIN"
    table: str
    alias: str | None = None
    condition: str | None = None


class SQLWindowFunction(BaseModel):
    name: str
    partition_by: list[str] = Field(default_factory=list)
    order_by: list[str] = Field(default_factory=list)


class SQLAstSummary(BaseModel):
    parse_status: str = "parsed"
    tables: list[str] = Field(default_factory=list)
    aliases: dict[str, str] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    joins: list[SQLJoinEdge] = Field(default_factory=list)
    ctes: list[str] = Field(default_factory=list)
    where: str = ""
    group_by: str = ""
    having: str = ""
    window_functions: list[SQLWindowFunction] = Field(default_factory=list)


def parse_sql_ast(sql: str) -> SQLAstSummary:
    """Extract structural SQL facts without depending on one database dialect."""
    inspector = SQLInspector.from_sql(sql)
    normalized = inspector.normalized_sql
    lowered = normalized.lower()

    try:
        ctes = _extract_ctes(normalized)
        sql_for_table_scans = _mask_function_inner_from(normalized)
        aliases = _extract_table_aliases(sql_for_table_scans)
        joins = _extract_joins(normalized)
        tables = _stable_unique(
            [
                table
                for table in aliases.values()
                if table.lower() not in {cte.lower() for cte in ctes}
            ]
            + [
                join.table
                for join in joins
                if join.table.lower() not in {cte.lower() for cte in ctes}
            ]
        )
        return SQLAstSummary(
            parse_status="parsed",
            tables=tables,
            aliases=aliases,
            columns=_extract_columns(normalized),
            joins=joins,
            ctes=ctes,
            where=inspector.clause_text("WHERE"),
            group_by=inspector.clause_text("GROUP BY"),
            having=inspector.clause_text("HAVING"),
            window_functions=_extract_window_functions(lowered),
        )
    except Exception:
        sql_for_table_scans = _mask_function_inner_from(lowered)
        return SQLAstSummary(
            parse_status="fallback",
            tables=_stable_unique(
                re.findall(r"\b(?:from|join)\s+\"?([a-z_][\w]*)\"?", sql_for_table_scans)
            ),
            where=inspector.clause_text("WHERE"),
            group_by=inspector.clause_text("GROUP BY"),
            having=inspector.clause_text("HAVING"),
            window_functions=_extract_window_functions(lowered),
        )


def _extract_ctes(sql: str) -> list[str]:
    if not re.search(r"^\s*WITH\b", sql, re.I):
        return []
    return _stable_unique(re.findall(r"(?:WITH|,)\s+\"?([a-z_][\w]*)\"?\s+AS\s*\(", sql, re.I))


def _mask_function_inner_from(sql: str) -> str:
    """Avoid treating EXTRACT(... FROM column) as a table FROM clause."""
    return re.sub(
        r"\bEXTRACT\s*\(\s*([a-z_]+)\s+FROM\s+([\s\S]*?)\)",
        lambda match: f"EXTRACT({match.group(1)} __FROM__ {match.group(2)})",
        sql,
        flags=re.I,
    )


def _extract_table_aliases(sql: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in re.finditer(
        r"\b(?:FROM|JOIN)\s+\"?([a-z_][\w]*)\"?(?:\s+(?:AS\s+)?\"?([a-z_][\w]*)\"?)?",
        sql,
        re.I,
    ):
        table = match.group(1)
        alias = match.group(2) or table
        if alias.upper() in {"ON", "WHERE", "GROUP", "ORDER", "JOIN", "LEFT", "RIGHT", "INNER"}:
            alias = table
        aliases[alias] = table
    return aliases


def _extract_joins(sql: str) -> list[SQLJoinEdge]:
    joins: list[SQLJoinEdge] = []
    pattern = re.compile(
        r"\b((?:LEFT|RIGHT|INNER|FULL|CROSS)?\s*JOIN)\s+\"?([a-z_][\w]*)\"?"
        r"(?:\s+(?:AS\s+)?\"?([a-z_][\w]*)\"?)?"
        r"(?:\s+ON\s+([\s\S]*?))?"
        r"(?=\b(?:LEFT|RIGHT|INNER|FULL|CROSS)?\s*JOIN\b|\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)",
        re.I,
    )
    for match in pattern.finditer(sql):
        alias = match.group(3)
        if alias and alias.upper() in {"ON", "WHERE", "GROUP", "ORDER"}:
            alias = None
        joins.append(
            SQLJoinEdge(
                join_type=" ".join(match.group(1).upper().split()),
                table=match.group(2),
                alias=alias,
                condition=(match.group(4) or "").strip() or None,
            )
        )
    return joins


def _extract_columns(sql: str) -> list[str]:
    columns = re.findall(r"\"?([a-z_][\w]*)\"?\s*\.\s*\"?([a-z_][\w]*)\"?", sql, re.I)
    return _stable_unique([f"{alias}.{column}" for alias, column in columns])


def _extract_window_functions(sql_lower: str) -> list[SQLWindowFunction]:
    windows: list[SQLWindowFunction] = []
    for match in re.finditer(
        r"\b(row_number|rank|dense_rank)\s*\(\s*\)\s+over\s*\(([\s\S]*?)\)",
        sql_lower,
        re.I,
    ):
        body = match.group(2)
        partition_by = _split_clause_values(body, "partition by", "order by")
        order_by = _split_clause_values(body, "order by", None)
        windows.append(
            SQLWindowFunction(
                name=match.group(1).lower(),
                partition_by=partition_by,
                order_by=order_by,
            )
        )
    return windows


def _split_clause_values(text: str, start_keyword: str, end_keyword: str | None) -> list[str]:
    pattern = rf"{re.escape(start_keyword)}\s+([\s\S]*?)"
    if end_keyword:
        pattern += rf"(?=\b{re.escape(end_keyword)}\b|$)"
    else:
        pattern += "$"
    match = re.search(pattern, text, re.I)
    if not match:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result
