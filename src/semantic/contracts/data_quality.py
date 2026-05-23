from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_QUALITY_PATH = ROOT / "docs" / "generated" / "data_quality_checks.json"

SEVERITY_ORDER = {"medium": 1, "high": 2, "critical": 3}
CHECK_REQUIRED_TOKENS = {
    "DQ002": {"internacoes", "dt_inter"},
    "DQ003": {"internacoes", "dt_saida"},
    "DQ004": {"internacoes", "dt_inter", "dt_saida", "dias_perm"},
    "DQ005": {"internacoes", "val_tot"},
    "DQ006": {"internacoes", "idade"},
    "DQ007": {"internacoes", "cnes"},
    "DQ008": {"internacoes", "diag_princ"},
    "DQ009": {"internacoes", "hospital", "cnes"},
    "DQ010": {"internacoes", "munic_res", "municipios", "co_municipio_6d"},
    "DQ011": {"internacoes", "diag_princ", "cid"},
    "DQ012": {"internacao_procedimento", "procedimentos", "proc_rea"},
    "DQ013": {"internacoes", "hospital", "no_hospital"},
    "DQ014": {"sexo", "descricao"},
    "DQ015": {"internacoes", "val_tot", "val_sh", "val_sp", "val_uti"},
    "DQ016": {"municipios", "sg_uf"},
    "DQ017": {"municipios", "co_municipio_6d"},
    "DQ018": {"municipios", "co_municipio_7d"},
}


@dataclass(frozen=True)
class DataQualityCheck:
    id: str
    title: str
    severity: str
    why_it_matters: str
    affected_rows: int
    sql: str
    sample_sql: str | None
    blocks_ground_truth: bool

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DataQualityCheck:
        return cls(
            id=str(row.get("id") or "").strip(),
            title=str(row.get("title") or "").strip(),
            severity=str(row.get("severity") or "").strip().lower(),
            why_it_matters=str(row.get("why_it_matters") or "").strip(),
            affected_rows=int(row.get("affected_rows") or 0),
            sql=str(row.get("sql") or "").strip(),
            sample_sql=row.get("sample_sql"),
            blocks_ground_truth=bool(row.get("blocks_ground_truth")),
        )

    @property
    def has_findings(self) -> bool:
        return self.affected_rows > 0

    @property
    def severity_rank(self) -> int:
        return SEVERITY_ORDER.get(self.severity, 0)

    @property
    def message_ptbr(self) -> str | None:
        if not self.has_findings:
            return None
        rows = f"{self.affected_rows:,}".replace(",", ".")
        return (
            f"{self.id} ({self.severity}): {self.title} afeta {rows} registros. "
            f"{self.why_it_matters}"
        )

    @property
    def referenced_tokens(self) -> set[str]:
        return _extract_sql_tokens(self.sql)

    @property
    def required_tokens(self) -> set[str]:
        return CHECK_REQUIRED_TOKENS.get(self.id.upper(), set())


class DataQualityRegistry:
    def __init__(self, checks: list[DataQualityCheck]) -> None:
        self.checks = checks
        self._by_id = {check.id.upper(): check for check in checks}

    def lookup(self, check_id: str) -> DataQualityCheck | None:
        return self._by_id.get(check_id.strip().upper())

    def checks_for_sql(
        self,
        sql: str,
        *,
        min_severity: str = "medium",
        findings_only: bool = True,
    ) -> list[DataQualityCheck]:
        sql_tokens = _extract_sql_tokens(sql)
        min_rank = SEVERITY_ORDER.get(min_severity.lower(), 0)
        matching: list[DataQualityCheck] = []
        for check in self.checks:
            if findings_only and not check.has_findings:
                continue
            if check.severity_rank < min_rank:
                continue
            if _check_matches_sql(check, sql_tokens):
                matching.append(check)
        return matching


def data_quality_caveats_for_sql(
    sql: str | None,
    *,
    registry: DataQualityRegistry | None = None,
    min_severity: str = "medium",
) -> list[str]:
    if not sql:
        return []
    registry = registry or load_data_quality_registry()
    caveats: list[str] = []
    for check in registry.checks_for_sql(sql, min_severity=min_severity):
        if check.message_ptbr and check.message_ptbr not in caveats:
            caveats.append(check.message_ptbr)
    return caveats


@lru_cache(maxsize=8)
def load_data_quality_registry(
    path: str | Path = DEFAULT_DATA_QUALITY_PATH,
) -> DataQualityRegistry:
    json_path = Path(path)
    checks = json.loads(json_path.read_text(encoding="utf-8"))
    return DataQualityRegistry([DataQualityCheck.from_row(row) for row in checks])


def _check_matches_sql(check: DataQualityCheck, sql_tokens: set[str]) -> bool:
    if check.required_tokens:
        return check.required_tokens <= sql_tokens

    check_tokens = check.referenced_tokens
    if not check_tokens:
        return False

    # Require at least one table-like token and one field-like token from the
    # documented check. This keeps generic date or COUNT tokens from producing
    # broad caveats on unrelated queries.
    field_tokens = {
        token
        for token in check_tokens
        if token
        not in {
            "select",
            "count",
            "from",
            "where",
            "join",
            "left",
            "and",
            "or",
            "is",
            "not",
            "null",
            "as",
            "on",
            "group",
            "by",
            "order",
            "limit",
            "date",
            "values",
            "with",
        }
    }
    overlap = field_tokens & sql_tokens
    return len(overlap) >= 2


def _extract_sql_tokens(sql: str) -> set[str]:
    normalized = sql.replace('"', "").lower()
    return set(re.findall(r"\b[a-z_][a-z0-9_]*\b", normalized))
