"""Result-set normalization helpers for evaluation runners."""

from __future__ import annotations

import ast
from decimal import Decimal
from typing import Any

from evaluation.metrics.execution_accuracy import ExecutionAccuracyMetric


def _literal_eval(raw: str) -> Any:
    try:
        return ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return raw


def _coerce_result_value(value: Any) -> list[tuple]:
    """Coerce a single runner result cell/value into one or more result rows."""
    if value is None:
        return []

    if isinstance(value, str):
        parsed = _literal_eval(value.strip())
        if parsed is value:
            return [(value,)]
        return _coerce_rows(parsed)

    if isinstance(value, tuple):
        return [value]

    if isinstance(value, list):
        if value and all(isinstance(item, (dict, list, tuple)) for item in value):
            return _coerce_rows(value)
        return [tuple(value)]

    if isinstance(value, dict):
        if "result" in value:
            return _coerce_result_value(value["result"])
        return [tuple(value.values())]

    return [(value,)]


def _coerce_rows(raw: Any) -> list[tuple]:
    """Coerce supported DB/tool/agent outputs into rows accepted by EX metric."""
    if raw is None:
        return []

    if isinstance(raw, str):
        parsed = _literal_eval(raw.strip())
        if parsed is raw:
            return [(raw,)]
        return _coerce_rows(parsed)

    if isinstance(raw, tuple):
        return [raw]

    if isinstance(raw, list):
        rows: list[tuple] = []
        for item in raw:
            rows.extend(_coerce_result_value(item))
        return rows

    if isinstance(raw, dict):
        return _coerce_result_value(raw)

    return [(raw,)]


def _json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def compare_results(agent_rows: Any, gold_raw: Any, sample_size: int = 5) -> dict[str, Any]:
    """Compare agent and gold outputs and return audit-friendly EX details."""
    if gold_raw is None or str(gold_raw).startswith("__GOLD_ERROR__"):
        return {
            "match": False,
            "gold_row_count": 0,
            "predicted_row_count": 0,
            "gold_rows_sample": [],
            "predicted_rows_sample": _json_safe(_coerce_rows(agent_rows)[:sample_size]),
            "details": {"reason": "gold_execution_failed", "gold_raw": str(gold_raw)},
        }

    gold_rows = _coerce_rows(gold_raw)
    predicted_rows = _coerce_rows(agent_rows)
    metric = ExecutionAccuracyMetric()
    match, details = metric._compare_results(gold_rows, predicted_rows)

    return {
        "match": match,
        "gold_row_count": len(gold_rows),
        "predicted_row_count": len(predicted_rows),
        "gold_rows_sample": _json_safe(gold_rows[:sample_size]),
        "predicted_rows_sample": _json_safe(predicted_rows[:sample_size]),
        "details": _json_safe(details),
    }


def results_match(agent_rows: Any, gold_raw: Any) -> bool:
    """Compare agent and gold results using the project's structured EX logic."""
    return bool(compare_results(agent_rows, gold_raw)["match"])
