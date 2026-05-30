"""Normalized evaluation suite loading.

This module keeps benchmark/evaluation data out of runtime code while giving
tests and runners a stable contract for smoke, regression, and holdout suites.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SuiteName = Literal["dev_smoke", "regression_failure_focused", "holdout_generalization"]
ExpectedBehavior = Literal["answer_with_sql", "safe_refusal", "requires_clarification"]

ROOT = Path(__file__).resolve().parents[1]

SUITE_FILES: dict[SuiteName, Path] = {
    "dev_smoke": ROOT / "evaluation" / "dev_smoke.json",
    "regression_failure_focused": ROOT / "evaluation" / "regression_set.json",
    "holdout_generalization": ROOT / "evaluation" / "holdout_generalization.json",
}


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    suite: SuiteName
    family: str
    difficulty: str
    question: str
    expected_behavior: ExpectedBehavior
    expected_tables: tuple[str, ...]
    gold_sql: str | None = None
    notes: str | None = None
    source_path: str | None = None


def load_evaluation_suite(suite: SuiteName) -> list[EvaluationCase]:
    path = SUITE_FILES[suite]
    records = json.loads(path.read_text(encoding="utf-8"))
    cases = [_normalize_case(suite, path, record) for record in records]
    _validate_suite(cases, path)
    return cases


def load_all_evaluation_suites() -> dict[SuiteName, list[EvaluationCase]]:
    return {suite: load_evaluation_suite(suite) for suite in SUITE_FILES}


def _normalize_case(suite: SuiteName, path: Path, record: dict[str, Any]) -> EvaluationCase:
    if suite == "regression_failure_focused":
        gold_sql = record.get("query")
        expected_tables = tuple(record.get("tables") or [])
    else:
        gold_sql = record.get("gold_sql") or record.get("reference_sql")
        expected_tables = tuple(record.get("expected_tables") or [])

    expected_behavior = record.get("expected_behavior")
    if expected_behavior is None:
        expected_behavior = _behavior_from_route(record.get("expected_route"), gold_sql)

    return EvaluationCase(
        id=str(record["id"]),
        suite=suite,
        family=str(record.get("family") or _infer_family(record)),
        difficulty=str(record.get("difficulty") or "medium"),
        question=str(record["question"]),
        expected_behavior=expected_behavior,
        expected_tables=expected_tables,
        gold_sql=gold_sql,
        notes=record.get("notes"),
        source_path=f"{path.as_posix()}#{record['id']}",
    )


def _behavior_from_route(route: str | None, gold_sql: str | None) -> ExpectedBehavior:
    if route == "schema_unavailable":
        return "safe_refusal"
    if route == "clarification":
        return "requires_clarification"
    return "answer_with_sql" if gold_sql else "safe_refusal"


def _infer_family(record: dict[str, Any]) -> str:
    text = " ".join(
        str(record.get(key) or "").lower()
        for key in ("question", "notes", "selection_reason")
    )
    rules = [
        ("schema_unavailable", ["schema", "hemograma", "medicamento", "bairro"]),
        ("diagnosticos_cid", ["cid", "diag", "pneumonia", "diabetes", "infarto"]),
        ("procedimentos", ["procedimento", "proc_rea"]),
        ("custos_permanencia", ["valor", "custo", "permanencia", "dias_perm"]),
        ("socioeconomico", ["pib", "populacao", "idhm", "socioeconomico"]),
        ("geografia", ["municipio", "uf", "estado"]),
        ("mortalidade", ["morte", "obito", "mortalidade"]),
        ("qualidade_dados", ["nulo", "sem catalogo", "qualidade"]),
        ("volume_temporal", ["ano", "mes", "periodo", "temporal"]),
    ]
    for family, tokens in rules:
        if any(token in text for token in tokens):
            return family
    return "general"


def _validate_suite(cases: list[EvaluationCase], path: Path) -> None:
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate case ids in {path}")
    missing = [
        case.id
        for case in cases
        if not case.family
        or not case.difficulty
        or not case.question.strip()
        or not case.expected_behavior
        or (
            case.expected_behavior == "answer_with_sql"
            and (not case.expected_tables or not case.gold_sql)
        )
    ]
    if missing:
        raise ValueError(f"Invalid evaluation case contract in {path}: {missing}")
