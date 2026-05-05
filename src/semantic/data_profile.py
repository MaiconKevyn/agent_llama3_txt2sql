"""Data profiling primitives for semantic Text-to-SQL robustness.

Profiles capture stable facts the agent can use to disambiguate domains:
cardinality, null rates, value ranges, and common categorical values. This
module builds dialect-light SQL snippets and typed containers; callers can
execute the generated SQL with the repository's existing database layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ColumnKind = Literal["categorical", "numeric", "temporal", "identifier", "unknown"]


class ColumnProfileSpec(BaseModel):
    table: str
    column: str
    kind: ColumnKind = "unknown"
    top_k: int = 20


class ColumnProfile(BaseModel):
    table: str
    column: str
    kind: ColumnKind
    row_count: int | None = None
    null_count: int | None = None
    distinct_count: int | None = None
    min_value: str | int | float | None = None
    max_value: str | int | float | None = None
    top_values: list[dict[str, str | int | float | None]] = Field(default_factory=list)


class TableProfile(BaseModel):
    table: str
    row_count: int | None = None
    columns: dict[str, ColumnProfile] = Field(default_factory=dict)


class SemanticProfile(BaseModel):
    """Persisted profile snapshot for semantic planning and validation."""

    generated_at: str | None = None
    source: str | None = None
    catalog_version: int | None = None
    tables: dict[str, TableProfile] = Field(default_factory=dict)

    def add_column(self, profile: ColumnProfile) -> None:
        table_profile = self.tables.setdefault(
            profile.table,
            TableProfile(table=profile.table, row_count=profile.row_count),
        )
        if table_profile.row_count is None:
            table_profile.row_count = profile.row_count
        table_profile.columns[profile.column] = profile


class ProfileQuerySet(BaseModel):
    table: str
    column: str
    summary_sql: str
    top_values_sql: str | None = None


def quote_identifier(identifier: str) -> str:
    """Quote a SQL identifier after validating it is a simple identifier."""
    if not identifier or "\x00" in identifier:
        raise ValueError("Identifier cannot be empty or contain null bytes")
    return '"' + identifier.replace('"', '""') + '"'


def build_column_profile_queries(spec: ColumnProfileSpec) -> ProfileQuerySet:
    table = quote_identifier(spec.table)
    column = quote_identifier(spec.column)

    summary_sql = (
        "SELECT "
        "COUNT(*) AS row_count, "
        f"SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) AS null_count, "
        f"COUNT(DISTINCT {column}) AS distinct_count"
    )

    if spec.kind in {"numeric", "temporal"}:
        summary_sql += f", MIN({column}) AS min_value, MAX({column}) AS max_value"

    summary_sql += f" FROM {table};"

    top_values_sql = None
    if spec.kind in {"categorical", "identifier", "unknown"}:
        top_values_sql = (
            f"SELECT {column} AS value, COUNT(*) AS frequency "
            f"FROM {table} "
            f"GROUP BY {column} "
            "ORDER BY frequency DESC "
            f"LIMIT {spec.top_k};"
        )

    return ProfileQuerySet(
        table=spec.table,
        column=spec.column,
        summary_sql=summary_sql,
        top_values_sql=top_values_sql,
    )


def default_profile_specs() -> list[ColumnProfileSpec]:
    """Core columns worth profiling before broad semantic rollout."""
    return [
        ColumnProfileSpec(table="internacoes", column="MORTE", kind="categorical"),
        ColumnProfileSpec(table="internacoes", column="VAL_UTI", kind="numeric"),
        ColumnProfileSpec(table="internacoes", column="DT_INTER", kind="temporal"),
        ColumnProfileSpec(table="internacoes", column="SEXO", kind="categorical"),
        ColumnProfileSpec(table="internacoes", column="RACA_COR", kind="categorical"),
        ColumnProfileSpec(table="internacoes", column="CNES", kind="identifier"),
        ColumnProfileSpec(table="internacoes", column="MUNIC_RES", kind="identifier"),
        ColumnProfileSpec(table="atendimentos", column="PROC_REA", kind="identifier"),
        ColumnProfileSpec(table="municipios", column="estado", kind="categorical"),
        ColumnProfileSpec(table="hospital", column="MUNIC_MOV", kind="identifier"),
    ]


def build_default_profile_query_sets() -> list[ProfileQuerySet]:
    return [build_column_profile_queries(spec) for spec in default_profile_specs()]
