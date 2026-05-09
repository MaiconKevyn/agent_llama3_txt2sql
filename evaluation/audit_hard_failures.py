"""Audit hard Text-to-SQL failures by executing gold and generated SQL.

This script is intentionally evaluation-oriented: it does not call the agent or
an LLM. It reads an ablation result file plus the ground-truth dataset, executes
the gold and generated SQL against the configured database, and writes a compact
JSON/Markdown report that separates semantic failures from execution/evaluation
artifacts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text

from src.agent.llm_manager import OpenAILLMManager
from src.application.config.simple_config import ApplicationConfig
from src.utils.sql_safety import sanitize_sql_for_execution

DEFAULT_DATASET = Path("evaluation/ground_truth_v2.json")
DEFAULT_ABLATION = Path("evaluation/ablation/results/ablation_ground_truth_v2/V0_full_pipeline.json")
DEFAULT_OUTPUT_DIR = Path("evaluation/ablation/results/hard_h1_audit")


@dataclass
class QueryExecution:
    success: bool
    row_count: int
    sample: list[list[Any]]
    error: str | None = None


@dataclass
class HardFailureAudit:
    query_id: str
    question: str
    ablation_gold_row_count: int | None
    ablation_predicted_row_count: int | None
    direct_gold: QueryExecution
    direct_predicted: QueryExecution | None
    classification: str
    notes: str


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _execute_sql(engine: Any, sql: str, *, sample_limit: int) -> QueryExecution:
    if not sql.strip():
        return QueryExecution(
            success=False,
            row_count=0,
            sample=[],
            error="missing_sql",
        )
    try:
        cleaned = sanitize_sql_for_execution(sql)
        with engine.connect() as conn:
            result = conn.execute(text(cleaned))
            rows = result.fetchall()
        sample = [list(row) for row in rows[:sample_limit]]
        return QueryExecution(success=True, row_count=len(rows), sample=sample)
    except Exception as exc:
        return QueryExecution(
            success=False,
            row_count=0,
            sample=[],
            error=str(exc),
        )


def _classify(
    result: dict[str, Any],
    direct_gold: QueryExecution,
    direct_predicted: QueryExecution | None,
) -> tuple[str, str]:
    ablation_gold_count = result.get("gold_row_count")
    ablation_predicted_count = result.get("predicted_row_count")
    generated_sql = result.get("generated_sql") or ""

    if not direct_gold.success:
        return "ground_truth_or_runtime_error", "gold SQL failed direct execution"
    if ablation_gold_count == 0 and direct_gold.row_count > 0:
        if direct_predicted is not None and not direct_predicted.success:
            return (
                "evaluation_artifact_and_agent_sql_error",
                "ablation recorded zero gold rows, but direct gold execution returned rows; generated SQL failed direct execution",
            )
        return "evaluation_artifact", "ablation recorded zero gold rows, but direct gold execution returned rows"
    if not generated_sql.strip():
        return "agent_generation_or_validation_failure", "ablation produced no generated SQL"
    if direct_predicted is not None and not direct_predicted.success:
        return "agent_sql_execution_error", "generated SQL failed direct execution"
    if (
        direct_predicted is not None
        and ablation_predicted_count == 0
        and direct_predicted.row_count > 0
    ):
        return (
            "evaluation_artifact",
            "ablation recorded zero predicted rows, but direct generated SQL execution returned rows",
        )
    return "semantic_mismatch", "gold and generated SQL execute, but EX failed"


def audit_hard_failures(
    *,
    dataset_path: Path,
    ablation_path: Path,
    sample_limit: int,
) -> list[HardFailureAudit]:
    load_dotenv(".env")
    manager = OpenAILLMManager(ApplicationConfig())
    engine = manager.get_database()._engine

    dataset = _load_json(dataset_path)
    gold_by_id = {item["id"]: item for item in dataset}

    ablation = _load_json(ablation_path)
    failed_hard = [
        item
        for item in ablation.get("queries", [])
        if item.get("difficulty") == "hard" and item.get("ex") is False
    ]

    audits: list[HardFailureAudit] = []
    for result in failed_hard:
        query_id = result["id"]
        gold_item = gold_by_id[query_id]
        direct_gold = _execute_sql(engine, gold_item["query"], sample_limit=sample_limit)
        generated_sql = result.get("generated_sql") or ""
        direct_predicted = (
            _execute_sql(engine, generated_sql, sample_limit=sample_limit)
            if generated_sql.strip()
            else None
        )
        classification, notes = _classify(result, direct_gold, direct_predicted)
        audits.append(
            HardFailureAudit(
                query_id=query_id,
                question=result.get("question") or gold_item["question"],
                ablation_gold_row_count=result.get("gold_row_count"),
                ablation_predicted_row_count=result.get("predicted_row_count"),
                direct_gold=direct_gold,
                direct_predicted=direct_predicted,
                classification=classification,
                notes=notes,
            )
        )
    return audits


def _write_outputs(audits: list[HardFailureAudit], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = [asdict(audit) for audit in audits]
    (output_dir / "hard_h1_audit.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Hard H1 Audit",
        "",
        "| ID | Classification | Ablation Rows | Direct Rows | Notes |",
        "|---|---|---:|---:|---|",
    ]
    for audit in audits:
        predicted_count = audit.direct_predicted.row_count if audit.direct_predicted else 0
        ablation_rows = (
            f"{audit.ablation_gold_row_count}/{audit.ablation_predicted_row_count}"
        )
        direct_rows = f"{audit.direct_gold.row_count}/{predicted_count}"
        lines.append(
            "| "
            + " | ".join(
                [
                    audit.query_id,
                    audit.classification,
                    ablation_rows,
                    direct_rows,
                    audit.notes.replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Legend:",
            "",
            "- `Ablation Rows`: gold/predicted row counts recorded by the ablation artifact.",
            "- `Direct Rows`: gold/predicted row counts from direct execution in this audit.",
        ]
    )
    (output_dir / "hard_h1_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit hard ablation failures.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--ablation", type=Path, default=DEFAULT_ABLATION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sample-limit", type=int, default=5)
    args = parser.parse_args()

    audits = audit_hard_failures(
        dataset_path=args.dataset,
        ablation_path=args.ablation,
        sample_limit=args.sample_limit,
    )
    _write_outputs(audits, args.output_dir)
    print(f"Wrote {len(audits)} audits to {args.output_dir}")


if __name__ == "__main__":
    main()
