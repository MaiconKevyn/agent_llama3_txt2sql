"""Shared paths for generated database schema artifacts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERATED_SCHEMA_DIR = Path(__file__).resolve().parent / "generated"
LEGACY_DOCS_GENERATED_DIR = ROOT / "docs" / "generated"


def generated_schema_artifact(filename: str) -> Path:
    """Return the authoritative generated schema artifact path.

    Older semantic-contract loaders used `docs/generated`. The current project
    keeps the generated DuckDB schema snapshot under
    `src/application/schema/generated`, so prefer that path and only fall back
    to the docs directory for legacy checkouts.
    """
    current_path = GENERATED_SCHEMA_DIR / filename
    if current_path.exists():
        return current_path
    return LEGACY_DOCS_GENERATED_DIR / filename
