from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JOIN_POLICY_PATH = ROOT / "docs" / "generated" / "join_policy.csv"

BUSINESS_INNER_JOIN_ALLOWED = "business_inner_join_allowed"
LEFT_JOIN_OR_EXPLICIT_SCOPE = "left_join_or_explicit_mapped_scope_required"
AUDIT_ONLY = "audit_only"


@dataclass(frozen=True)
class JoinEndpoint:
    table: str
    column: str

    @classmethod
    def parse(cls, value: str) -> JoinEndpoint:
        table, _, column = value.strip().partition(".")
        if not table or not column:
            raise ValueError(f"Invalid qualified join endpoint: {value!r}")
        return cls(table=table.lower(), column=column.lower())

    @property
    def qualified_name(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass(frozen=True)
class JoinPolicy:
    left: JoinEndpoint
    right: JoinEndpoint
    business_meaning: str
    left_rows: int | None
    matched_rows: int | None
    unmatched_rows: int | None
    match_rate_non_null: float | None
    confidence: str
    accepted_usage_policy: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> JoinPolicy:
        return cls(
            left=JoinEndpoint.parse(row["left"]),
            right=JoinEndpoint.parse(row["right"]),
            business_meaning=(row.get("business_meaning") or "").strip(),
            left_rows=_parse_int(row.get("left_rows")),
            matched_rows=_parse_int(row.get("matched_rows")),
            unmatched_rows=_parse_int(row.get("unmatched_rows")),
            match_rate_non_null=_parse_float(row.get("match_rate_non_null")),
            confidence=(row.get("confidence") or "").strip().lower(),
            accepted_usage_policy=(row.get("accepted_usage_policy") or "").strip().lower(),
        )

    @property
    def is_allowed(self) -> bool:
        return self.accepted_usage_policy in {
            BUSINESS_INNER_JOIN_ALLOWED,
            LEFT_JOIN_OR_EXPLICIT_SCOPE,
        }

    @property
    def requires_caveat(self) -> bool:
        return self.accepted_usage_policy == LEFT_JOIN_OR_EXPLICIT_SCOPE

    @property
    def is_audit_only(self) -> bool:
        return self.accepted_usage_policy == AUDIT_ONLY

    @property
    def caveat_code(self) -> str | None:
        if self.requires_caveat:
            return f"{self.left.table}_{self.left.column}_mapped_scope"
        if self.is_audit_only:
            return f"{self.left.table}_{self.left.column}_audit_only"
        return None

    @property
    def message_ptbr(self) -> str | None:
        if self.requires_caveat:
            return (
                f"O join {self.left.qualified_name} -> {self.right.qualified_name} "
                "tem cobertura imperfeita; resultados consideram registros mapeaveis."
            )
        if self.is_audit_only:
            return (
                f"O join {self.left.qualified_name} -> {self.right.qualified_name} "
                "e audit-only e nao deve ser usado como relacao analitica normal sem escopo explicito."
            )
        return None


class JoinPolicyRegistry:
    def __init__(self, policies: list[JoinPolicy]) -> None:
        self.policies = policies
        self._by_pair: dict[tuple[str, str], JoinPolicy] = {}
        for policy in policies:
            left = policy.left.qualified_name
            right = policy.right.qualified_name
            self._by_pair[(left, right)] = policy
            self._by_pair[(right, left)] = policy

    def lookup(
        self,
        left_table: str,
        left_column: str,
        right_table: str,
        right_column: str,
    ) -> JoinPolicy | None:
        left = f"{left_table.strip().lower()}.{left_column.strip().lower()}"
        right = f"{right_table.strip().lower()}.{right_column.strip().lower()}"
        return self._by_pair.get((left, right))


def policies_for_sql_joins(
    sql: str,
    registry: JoinPolicyRegistry | None = None,
) -> list[JoinPolicy]:
    registry = registry or load_join_policy_registry()
    normalized = sql.replace('"', "").lower()
    aliases = _extract_table_aliases(normalized)
    policies: list[JoinPolicy] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(
        r"\b([a-z_][\w]*)\.([a-z_][\w]*)\s*=\s*([a-z_][\w]*)\.([a-z_][\w]*)\b",
        normalized,
        re.I,
    ):
        left_alias, left_column, right_alias, right_column = match.groups()
        left_table = aliases.get(left_alias, left_alias)
        right_table = aliases.get(right_alias, right_alias)
        policy = registry.lookup(left_table, left_column, right_table, right_column)
        if policy is None:
            continue
        key = tuple(sorted([policy.left.qualified_name, policy.right.qualified_name]))
        if key not in seen:
            policies.append(policy)
            seen.add(key)
    return policies


@lru_cache(maxsize=8)
def load_join_policy_registry(path: str | Path = DEFAULT_JOIN_POLICY_PATH) -> JoinPolicyRegistry:
    csv_path = Path(path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return JoinPolicyRegistry([JoinPolicy.from_row(row) for row in rows])


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _extract_table_aliases(sql_lower: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    stop_words = {
        "on",
        "where",
        "join",
        "left",
        "right",
        "inner",
        "full",
        "cross",
        "group",
        "order",
        "limit",
    }
    for match in re.finditer(
        r"\b(?:from|join)\s+([a-z_][\w]*)(?:\s+(?:as\s+)?([a-z_][\w]*))?",
        sql_lower,
        re.I,
    ):
        table, alias = match.groups()
        aliases[table] = table
        if alias and alias not in stop_words:
            aliases[alias] = table
    return aliases
