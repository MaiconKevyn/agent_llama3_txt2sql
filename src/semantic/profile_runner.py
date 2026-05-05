"""CLI runner that persists semantic data profiles from the configured database."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.application.config.simple_config import ApplicationConfig

from .catalog import catalog_summary
from .data_profile import (
    ColumnProfile,
    ColumnProfileSpec,
    SemanticProfile,
    build_column_profile_queries,
    default_profile_specs,
)
from .profile_store import GENERATED_PROFILE_PATH, save_semantic_profile

QueryExecutor = Callable[[str], Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]]]


def run_profile_specs(
    specs: Iterable[ColumnProfileSpec],
    execute_sql: QueryExecutor,
    *,
    generated_at: str | None = None,
    source: str | None = None,
    catalog_version: int | None = None,
) -> SemanticProfile:
    """Execute profile specs with an injected SQL executor and return a snapshot."""
    profile = SemanticProfile(
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        source=source,
        catalog_version=catalog_version,
    )

    for spec in specs:
        query_set = build_column_profile_queries(spec)
        summary_rows = execute_sql(query_set.summary_sql)
        summary = _first_row(summary_rows)
        column_profile = ColumnProfile(
            table=spec.table,
            column=spec.column,
            kind=spec.kind,
            row_count=_to_int(summary.get("row_count")),
            null_count=_to_int(summary.get("null_count")),
            distinct_count=_to_int(summary.get("distinct_count")),
            min_value=_normalize_scalar(summary.get("min_value")),
            max_value=_normalize_scalar(summary.get("max_value")),
        )

        if query_set.top_values_sql:
            top_rows = execute_sql(query_set.top_values_sql)
            column_profile.top_values = [
                {
                    "value": _normalize_scalar(row.get("value")),
                    "frequency": _to_int(row.get("frequency")) or 0,
                }
                for row in _row_mappings(top_rows)
            ]

        profile.add_column(column_profile)

    return profile


def profile_database(
    db_url: str | None = None,
    *,
    output_path: str | Path | None = None,
    max_specs: int | None = None,
) -> Path:
    load_dotenv()
    resolved_db_url = db_url or ApplicationConfig().database_path
    if not resolved_db_url:
        raise ValueError("Database URL is required via --db-url, DATABASE_URL or DATABASE_PATH")

    engine = create_engine(resolved_db_url)
    specs = default_profile_specs()
    if max_specs is not None:
        specs = specs[:max_specs]

    with engine.connect() as connection:
        profile = run_profile_specs(
            specs,
            lambda sql: [dict(row._mapping) for row in connection.execute(text(sql))],
            source=redact_database_url(resolved_db_url),
            catalog_version=catalog_summary()["version"],
        )

    return save_semantic_profile(profile, output_path or GENERATED_PROFILE_PATH)


def redact_database_url(db_url: str) -> str:
    parsed = urlsplit(db_url)
    if not parsed.netloc:
        return db_url
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = parsed.username or ""
    auth = f"{user}:***@" if user else ""
    return urlunsplit((parsed.scheme, f"{auth}{host}{port}", parsed.path, "", ""))


def _first_row(rows: Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]]) -> dict[str, Any]:
    mappings = _row_mappings(rows)
    if not mappings:
        return {}
    return mappings[0]


def _row_mappings(
    rows: Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            normalized.append(dict(row))
        elif hasattr(row, "_mapping"):
            normalized.append(dict(row._mapping))
        else:
            sequence = list(row)
            if len(sequence) == 2:
                normalized.append({"value": sequence[0], "frequency": sequence[1]})
            elif len(sequence) >= 5:
                normalized.append(
                    {
                        "row_count": sequence[0],
                        "null_count": sequence[1],
                        "distinct_count": sequence[2],
                        "min_value": sequence[3],
                        "max_value": sequence[4],
                    }
                )
            elif len(sequence) >= 3:
                normalized.append(
                    {
                        "row_count": sequence[0],
                        "null_count": sequence[1],
                        "distinct_count": sequence[2],
                    }
                )
    return normalized


def _normalize_scalar(value: Any) -> str | int | float | None:
    if value is None or isinstance(value, str | int | float):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate persistent semantic data profiles.")
    parser.add_argument("--db-url", default=None, help="Database URL. Defaults to env config.")
    parser.add_argument(
        "--output",
        default=str(GENERATED_PROFILE_PATH),
        help="Output JSON path for the generated profile.",
    )
    parser.add_argument(
        "--max-specs",
        type=int,
        default=None,
        help="Optional smoke-test limit for number of profile specs to execute.",
    )
    args = parser.parse_args(argv)

    output_path = profile_database(args.db_url, output_path=args.output, max_specs=args.max_specs)
    print(f"Semantic profile written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
