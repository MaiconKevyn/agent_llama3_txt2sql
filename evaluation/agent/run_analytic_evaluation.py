"""Run or dry-run the analytic response sentinel set."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.agent.analytic_rubric import AnalyticQuestionSet, score_analytic_response
from src.agent.orchestrator import LangGraphOrchestrator
from src.application.config.simple_config import OrchestratorConfig
from src.semantic.analytic_templates import select_analytic_template
from src.semantic.planner import build_semantic_plan


def build_dry_run_items(question_set: AnalyticQuestionSet) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in question_set.questions:
        plan = build_semantic_plan(item.question)
        template = select_analytic_template(plan)
        items.append(
            {
                "id": item.id,
                "question": item.question,
                "expected_template": item.expected_template,
                "detected_template": template.id if template else None,
                "semantic_plan": plan.model_dump(exclude_none=True),
                "template_match": bool(template and template.id == item.expected_template),
            }
        )
    return items


def run_live_items(question_set: AnalyticQuestionSet, *, limit: int | None) -> list[dict[str, Any]]:
    orchestrator = LangGraphOrchestrator(
        orchestrator_config=OrchestratorConfig(
            enable_llamaindex_context=True,
            llamaindex_mode="context",
        ),
        environment="testing",
    )
    selected_questions = question_set.questions[:limit] if limit else question_set.questions
    items: list[dict[str, Any]] = []
    for item in selected_questions:
        result = orchestrator.process_query(
            item.question,
            session_id=f"analytic_eval_{item.id.lower()}",
            force_single_query=True,
        )
        metadata = result.get("metadata") or {}
        response = result.get("response") or result.get("final_response") or ""
        sql = result.get("sql_query") or result.get("generated_sql") or ""
        score = score_analytic_response(
            question=item.question,
            response=response,
            sql=sql,
            semantic_plan=metadata.get("semantic_plan") or {},
        )
        items.append(
            {
                "id": item.id,
                "question": item.question,
                "success": result.get("success", False),
                "expected_template": item.expected_template,
                "detected_template": metadata.get("analytic_template"),
                "score": score.model_dump(),
                "sql": sql,
                "response": response,
                "metadata": metadata,
            }
        )
    return items


def write_result(items: list[dict[str, Any]], *, dry_run: bool) -> Path:
    results_dir = Path(__file__).with_name("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = results_dir / f"analytic_eval_{'dry_run' if dry_run else 'live'}_{stamp}.json"
    payload = {
        "created_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not call the agent.")
    parser.add_argument("--limit", type=int, default=None, help="Limit live questions.")
    args = parser.parse_args()

    question_set = AnalyticQuestionSet.load_default()
    items = (
        build_dry_run_items(question_set)
        if args.dry_run
        else run_live_items(question_set, limit=args.limit)
    )
    path = write_result(items, dry_run=args.dry_run)
    print(path)


if __name__ == "__main__":
    main()
