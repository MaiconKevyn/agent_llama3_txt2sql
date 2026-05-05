"""Typed loader and lookup helpers for persisted semantic data profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_profile import ColumnProfile, SemanticProfile

PROFILE_DIR = Path(__file__).parent / "profiles"
GENERATED_PROFILE_PATH = PROFILE_DIR / "generated_profile.json"


class SemanticProfileStore:
    """Read-only profile lookup used by planners and validators."""

    def __init__(self, profile: SemanticProfile | None = None):
        self.profile = profile or SemanticProfile()

    def get_column(self, table: str, column: str) -> ColumnProfile | None:
        table_profile = self.profile.tables.get(table)
        if table_profile is None:
            return None
        return table_profile.columns.get(column)

    def describe_column(self, table: str, column: str) -> dict[str, Any]:
        profile = self.get_column(table, column)
        if profile is None:
            return {}
        return profile.model_dump(exclude_none=True)

    def temporal_range(self, table: str, column: str) -> tuple[str | None, str | None] | None:
        profile = self.get_column(table, column)
        if profile is None or profile.kind != "temporal":
            return None
        return _as_text(profile.min_value), _as_text(profile.max_value)

    def null_rate(self, table: str, column: str) -> float | None:
        profile = self.get_column(table, column)
        if profile is None or not profile.row_count:
            return None
        null_count = profile.null_count or 0
        return null_count / profile.row_count

    def high_cardinality(self, table: str, column: str, threshold: int = 100) -> bool:
        profile = self.get_column(table, column)
        return bool(profile and profile.distinct_count and profile.distinct_count >= threshold)

    def has_top_value(self, table: str, column: str, value: str) -> bool:
        profile = self.get_column(table, column)
        if profile is None:
            return False
        needle = value.strip().lower()
        for item in profile.top_values:
            candidate = item.get("value")
            if candidate is not None and str(candidate).strip().lower() == needle:
                return True
        return False


def load_semantic_profile(path: str | Path | None = None) -> SemanticProfile | None:
    profile_path = Path(path) if path else GENERATED_PROFILE_PATH
    if not profile_path.exists():
        return None
    return SemanticProfile.model_validate_json(profile_path.read_text(encoding="utf-8"))


def load_profile_store(
    path: str | Path | None = None, *, strict: bool = False
) -> SemanticProfileStore:
    try:
        profile = load_semantic_profile(path)
    except Exception:
        if strict:
            raise
        profile = None
    return SemanticProfileStore(profile)


def save_semantic_profile(profile: SemanticProfile, path: str | Path | None = None) -> Path:
    profile_path = Path(path) if path else GENERATED_PROFILE_PATH
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        profile.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    return profile_path


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
