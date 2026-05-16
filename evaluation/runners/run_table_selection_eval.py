#!/usr/bin/env python3
"""Dedicated benchmark runner for the table-selection component."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Load .env before any env-guard checks
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from evaluation.table_selection.benchmark import (  # noqa: E402
    DEFAULT_GOLD_PATH,
    load_table_selection_gold,
    score_table_selection,
)
from src.agent.table_selection import select_tables_with_llamaindex  # noqa: E402
from src.application.config.table_descriptions import TABLE_DESCRIPTIONS  # noqa: E402

LLAMAINDEX_CONTEXT_MODE = "llamaindex_context"
DEFAULT_MODES = [
    LLAMAINDEX_CONTEXT_MODE,
]
_BLOCKED_RUNTIME_TABLE_PREFIXES = (
    "stg_",
    "source_",
    "relationships_",
    "not_null_",
    "accepted_values_",
    "dbt_",
)


@dataclass
class VariantSpec:
    id: str
    mode: str
    description_variant: str = "llamaindex"
    prompt_variant: str = "llamaindex"

    @property
    def name(self) -> str:
        return self.mode


def _build_variants(
    modes: List[str],
    description_variants: List[str],
    prompt_variants: List[str],
) -> List[VariantSpec]:
    variants: List[VariantSpec] = []
    counter = 0
    for mode in modes:
        if mode != LLAMAINDEX_CONTEXT_MODE:
            raise ValueError("Only llamaindex_context mode is supported")
        variants.append(VariantSpec(id=f"TS{counter:02d}", mode=mode))
        counter += 1
    return variants


def _available_tables() -> List[str]:
    metadata_path = ROOT / "docs" / "generated" / "table_metadata.csv"
    if metadata_path.exists():
        with open(metadata_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            table_names = {
                (row.get("table_name") or "").strip()
                for row in reader
                if (row.get("schema_name") or "").strip() in {"", "main"}
                and (row.get("table_name") or "").strip()
                and not (row.get("table_name") or "").strip().startswith(
                    _BLOCKED_RUNTIME_TABLE_PREFIXES
                )
            }
        if table_names:
            return sorted(table_names)

    return sorted(TABLE_DESCRIPTIONS.keys())


def _run_variant(
    spec: VariantSpec,
    dataset: List[Dict[str, Any]],
    available_tables: List[str],
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    detail_rows: List[Dict[str, Any]] = []
    if verbose:
        print(f"\n  ── {spec.id}: {spec.name} ──")

    for item in dataset:
        validated_tables, raw_tables, retrieved = select_tables_with_llamaindex(
            user_query=item["question"],
            available_tables=available_tables,
        )
        debug = {
            "stage_used": retrieved.retrieval_mode,
            "heuristic": {"selected_tables": [], "confidence": 0.0},
            "embedding": {"selected_tables": [], "confidence": 0.0},
            "llm": {
                "parsed_tables": retrieved.selected_tables,
                "raw_response": retrieved.schema_context,
            },
            "raw_selected_tables": raw_tables,
            "validated_selected_tables": validated_tables,
            "error": retrieved.error,
        }
        raw_score = score_table_selection(
            selected_tables=debug["raw_selected_tables"],
            gold_core_tables=item["gold_core_tables"],
            gold_optional_tables=item.get("gold_optional_tables", []),
            gold_forbidden_tables=item.get("gold_forbidden_tables", []),
        )
        validated_score = score_table_selection(
            selected_tables=debug["validated_selected_tables"],
            gold_core_tables=item["gold_core_tables"],
            gold_optional_tables=item.get("gold_optional_tables", []),
            gold_forbidden_tables=item.get("gold_forbidden_tables", []),
        )

        row = {
            "variant_id": spec.id,
            "variant_name": spec.name,
            "mode": spec.mode,
            "description_variant": spec.description_variant,
            "prompt_variant": spec.prompt_variant,
            "id": item["id"],
            "difficulty": item["difficulty"],
            "question": item["question"],
            "stage_used": debug["stage_used"],
            "heuristic_tables": json.dumps(debug["heuristic"]["selected_tables"], ensure_ascii=False),
            "heuristic_confidence": debug["heuristic"]["confidence"],
            "embedding_tables": json.dumps(debug["embedding"]["selected_tables"], ensure_ascii=False),
            "embedding_confidence": debug["embedding"]["confidence"],
            "llm_tables": json.dumps(debug["llm"]["parsed_tables"], ensure_ascii=False),
            "llm_raw_response": debug["llm"]["raw_response"],
            "raw_selected_tables": json.dumps(debug["raw_selected_tables"], ensure_ascii=False),
            "validated_selected_tables": json.dumps(debug["validated_selected_tables"], ensure_ascii=False),
            "gold_core_tables": json.dumps(item["gold_core_tables"], ensure_ascii=False),
            "gold_optional_tables": json.dumps(item.get("gold_optional_tables", []), ensure_ascii=False),
            "gold_forbidden_tables": json.dumps(item.get("gold_forbidden_tables", []), ensure_ascii=False),
            "raw_core_recall": raw_score["core_recall"],
            "raw_allowed_precision": raw_score["allowed_precision"],
            "raw_exact_core_match": raw_score["exact_core_match"],
            "raw_acceptable": raw_score["acceptable"],
            "raw_forbidden_hit": raw_score["forbidden_hit"],
            "raw_missing_core": json.dumps(raw_score["missing_core"], ensure_ascii=False),
            "raw_unexpected_tables": json.dumps(raw_score["unexpected_tables"], ensure_ascii=False),
            "raw_forbidden_selected": json.dumps(raw_score["forbidden_selected"], ensure_ascii=False),
            "validated_core_recall": validated_score["core_recall"],
            "validated_allowed_precision": validated_score["allowed_precision"],
            "validated_exact_core_match": validated_score["exact_core_match"],
            "validated_acceptable": validated_score["acceptable"],
            "validated_forbidden_hit": validated_score["forbidden_hit"],
            "validated_missing_core": json.dumps(validated_score["missing_core"], ensure_ascii=False),
            "validated_unexpected_tables": json.dumps(validated_score["unexpected_tables"], ensure_ascii=False),
            "validated_forbidden_selected": json.dumps(validated_score["forbidden_selected"], ensure_ascii=False),
            "error": debug["error"],
        }
        detail_rows.append(row)

        if verbose:
            status = "✓" if validated_score["acceptable"] else "✗"
            print(
                f"    {status} {item['id']}  stage={debug['stage_used']:<18} "
                f"selected={debug['validated_selected_tables']}"
            )

    return detail_rows


def _aggregate(detail_rows: List[Dict[str, Any]], spec: VariantSpec) -> Dict[str, Any]:
    n = len(detail_rows) or 1
    raw_acceptable = sum(1 for row in detail_rows if row["raw_acceptable"])
    validated_acceptable = sum(1 for row in detail_rows if row["validated_acceptable"])
    raw_exact = sum(1 for row in detail_rows if row["raw_exact_core_match"])
    validated_exact = sum(1 for row in detail_rows if row["validated_exact_core_match"])
    raw_forbidden = sum(1 for row in detail_rows if row["raw_forbidden_hit"])
    validated_forbidden = sum(1 for row in detail_rows if row["validated_forbidden_hit"])
    raw_core_recall = sum(float(row["raw_core_recall"]) for row in detail_rows) / n
    validated_core_recall = sum(float(row["validated_core_recall"]) for row in detail_rows) / n
    raw_precision = sum(float(row["raw_allowed_precision"]) for row in detail_rows) / n
    validated_precision = sum(float(row["validated_allowed_precision"]) for row in detail_rows) / n
    avg_selected = sum(len(json.loads(row["validated_selected_tables"])) for row in detail_rows) / n

    stage_counts: Dict[str, int] = {}
    for row in detail_rows:
        stage_counts[row["stage_used"]] = stage_counts.get(row["stage_used"], 0) + 1

    return {
        "variant_id": spec.id,
        "variant_name": spec.name,
        "mode": spec.mode,
        "description_variant": spec.description_variant,
        "prompt_variant": spec.prompt_variant,
        "n_queries": len(detail_rows),
        "raw_acceptable_rate": round(raw_acceptable / n, 4),
        "validated_acceptable_rate": round(validated_acceptable / n, 4),
        "raw_exact_core_match_rate": round(raw_exact / n, 4),
        "validated_exact_core_match_rate": round(validated_exact / n, 4),
        "raw_avg_core_recall": round(raw_core_recall, 4),
        "validated_avg_core_recall": round(validated_core_recall, 4),
        "raw_avg_allowed_precision": round(raw_precision, 4),
        "validated_avg_allowed_precision": round(validated_precision, 4),
        "raw_forbidden_hit_rate": round(raw_forbidden / n, 4),
        "validated_forbidden_hit_rate": round(validated_forbidden / n, 4),
        "avg_selected_tables": round(avg_selected, 2),
        "stage_counts": json.dumps(stage_counts, ensure_ascii=False, sort_keys=True),
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_report(path: Path, summary_rows: List[Dict[str, Any]], detail_rows: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append("# Table Selection Benchmark Report")
    lines.append("")
    lines.append(f"- **Date**: {datetime.now(UTC).isoformat()}")
    lines.append(f"- **Queries per variant**: {len({row['id'] for row in detail_rows})}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| ID | Variant | Raw Acceptable | Validated Acceptable | Raw Core Recall | Validated Core Recall | Raw Precision | Validated Precision | Avg Selected |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in summary_rows:
        lines.append(
            f"| {row['variant_id']} | {row['variant_name']} | "
            f"{row['raw_acceptable_rate'] * 100:.1f}% | {row['validated_acceptable_rate'] * 100:.1f}% | "
            f"{row['raw_avg_core_recall'] * 100:.1f}% | {row['validated_avg_core_recall'] * 100:.1f}% | "
            f"{row['raw_avg_allowed_precision'] * 100:.1f}% | {row['validated_avg_allowed_precision'] * 100:.1f}% | "
            f"{row['avg_selected_tables']:.2f} |"
        )

    lines.append("")
    lines.append("## Failure Samples")
    lines.append("")

    detail_by_variant: Dict[str, List[Dict[str, Any]]] = {}
    for row in detail_rows:
        detail_by_variant.setdefault(row["variant_id"], []).append(row)

    for summary in summary_rows:
        failures = [row for row in detail_by_variant[summary["variant_id"]] if not row["validated_acceptable"]]
        if not failures:
            continue
        lines.append(f"### {summary['variant_id']} {summary['variant_name']}")
        lines.append("")
        for row in failures[:5]:
            lines.append(
                f"- `{row['id']}` stage=`{row['stage_used']}` "
                f"selected={row['validated_selected_tables']} "
                f"raw_ok={row['raw_acceptable']} validated_ok={row['validated_acceptable']} "
                f"missing={row['validated_missing_core']} unexpected={row['validated_unexpected_tables']} "
                f"forbidden={row['validated_forbidden_selected']}"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dedicated table-selection benchmark")
    parser.add_argument("--gold", type=str, default=str(DEFAULT_GOLD_PATH))
    parser.add_argument("--modes", nargs="+", default=DEFAULT_MODES)
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    dataset = load_table_selection_gold(args.gold)
    if args.max_queries:
        dataset = dataset[: args.max_queries]

    output_dir = Path(
        args.output
        or ROOT
        / "evaluation"
        / "table_selection"
        / "results"
        / f"table_selection_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = _build_variants(args.modes, [], [])

    available_tables = _available_tables()
    summary_rows: List[Dict[str, Any]] = []
    detail_rows: List[Dict[str, Any]] = []

    for spec in variants:
        rows = _run_variant(
            spec=spec,
            dataset=dataset,
            available_tables=available_tables,
            verbose=not args.quiet,
        )
        detail_rows.extend(rows)
        summary_rows.append(_aggregate(rows, spec))

    summary_rows.sort(
        key=lambda row: (
            -row["validated_acceptable_rate"],
            -row["validated_avg_core_recall"],
            row["variant_id"],
        )
    )

    _write_csv(output_dir / "results.csv", summary_rows)
    _write_csv(output_dir / "results_detail.csv", detail_rows)
    _write_report(output_dir / "report.md", summary_rows, detail_rows)

    if not args.quiet:
        print(f"\nResults written to {output_dir}")


if __name__ == "__main__":
    main()
