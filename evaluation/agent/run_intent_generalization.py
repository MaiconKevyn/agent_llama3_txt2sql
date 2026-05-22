"""Run the intent/tool-planning generalization corpus."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.agent.intent_generalization_rubric import (
    build_intent_generalization_trace,
    dump_json,
    load_intent_generalization_questions,
    score_intent_generalization,
)


def select_questions(
    *,
    ids: list[str] | None = None,
    family: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Any]:
    questions = load_intent_generalization_questions()
    if ids:
        wanted = set(ids)
        questions = [item for item in questions if item.id in wanted]
        missing = wanted - {item.id for item in questions}
        if missing:
            raise ValueError(f"Unknown intent generalization question ids: {sorted(missing)}")
    if family:
        questions = [item for item in questions if item.family == family]
    if offset:
        questions = questions[offset:]
    return questions[:limit] if limit else questions


def run_items(
    *,
    ids: list[str] | None = None,
    family: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for question in select_questions(ids=ids, family=family, limit=limit, offset=offset):
        trace = build_intent_generalization_trace(question.question)
        judgement = score_intent_generalization(question, trace)
        items.append(
            {
                "id": question.id,
                "persona": question.persona,
                "family": question.family,
                "question": question.question,
                "expected_intent": question.expected_intent,
                "expected_concepts": question.expected_concepts,
                "expected_tables": question.expected_tables,
                "judge": question.judge,
                "anti_overfit_family": question.anti_overfit_family,
                "status": "passed" if judgement["passed"] else "failed",
                "judgement": judgement,
                "trace": trace.model_dump(),
            }
        )
    return items


def summarize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "status_counts": dict(Counter(item["status"] for item in items)),
        "family_counts": dict(Counter(item["family"] for item in items)),
        "judge_counts": dict(Counter(item["judge"] for item in items)),
        "failure_missing_counts": dict(
            Counter(
                missing
                for item in items
                if item["status"] == "failed"
                for missing in item.get("judgement", {}).get("missing", [])
            )
        ),
    }


def write_outputs(payload: dict[str, Any]) -> tuple[Path, Path]:
    results_dir = Path(__file__).with_name("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    json_path = results_dir / f"intent_generalization_{stamp}.json"
    md_path = results_dir / f"intent_generalization_{stamp}.md"
    json_path.write_text(dump_json(payload), encoding="utf-8")
    md_path.write_text(_to_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _to_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Intent Generalization Evaluation",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Total: {summary['total']}",
        f"- Status: `{summary['status_counts']}`",
        "",
        "## Failures",
        "",
    ]
    failures = [item for item in payload["items"] if item["status"] == "failed"]
    if not failures:
        lines.append("No failures.")
    for item in failures[:50]:
        missing = ", ".join(item["judgement"].get("missing") or [])
        lines.extend(
            [
                f"- `{item['id']}` ({item['family']}): {missing}",
                f"  - Question: {item['question']}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", default="contract", help="Run label only.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--family", default=None)
    parser.add_argument("--ids", nargs="*", default=None)
    parser.add_argument("--allow-failures", action="store_true")
    args = parser.parse_args()

    run_id = f"intent_{args.round}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    items = run_items(ids=args.ids, family=args.family, limit=args.limit, offset=args.offset)
    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
        "summary": summarize_items(items),
        "items": items,
    }
    json_path, md_path = write_outputs(payload)
    print(json_path)
    print(md_path)
    failures = payload["summary"]["status_counts"].get("failed", 0)
    if failures and not args.allow_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
