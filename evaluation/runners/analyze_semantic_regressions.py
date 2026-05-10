"""Analyze ablation rows where semantic validation likely degraded results.

The script compares a full-pipeline variant against a variant with semantic plan
validation disabled and writes an audit CSV. It is intentionally benchmark-id
agnostic: query IDs are only identifiers for reporting, while categorization is
based on result shape and recorded semantic metadata.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

FIELDS = [
    "id",
    "difficulty",
    "question",
    "category",
    "baseline_ex",
    "comparison_ex",
    "baseline_rows",
    "comparison_rows",
    "semantic_validation_message",
    "semantic_error_category",
    "repair_attempt_count",
    "baseline_sql",
    "comparison_sql",
]


def _load_variant(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = payload.get("queries", [])
    if not isinstance(queries, list):
        raise ValueError(f"Variant file does not contain a query list: {path}")
    return queries


def _json_field(row: dict[str, Any], key: str, default: Any) -> Any:
    raw = row.get(key)
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _repair_attempt_count(row: dict[str, Any]) -> int:
    attempts = _json_field(row, "repair_attempts", [])
    return len(attempts) if isinstance(attempts, list) else 0


def _semantic_validation_message(row: dict[str, Any]) -> str:
    semantic_validation = _json_field(row, "semantic_validation", {})
    if isinstance(semantic_validation, dict):
        return str(semantic_validation.get("message") or "")
    return ""


def _semantic_error_category(row: dict[str, Any]) -> str:
    semantic_error = _json_field(row, "semantic_error", {})
    if isinstance(semantic_error, dict):
        return str(semantic_error.get("category") or "")
    return ""


def _categorize(baseline: dict[str, Any], comparison: dict[str, Any]) -> str:
    baseline_sql = str(baseline.get("generated_sql") or "")
    baseline_rows = int(baseline.get("predicted_row_count") or 0)
    gold_rows = int(baseline.get("gold_row_count") or 0)
    message = _semantic_validation_message(baseline).lower()
    semantic_category = _semantic_error_category(baseline)

    if gold_rows == 1 and baseline_rows > 1 and re.search(r"\bgroup\s+by\b", baseline_sql, re.I):
        return "scalar_grouped_table"
    if "single scalar" in message or "group by" in message:
        return "answer_shape_validation"
    if semantic_category:
        return f"semantic_{semantic_category}"
    if _repair_attempt_count(baseline):
        return "repair_changed_sql"
    if baseline.get("generated_sql") and comparison.get("generated_sql"):
        return "semantic_validation_degradation_candidate"
    return "unknown"


def build_report(
    output_dir: Path,
    *,
    baseline_variant: str = "V0_full_pipeline.json",
    comparison_variant: str = "V10_no_semantic_plan_validation.json",
) -> list[dict[str, Any]]:
    baseline_rows = _load_variant(output_dir / baseline_variant)
    comparison_rows = _load_variant(output_dir / comparison_variant)
    comparison_by_id = {row["id"]: row for row in comparison_rows}

    report_rows: list[dict[str, Any]] = []
    for baseline in baseline_rows:
        comparison = comparison_by_id.get(baseline["id"])
        if comparison is None:
            continue
        if baseline.get("ex") or not comparison.get("ex"):
            continue
        report_rows.append(
            {
                "id": baseline["id"],
                "difficulty": baseline["difficulty"],
                "question": baseline["question"],
                "category": _categorize(baseline, comparison),
                "baseline_ex": baseline.get("ex"),
                "comparison_ex": comparison.get("ex"),
                "baseline_rows": baseline.get("predicted_row_count"),
                "comparison_rows": comparison.get("predicted_row_count"),
                "semantic_validation_message": _semantic_validation_message(baseline),
                "semantic_error_category": _semantic_error_category(baseline),
                "repair_attempt_count": _repair_attempt_count(baseline),
                "baseline_sql": baseline.get("generated_sql", ""),
                "comparison_sql": comparison.get("generated_sql", ""),
            }
        )
    return report_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze semantic validation ablation regressions.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV path. Default: <output_dir>/semantic_validation_regressions.csv",
    )
    args = parser.parse_args()

    rows = build_report(args.output_dir)
    output = args.output or args.output_dir / "semantic_validation_regressions.csv"
    write_csv(output, rows)
    print(f"Wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
