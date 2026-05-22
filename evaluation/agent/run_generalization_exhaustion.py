"""Run or dry-run the agent generalization exhaustion set."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from evaluation.agent.analytic_rubric import score_analytic_response
from evaluation.agent.generalization_rubric import (
    dump_json,
    judge_safe_refusal,
    load_generalization_questions,
)


def summarize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status_counts": dict(Counter(item.get("status") for item in items)),
        "root_cause_counts": dict(
            Counter(item.get("root_cause") for item in items if item.get("root_cause"))
        ),
        "severity_counts": dict(
            Counter(item.get("severity") for item in items if item.get("severity"))
        ),
    }


def classify_failure(item: dict[str, Any]) -> tuple[str | None, str | None]:
    if item.get("status") == "passed":
        return None, None

    response = str(item.get("response") or "").lower()
    error = str(item.get("error") or "").lower()
    sql = str(item.get("sql") or "").lower()
    question = str(item.get("question") or "").lower()
    expected_behavior = item.get("expected_behavior")

    if expected_behavior == "safe_refusal" and any(
        token in response for token in ["0 ", "zero", "foram encontrados"]
    ):
        return "unsupported_schema_detection", "critical"
    if "binder error" in error or "does not exist" in error:
        return "sql_execution_error", "high"
    if "populacao" in sql and "join internacoes" in sql:
        return "denominator_error", "high"
    if "cid_morte" in sql and "causa" in question:
        return "clinical_concept_resolution", "high"
    return "response_grounding_error", "medium"


def evaluate_response(
    question: Any,
    result: dict[str, Any],
    *,
    sql_executor: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    response = result.get("response") or result.get("final_response") or ""
    sql = result.get("sql_query") or result.get("generated_sql") or ""
    metadata = result.get("metadata") or {}

    if question.expected_behavior == "safe_refusal":
        judgement = judge_safe_refusal(response=response, judge=question.judge)
        return {"passed": judgement["passed"], "judge": judgement}

    if question.expected_behavior == "answer_with_analytic_template":
        score = score_analytic_response(
            question=question.question,
            response=response,
            sql=sql,
            semantic_plan=metadata.get("semantic_plan") or {},
        )
        return {"passed": score.score >= 0.85 and not score.missing, "judge": score.model_dump()}

    if question.expected_behavior == "answer_with_sql":
        if sql_executor is None:
            return {
                "passed": bool(result.get("success")) and bool(response),
                "judge": {"type": "needs_reference_sql_execution"},
            }
        if not sql:
            return {
                "passed": False,
                "judge": {"type": "result_equivalence", "missing": ["missing_agent_sql"]},
            }
        try:
            expected_rows = sql_executor(question.reference_sql)
            actual_rows = sql_executor(sql)
        except Exception as exc:
            return {
                "passed": False,
                "judge": {
                    "type": "result_equivalence",
                    "missing": ["sql_execution_error"],
                    "error": f"{type(exc).__name__}: {exc}",
                },
            }
        judge_config = question.judge
        from evaluation.agent.generalization_rubric import score_numeric_equivalence

        comparison = score_numeric_equivalence(
            expected_rows,
            actual_rows,
            required_columns=list(judge_config.get("required_columns") or []),
            tolerance=float(judge_config.get("tolerance") or 0.0),
            column_aliases=judge_config.get("column_aliases") or {},
            order_sensitive=bool(judge_config.get("order_sensitive", False)),
        )
        comparison["type"] = "result_equivalence"
        comparison["expected_preview"] = expected_rows[:5]
        comparison["actual_preview"] = actual_rows[:5]
        return {"passed": comparison["passed"], "judge": comparison}

    return {
        "passed": bool(result.get("success")) and bool(response),
        "judge": {"type": "needs_reference_sql_execution"},
    }


def select_questions(
    *,
    limit: int | None,
    offset: int,
    category: str | None,
    behavior: str | None,
    ids: list[str] | None,
) -> list[Any]:
    questions = load_generalization_questions()
    if ids:
        wanted = set(ids)
        questions = [item for item in questions if item.id in wanted]
        missing = wanted - {item.id for item in questions}
        if missing:
            raise ValueError(f"Unknown generalization question ids: {sorted(missing)}")
    if category:
        questions = [item for item in questions if item.category == category]
    if behavior:
        questions = [item for item in questions if item.expected_behavior == behavior]
    if offset:
        questions = questions[offset:]
    return questions[:limit] if limit else questions


def run_items(
    *,
    run_id: str,
    limit: int | None,
    offset: int = 0,
    category: str | None = None,
    behavior: str | None = None,
    ids: list[str] | None = None,
    dry_run: bool,
) -> list[dict[str, Any]]:
    selected = select_questions(
        limit=limit,
        offset=offset,
        category=category,
        behavior=behavior,
        ids=ids,
    )
    if dry_run:
        return [
            {
                "id": item.id,
                "question": item.question,
                "expected_behavior": item.expected_behavior,
                "anti_overfit_family": item.anti_overfit_family,
                "status": "dry_run",
                "root_cause": None,
                "severity": None,
            }
            for item in selected
        ]

    from src.agent.orchestrator import LangGraphOrchestrator
    from src.application.config.simple_config import ApplicationConfig, OrchestratorConfig

    load_dotenv(".env")
    db_url = ApplicationConfig().database_path
    if not db_url:
        raise ValueError("DATABASE_URL or DATABASE_PATH is required for live generalization runs")
    sql_executor = build_sql_executor(db_url)
    orchestrator = LangGraphOrchestrator(
        orchestrator_config=OrchestratorConfig(
            enable_llamaindex_context=True,
            llamaindex_mode="context",
        ),
        environment="testing",
    )

    results: list[dict[str, Any]] = []
    for item in selected:
        raw = orchestrator.process_query(
            item.question,
            session_id=f"{run_id}_{item.id.lower()}",
            force_single_query=True,
        )
        judgement = evaluate_response(item, raw, sql_executor=sql_executor)
        output = {
            "id": item.id,
            "persona": item.persona,
            "category": item.category,
            "difficulty": item.difficulty,
            "question": item.question,
            "expected_behavior": item.expected_behavior,
            "anti_overfit_family": item.anti_overfit_family,
            "status": "passed" if judgement["passed"] else "failed",
            "judge": judgement["judge"],
            "success": raw.get("success"),
            "response": raw.get("response") or raw.get("final_response"),
            "sql": raw.get("sql_query") or raw.get("generated_sql"),
            "metadata": raw.get("metadata") or {},
            "error": raw.get("error_message") or raw.get("error"),
        }
        root_cause, severity = classify_failure(output)
        output["root_cause"] = root_cause
        output["severity"] = severity
        results.append(output)
    return results


def build_sql_executor(db_url: str) -> Callable[[str], list[dict[str, Any]]]:
    engine = create_engine(db_url)

    def execute(sql: str) -> list[dict[str, Any]]:
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            rows = result.mappings().fetchmany(1001)
        if len(rows) > 1000:
            raise ValueError("SQL result exceeded 1000 rows; add a bounded reference query")
        return [_json_safe_row(dict(row)) for row in rows]

    return execute


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(value) for key, value in row.items()}


def _json_safe_value(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    summary = payload["summary"]
    lines = [
        "# Agent Generalization Exhaustion",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Total: {len(payload['items'])}",
        f"- Dry run: `{payload['dry_run']}`",
        "",
        "## Status",
        "",
        "| Status | Count |",
        "| --- | ---:|",
    ]
    for status, count in sorted(summary["status_counts"].items()):
        lines.append(f"| `{status}` | {count} |")

    lines.extend(["", "## Failures", "", "| ID | Severity | Root cause | Question |", "| --- | --- | --- | --- |"])
    failure_rows = 0
    for item in payload["items"]:
        if item.get("status") != "failed":
            continue
        failure_rows += 1
        question = str(item["question"]).replace("|", "\\|")
        lines.append(
            f"| {item['id']} | `{item.get('severity')}` | `{item.get('root_cause')}` | {question} |"
        )
    if not failure_rows:
        lines.append("| none | none | none | none |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument(
        "--behavior",
        choices=["answer_with_sql", "safe_refusal", "answer_with_analytic_template"],
        default=None,
    )
    parser.add_argument("--ids", type=str, default=None, help="Comma-separated GEN ids to run.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_id = datetime.now().strftime("generalization_exhaustion_%Y%m%dT%H%M%S")
    ids = [item.strip() for item in args.ids.split(",") if item.strip()] if args.ids else None
    items = run_items(
        run_id=run_id,
        limit=args.limit,
        offset=args.offset,
        category=args.category,
        behavior=args.behavior,
        ids=ids,
        dry_run=args.dry_run,
    )
    output_dir = Path("evaluation/agent/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "summary": summarize_items(items),
        "items": items,
    }
    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"
    json_path.write_text(dump_json(payload), encoding="utf-8")
    write_markdown(payload, md_path)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
