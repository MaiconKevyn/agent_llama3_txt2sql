#!/usr/bin/env python3
"""Evaluate explicit chart intent and ChartSpec generation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from src.visualization import (  # noqa: E402
    build_chart_plan,
    build_chart_planning_input,
    detect_visualization_intent,
    plan_chart,
)
from src.visualization.echarts import chart_spec_to_echarts_option  # noqa: E402

DEFAULT_GOLD = ROOT / "evaluation" / "visualization" / "chart_gold.json"
DEFAULT_OUTPUT_DIR = ROOT / "evaluation" / "visualization" / "results"

load_dotenv(ROOT / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run visualization planning evaluation")
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--run-agent",
        action="store_true",
        help="Run the real LangGraph agent against each applicable gold query.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of gold items.")
    parser.add_argument("--only", default=None, help="Run only IDs containing this substring.")
    return parser.parse_args()


def evaluate_items(
    items: list[dict[str, Any]],
    *,
    run_agent: bool = False,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    counts = {
        "intent_tp": 0,
        "intent_fp": 0,
        "intent_tn": 0,
        "intent_fn": 0,
        "spec_valid": 0,
        "spec_expected": 0,
        "column_fidelity": 0,
        "chart_type_correct": 0,
        "chart_type_expected": 0,
        "x_correct": 0,
        "x_expected": 0,
        "y_correct": 0,
        "y_expected": 0,
        "series_correct": 0,
        "series_expected": 0,
        "echarts_valid": 0,
        "echarts_expected": 0,
        "presentation_expected": 0,
        "presentation_correct": 0,
        "agent_expected": 0,
        "agent_success": 0,
        "agent_chart_type_correct": 0,
        "agent_x_correct": 0,
        "agent_y_correct": 0,
        "agent_series_correct": 0,
        "agent_echarts_valid": 0,
    }
    orchestrator = _create_orchestrator() if run_agent else None
    agent_run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")

    for item in items:
        intent = detect_visualization_intent(item["query"])
        expected_requested = bool(item.get("expect_requested"))
        if intent.requested and expected_requested:
            counts["intent_tp"] += 1
        elif intent.requested and not expected_requested:
            counts["intent_fp"] += 1
        elif not intent.requested and not expected_requested:
            counts["intent_tn"] += 1
        else:
            counts["intent_fn"] += 1

        spec = None
        spec_error = None
        if expected_requested:
            counts["spec_expected"] += 1
            try:
                chart_plan = build_chart_plan(item["query"], intent)
                planning_input = build_chart_planning_input(
                    user_query=item["query"],
                    sql_query=item.get("sql_query"),
                    results=item.get("results") or [],
                    row_count=item.get("row_count", 0),
                    chart_hint=intent.chart_hint,
                    chart_plan=chart_plan,
                )
                spec = plan_chart(planning_input)
                if spec.chartable:
                    counts["spec_valid"] += 1
                spec_columns = {spec.x, spec.y, spec.series} - {None}
                if spec_columns.issubset(set(planning_input.columns)):
                    counts["column_fidelity"] += 1
                if item.get("expected_chart_type"):
                    counts["chart_type_expected"] += 1
                    if spec.chart_type == item["expected_chart_type"]:
                        counts["chart_type_correct"] += 1
                if item.get("expected_x"):
                    counts["x_expected"] += 1
                    if _same_field(spec.x, item["expected_x"]):
                        counts["x_correct"] += 1
                if item.get("expected_y"):
                    counts["y_expected"] += 1
                    if _same_field(spec.y, item["expected_y"]):
                        counts["y_correct"] += 1
                if "expected_series" in item:
                    counts["series_expected"] += 1
                    if _same_optional_field(spec.series, item.get("expected_series")):
                        counts["series_correct"] += 1
                echarts_option = chart_spec_to_echarts_option(spec)
                if item.get("expected_echarts_series_type"):
                    counts["echarts_expected"] += 1
                    if _echarts_has_series_type(echarts_option, item["expected_echarts_series_type"]):
                        counts["echarts_valid"] += 1
                if any(
                    key in item
                    for key in [
                        "expected_value_format",
                        "expected_x_label",
                        "expected_y_label",
                        "expected_warning_codes",
                    ]
                ):
                    counts["presentation_expected"] += 1
                    if _presentation_matches(spec, item):
                        counts["presentation_correct"] += 1
            except Exception as exc:
                spec_error = str(exc)

        agent_detail = None
        if run_agent and orchestrator and not item.get("skip_agent"):
            counts["agent_expected"] += 1
            agent_detail = _evaluate_agent_item(orchestrator, item, agent_run_id=agent_run_id)
            if agent_detail["success"]:
                counts["agent_success"] += 1
            if agent_detail["chart_type_correct"]:
                counts["agent_chart_type_correct"] += 1
            if agent_detail["x_correct"]:
                counts["agent_x_correct"] += 1
            if agent_detail["y_correct"]:
                counts["agent_y_correct"] += 1
            if agent_detail["series_correct"]:
                counts["agent_series_correct"] += 1
            if agent_detail["echarts_valid"]:
                counts["agent_echarts_valid"] += 1

        details.append(
            {
                "id": item["id"],
                "query": item["query"],
                "expected_requested": expected_requested,
                "actual_requested": intent.requested,
                "uses_last_result": intent.uses_last_result,
                "chart_hint": intent.chart_hint,
                "chart_type": spec.chart_type if spec else None,
                "chartable": spec.chartable if spec else None,
                "x": spec.x if spec else None,
                "y": spec.y if spec else None,
                "series": spec.series if spec else None,
                "spec_error": spec_error,
                "agent": agent_detail,
            }
        )

    precision_den = counts["intent_tp"] + counts["intent_fp"]
    recall_den = counts["intent_tp"] + counts["intent_fn"]
    metrics = {
        "intent_precision": counts["intent_tp"] / precision_den if precision_den else 1.0,
        "intent_recall": counts["intent_tp"] / recall_den if recall_den else 1.0,
        "intent_accuracy": (counts["intent_tp"] + counts["intent_tn"]) / len(items) if items else 0.0,
        "spec_validity": counts["spec_valid"] / counts["spec_expected"] if counts["spec_expected"] else 1.0,
        "column_fidelity": (
            counts["column_fidelity"] / counts["spec_expected"] if counts["spec_expected"] else 1.0
        ),
        "chart_type_accuracy": (
            counts["chart_type_correct"] / counts["chart_type_expected"]
            if counts["chart_type_expected"]
            else 1.0
        ),
        "x_accuracy": counts["x_correct"] / counts["x_expected"] if counts["x_expected"] else 1.0,
        "y_accuracy": counts["y_correct"] / counts["y_expected"] if counts["y_expected"] else 1.0,
        "series_accuracy": (
            counts["series_correct"] / counts["series_expected"] if counts["series_expected"] else 1.0
        ),
        "echarts_validity": (
            counts["echarts_valid"] / counts["echarts_expected"] if counts["echarts_expected"] else 1.0
        ),
        "presentation_validity": (
            counts["presentation_correct"] / counts["presentation_expected"]
            if counts["presentation_expected"]
            else 1.0
        ),
    }
    if run_agent:
        metrics.update(
            {
                "agent_success_rate": (
                    counts["agent_success"] / counts["agent_expected"]
                    if counts["agent_expected"]
                    else 1.0
                ),
                "agent_chart_type_accuracy": (
                    counts["agent_chart_type_correct"] / counts["agent_expected"]
                    if counts["agent_expected"]
                    else 1.0
                ),
                "agent_x_accuracy": (
                    counts["agent_x_correct"] / counts["agent_expected"]
                    if counts["agent_expected"]
                    else 1.0
                ),
                "agent_y_accuracy": (
                    counts["agent_y_correct"] / counts["agent_expected"]
                    if counts["agent_expected"]
                    else 1.0
                ),
                "agent_series_accuracy": (
                    counts["agent_series_correct"] / counts["agent_expected"]
                    if counts["agent_expected"]
                    else 1.0
                ),
                "agent_echarts_validity": (
                    counts["agent_echarts_valid"] / counts["agent_expected"]
                    if counts["agent_expected"]
                    else 1.0
                ),
            }
        )
    return {"metrics": metrics, "counts": counts, "details": details}


def _same_field(actual: str | None, expected: str | list[str]) -> bool:
    expected_values = expected if isinstance(expected, list) else [expected]
    return (actual or "").lower() in {str(value).lower() for value in expected_values}


def _same_optional_field(actual: str | None, expected: str | None) -> bool:
    if expected is None:
        return actual is None
    return _same_field(actual, expected)


def _presentation_matches(spec, item: dict[str, Any]) -> bool:
    presentation = spec.presentation
    if item.get("expected_value_format") and presentation.value_format != item["expected_value_format"]:
        return False
    if item.get("expected_x_label") and presentation.x_label != item["expected_x_label"]:
        return False
    if item.get("expected_y_label") and presentation.y_label != item["expected_y_label"]:
        return False
    expected_warning_codes = set(item.get("expected_warning_codes") or [])
    actual_warning_codes = {warning.code for warning in spec.warnings}
    if not expected_warning_codes.issubset(actual_warning_codes):
        return False
    if spec.chartable and not presentation.title:
        return False
    return True


def _echarts_has_series_type(option: dict[str, Any] | None, expected_type: str) -> bool:
    if not option:
        return False
    return any(series.get("type") == expected_type for series in option.get("series", []))


def _create_orchestrator():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for --run-agent")
    from src.agent.orchestrator import LangGraphOrchestrator
    from src.application.config.simple_config import ApplicationConfig, OrchestratorConfig

    return LangGraphOrchestrator(ApplicationConfig(), OrchestratorConfig(), environment="development")


def _evaluate_agent_item(
    orchestrator,
    item: dict[str, Any],
    *,
    agent_run_id: str,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    try:
        result = orchestrator.process_query(
            user_query=item["query"],
            session_id=f"chart_eval_{agent_run_id}_{item['id']}",
            streaming=False,
            force_single_query=True,
        )
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "elapsed_seconds": (datetime.now(UTC) - started_at).total_seconds(),
            "chart_type": None,
            "x": None,
            "y": None,
            "series": None,
            "chart_type_correct": False,
            "x_correct": False,
            "y_correct": False,
            "series_correct": False,
            "echarts_valid": False,
        }

    chart = result.get("chart") or {}
    spec = chart.get("spec") or {}
    echarts_option = chart.get("echarts")
    success = bool(result.get("success")) and bool(chart.get("requested")) == bool(item.get("expect_requested"))
    if item.get("expect_requested"):
        success = success and bool(spec.get("chartable"))

    return {
        "success": success,
        "error": result.get("error_message"),
        "elapsed_seconds": (datetime.now(UTC) - started_at).total_seconds(),
        "sql_query": result.get("sql_query"),
        "row_count": result.get("row_count"),
        "chart_type": spec.get("chart_type"),
        "x": spec.get("x"),
        "y": spec.get("y"),
        "series": spec.get("series"),
        "chart_type_correct": (
            not item.get("expected_chart_type")
            or spec.get("chart_type") == item.get("expected_chart_type")
        ),
        "x_correct": (
            not item.get("expected_x")
            or _same_field(spec.get("x"), item.get("expected_x"))
        ),
        "y_correct": (
            not item.get("expected_y")
            or _same_field(spec.get("y"), item.get("expected_y"))
        ),
        "series_correct": (
            "expected_series" not in item
            or _same_optional_field(spec.get("series"), item.get("expected_series"))
        ),
        "echarts_valid": (
            not item.get("expected_echarts_series_type")
            or _echarts_has_series_type(echarts_option, item["expected_echarts_series_type"])
        ),
    }


def main() -> int:
    args = parse_args()
    gold_path = Path(args.gold)
    if not gold_path.is_absolute():
        gold_path = ROOT / gold_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    items = json.loads(gold_path.read_text(encoding="utf-8"))
    if args.only:
        items = [item for item in items if args.only in item["id"]]
    if args.limit is not None:
        items = items[: args.limit]

    report = evaluate_items(items, run_agent=args.run_agent)
    report["run"] = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "gold": str(gold_path.relative_to(ROOT)),
        "total": len(items),
        "run_agent": args.run_agent,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"chart_evaluation_{timestamp}.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(report["metrics"], indent=2, ensure_ascii=False))
    print(f"Report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
