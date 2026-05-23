"""Question models and local judges for generalization exhaustion runs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ExpectedBehavior = Literal[
    "answer_with_sql",
    "safe_refusal",
    "requires_clarification",
    "answer_with_analytic_template",
]


class GeneralizationQuestion(BaseModel):
    id: str
    persona: str
    category: str
    difficulty: Literal["easy", "medium", "hard"]
    question: str
    expected_behavior: ExpectedBehavior
    expected_tables: list[str] = Field(default_factory=list)
    reference_sql: str | None = None
    judge: dict[str, Any]
    schema_basis: list[str] = Field(default_factory=list)
    anti_overfit_family: str
    expected_caveats: list[str] = Field(default_factory=list)
    max_latency_seconds: float | None = None

    @model_validator(mode="after")
    def validate_sql_policy(self) -> GeneralizationQuestion:
        if self.expected_behavior == "answer_with_sql" and not self.reference_sql:
            raise ValueError(f"{self.id} expects SQL but has no reference_sql")
        if (
            self.expected_behavior in {"safe_refusal", "requires_clarification"}
            and self.reference_sql
        ):
            raise ValueError(f"{self.id} is {self.expected_behavior} but has reference_sql")
        return self


def load_generalization_questions(path: Path | None = None) -> list[GeneralizationQuestion]:
    path = path or Path(__file__).with_name("generalization_questions.jsonl")
    questions: list[GeneralizationQuestion] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            questions.append(GeneralizationQuestion.model_validate_json(line))
        except Exception as exc:
            raise ValueError(
                f"Invalid generalization question at {path}:{line_number}: {exc}"
            ) from exc
    return questions


def load_benchmark_questions(path: Path) -> list[GeneralizationQuestion]:
    """Load a benchmark directory or file, resolving source_id refs to the main corpus."""

    base_by_id = {question.id: question for question in load_generalization_questions()}
    records: list[dict[str, Any]] = []
    files = sorted(path.glob("*.json*")) if path.is_dir() else [path]
    for file_path in files:
        records.extend(_load_benchmark_records(file_path))

    questions: list[GeneralizationQuestion] = []
    for record in records:
        source_id = record.pop("source_id", None)
        if source_id:
            if source_id not in base_by_id:
                raise ValueError(f"Unknown benchmark source_id: {source_id}")
            source = base_by_id[source_id]
            update = {key: value for key, value in record.items() if value is not None}
            update.setdefault("id", source.id)
            questions.append(source.model_copy(update=update))
        else:
            questions.append(GeneralizationQuestion.model_validate(record))
    return questions


def _load_benchmark_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        return payload["cases"]
    raise ValueError(f"Unsupported benchmark file shape: {path}")


def _normalize_text(value: str) -> str:
    translation = str.maketrans(
        {
            "ã": "a",
            "á": "a",
            "à": "a",
            "â": "a",
            "é": "e",
            "ê": "e",
            "í": "i",
            "ó": "o",
            "ô": "o",
            "õ": "o",
            "ú": "u",
            "ç": "c",
        }
    )
    return value.lower().translate(translation)


def judge_safe_refusal(*, response: str, judge: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_text(response or "")
    missing: list[str] = []
    for token in judge.get("must_mention", []):
        if _normalize_text(str(token)) not in normalized:
            missing.append(f"missing_token:{token}")

    if judge.get("must_not_claim_numeric_answer") and _claims_numeric_answer(normalized):
        missing.append("numeric_claim_for_unsupported_schema")
    return {"passed": not missing, "missing": missing}


def score_numeric_equivalence(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    *,
    required_columns: list[str],
    tolerance: float,
    column_aliases: dict[str, list[str]] | None = None,
    order_sensitive: bool = False,
) -> dict[str, Any]:
    missing: list[str] = []
    column_aliases = _merged_column_aliases(column_aliases or {})
    expected_rows = _project_rows(
        expected_rows, required_columns, column_aliases, missing, "expected"
    )
    actual_rows = _project_rows(actual_rows, required_columns, column_aliases, missing, "actual")
    if len(expected_rows) != len(actual_rows):
        missing.append(f"row_count:{len(actual_rows)}!={len(expected_rows)}")
    if missing:
        return {"passed": False, "missing": _unique(missing)}

    if not order_sensitive:
        expected_rows, actual_rows = _sort_rows_for_equivalence(
            expected_rows, actual_rows, required_columns
        )

    if _has_only_arbitrary_label_differences_for_tied_metrics(
        expected_rows, actual_rows, required_columns, tolerance
    ):
        return {"passed": True, "missing": []}

    for index, (expected, actual) in enumerate(zip(expected_rows, actual_rows, strict=False)):
        for column in required_columns:
            expected_value = expected.get(column)
            actual_value = actual.get(column)
            if _is_number(expected_value) and _is_number(actual_value):
                if abs(float(expected_value) - float(actual_value)) > tolerance:
                    missing.append(f"value_mismatch:{index}:{column}")
            elif str(expected_value) != str(actual_value):
                missing.append(f"value_mismatch:{index}:{column}")
    return {"passed": not missing, "missing": _unique(missing)}


def _has_only_arbitrary_label_differences_for_tied_metrics(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    required_columns: list[str],
    tolerance: float,
) -> bool:
    if len(required_columns) < 2 or not expected_rows or not actual_rows:
        return False
    numeric_columns = [
        column
        for column in required_columns
        if all(_is_number(row.get(column)) for row in expected_rows + actual_rows)
    ]
    label_columns = [column for column in required_columns if column not in numeric_columns]
    if not numeric_columns or not label_columns:
        return False
    for column in numeric_columns:
        values = [float(row[column]) for row in expected_rows + actual_rows]
        if max(values) - min(values) > tolerance:
            return False
    return True


def _claims_numeric_answer(normalized_response: str) -> bool:
    has_number = bool(re.search(r"\b\d+(?:[.,]\d+)?\b", normalized_response))
    if not has_number:
        return False
    answer_verbs = [
        "foram encontrados",
        "foram registrad",
        "total",
        "taxa",
        "percentual",
        "cobertura",
        "resultado",
    ]
    return any(token in normalized_response for token in answer_verbs)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _merged_column_aliases(overrides: dict[str, list[str]]) -> dict[str, list[str]]:
    aliases = {
        "uf": ["uf_residencia", "estado_residencia", "estado"],
        "uf_residencia": ["uf", "estado_residencia", "estado"],
        "estado_residencia": ["uf", "uf_residencia", "estado"],
        "municipio_residencia": ["municipio"],
        "municipio": ["municipio_residencia"],
        "total_internacoes": ["total", "internacoes", "qtd_internacoes", "quantidade"],
        "total": ["total_internacoes", "internacoes", "qtd_internacoes", "quantidade"],
        "total_procedimentos": ["total_internacoes", "total", "quantidade"],
        "total_obitos": ["total_mortes", "obitos", "mortes"],
        "total_mortes": ["total_obitos", "obitos", "mortes"],
        "valor_indicador": ["leitos_sus_1000", "medicos_1000", "indicador"],
        "taxa_por_100k": ["taxa_internacoes_por_100_mil", "taxa_100k"],
        "taxa_mortalidade_percentual": [
            "taxa_mortalidade",
            "taxa_obitos",
            "mortalidade_percentual",
        ],
        "taxa_mortalidade": [
            "taxa_mortalidade_percentual",
            "taxa_obitos",
            "mortalidade_percentual",
        ],
        "capitulo_cid": ["cid_capitulo"],
        "cid_capitulo": ["capitulo_cid"],
    }
    for canonical, custom_aliases in overrides.items():
        aliases.setdefault(canonical, [])
        aliases[canonical].extend(custom_aliases)
    return aliases


def _project_rows(
    rows: list[dict[str, Any]],
    required_columns: list[str],
    column_aliases: dict[str, list[str]],
    missing: list[str],
    prefix: str,
) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for row in rows:
        projected_row: dict[str, Any] = {}
        for column in required_columns:
            source_column = _find_column(row, column, column_aliases)
            if source_column is None:
                missing_prefix = (
                    "expected_missing_column" if prefix == "expected" else "missing_column"
                )
                missing.append(f"{missing_prefix}:{column}")
                continue
            projected_row[column] = row[source_column]
        projected.append(projected_row)
    return projected


def _find_column(
    row: dict[str, Any],
    required_column: str,
    column_aliases: dict[str, list[str]],
) -> str | None:
    if required_column in row:
        return required_column
    for alias in column_aliases.get(required_column, []):
        if alias in row:
            return alias
    return None


def _sort_rows_for_equivalence(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    required_columns: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not required_columns or not expected_rows or not actual_rows:
        return expected_rows, actual_rows
    key_column = required_columns[0]
    if _is_number(expected_rows[0].get(key_column)) or _is_number(actual_rows[0].get(key_column)):
        return expected_rows, actual_rows
    return (
        sorted(expected_rows, key=lambda row: str(row.get(key_column))),
        sorted(actual_rows, key=lambda row: str(row.get(key_column))),
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
