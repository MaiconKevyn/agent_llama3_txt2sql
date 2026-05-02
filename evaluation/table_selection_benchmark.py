"""Utilities for the dedicated table-selection benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
DEFAULT_GOLD_PATH = ROOT / "table_selection_gold.json"


def load_table_selection_gold(path: str | Path = DEFAULT_GOLD_PATH) -> List[Dict[str, Any]]:
    """Load the table-selection gold dataset."""
    gold_path = Path(path)
    with gold_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def score_table_selection(
    selected_tables: List[str],
    gold_core_tables: List[str],
    gold_optional_tables: List[str] | None = None,
    gold_forbidden_tables: List[str] | None = None,
) -> Dict[str, Any]:
    """Score one predicted selection against the annotated gold tables."""
    predicted = list(dict.fromkeys(selected_tables))
    core = list(dict.fromkeys(gold_core_tables))
    optional = list(dict.fromkeys(gold_optional_tables or []))
    forbidden = list(dict.fromkeys(gold_forbidden_tables or []))

    predicted_set = set(predicted)
    core_set = set(core)
    optional_set = set(optional)
    forbidden_set = set(forbidden)
    allowed_set = core_set | optional_set

    missing_core = sorted(core_set - predicted_set)
    unexpected_tables = sorted(predicted_set - allowed_set)
    forbidden_selected = sorted(predicted_set & forbidden_set)

    core_recall = 1.0 if not core_set else (len(core_set & predicted_set) / len(core_set))
    allowed_precision = 0.0 if not predicted_set else (len(predicted_set & allowed_set) / len(predicted_set))
    exact_core_match = predicted_set == core_set
    acceptable = not missing_core and not unexpected_tables and not forbidden_selected

    return {
        "core_recall": round(core_recall, 4),
        "allowed_precision": round(allowed_precision, 4),
        "exact_core_match": exact_core_match,
        "acceptable": acceptable,
        "forbidden_hit": bool(forbidden_selected),
        "predicted_count": len(predicted),
        "missing_core": missing_core,
        "unexpected_tables": unexpected_tables,
        "forbidden_selected": forbidden_selected,
    }
