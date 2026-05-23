from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CANDIDATE_KEYS_PATH = ROOT / "docs" / "generated" / "candidate_keys.csv"


@dataclass(frozen=True)
class CandidateKey:
    table_name: str
    columns: tuple[str, ...]
    business_meaning: str
    row_count: int
    null_key_rows: int
    distinct_key_count: int
    duplicate_key_rows: int
    confidence: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> CandidateKey:
        return cls(
            table_name=(row.get("table_name") or "").strip().lower(),
            columns=_parse_columns(row.get("candidate_key") or ""),
            business_meaning=(row.get("business_meaning") or "").strip(),
            row_count=_parse_int(row.get("row_count")),
            null_key_rows=_parse_int(row.get("null_key_rows")),
            distinct_key_count=_parse_int(row.get("distinct_key_count")),
            duplicate_key_rows=_parse_int(row.get("duplicate_key_rows")),
            confidence=(row.get("confidence") or "").strip().lower(),
        )

    @property
    def is_confirmed(self) -> bool:
        return self.confidence == "confirmed"

    @property
    def is_unique(self) -> bool:
        return self.null_key_rows == 0 and self.duplicate_key_rows == 0

    @property
    def qualified_name(self) -> str:
        return f"{self.table_name}({', '.join(self.columns)})"


class CandidateKeyRegistry:
    def __init__(self, keys: list[CandidateKey]) -> None:
        self.keys = keys
        self._by_table = {key.table_name: key for key in keys}

    def lookup(self, table_name: str) -> CandidateKey | None:
        return self._by_table.get(table_name.strip().lower())

    def is_candidate_key(self, table_name: str, columns: list[str] | tuple[str, ...]) -> bool:
        key = self.lookup(table_name)
        if key is None:
            return False
        normalized = tuple(column.strip().lower() for column in columns)
        return normalized == tuple(column.lower() for column in key.columns)


@lru_cache(maxsize=8)
def load_candidate_key_registry(
    path: str | Path = DEFAULT_CANDIDATE_KEYS_PATH,
) -> CandidateKeyRegistry:
    csv_path = Path(path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return CandidateKeyRegistry([CandidateKey.from_row(row) for row in rows])


def _parse_columns(value: str) -> tuple[str, ...]:
    return tuple(column.strip() for column in value.split(",") if column.strip())


def _parse_int(value: str | None) -> int:
    if value is None or value == "":
        return 0
    return int(float(value))
