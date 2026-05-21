#!/usr/bin/env python3
"""Production canary evaluation for real chart-agent questions."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from src.semantic.planner import build_semantic_plan  # noqa: E402
from src.visualization import (  # noqa: E402
    build_chart_plan,
    build_chart_planning_input,
    detect_visualization_intent,
    plan_chart,
)
from src.visualization.echarts import chart_spec_to_echarts_option  # noqa: E402

DEFAULT_CASES = ROOT / "evaluation" / "visualization" / "chart_agent_prod_cases.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "evaluation" / "visualization" / "results"

RAW_INTERNAL_ERROR_PATTERNS = [
    r"SEMANTIC PLAN ERROR",
    r"CHART PLAN ERROR",
    r"\bBinder Error\b",
    r"\bCatalog Error\b",
    r"\bParser Error\b",
    r"\bTraceback\b",
    r"\bsqlalchemy(?:\.exc)?\b",
    r"\bduckdb(?:\.|_|\b)",
    r"\bKeyError\b",
    r"\bValueError\b",
    r"\bInternal Server Error\b",
]

load_dotenv(ROOT / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run production chart-agent canary evaluation")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--run-agent",
        action="store_true",
        help="Run the real LangGraph agent and validate SQL/chart invariants.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of selected cases.")
    parser.add_argument("--only", default=None, help="Run IDs containing this value, e.g. PROD_MORT_LOC.")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle selected cases before limiting.")
    parser.add_argument("--seed", type=int, default=20260521, help="Seed used with --shuffle.")
    return parser.parse_args()


def load_cases(path: str | Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    case_path = Path(path)
    if not case_path.is_absolute():
        case_path = ROOT / case_path
    rows = [
        json.loads(line)
        for line in case_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return rows


def select_cases(
    cases: list[dict[str, Any]],
    *,
    only: str | None = None,
    limit: int | None = None,
    shuffle: bool = False,
    seed: int = 20260521,
) -> list[dict[str, Any]]:
    selected = [case for case in cases if only is None or only in case["id"]]
    if shuffle:
        selected = list(selected)
        random.Random(seed).shuffle(selected)
    if limit is not None:
        selected = selected[:limit]
    return selected


def evaluate_cases(
    cases: list[dict[str, Any]],
    *,
    run_agent: bool = False,
) -> dict[str, Any]:
    orchestrator = _create_orchestrator() if run_agent else None
    agent_run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    details = []
    counts = {
        "success": 0,
        "no_raw_internal_error": 0,
        "chart_contract_valid": 0,
        "sql_invariant_valid": 0,
        "semantic_dimension_valid": 0,
    }

    for case in cases:
        detail = _evaluate_case(
            case,
            orchestrator=orchestrator,
            agent_run_id=agent_run_id,
            run_agent=run_agent,
        )
        details.append(detail)
        if detail["success"]:
            counts["success"] += 1
        if detail["checks"]["no_raw_internal_error"]:
            counts["no_raw_internal_error"] += 1
        if detail["checks"]["chart_contract_validity"]:
            counts["chart_contract_valid"] += 1
        if detail["checks"]["sql_invariant_validity"]:
            counts["sql_invariant_valid"] += 1
        if detail["checks"]["semantic_dimension_validity"]:
            counts["semantic_dimension_valid"] += 1

    total = len(cases)
    metrics = {
        "success_rate": _ratio(counts["success"], total),
        "no_raw_internal_error": _ratio(counts["no_raw_internal_error"], total),
        "chart_contract_validity": _ratio(counts["chart_contract_valid"], total),
        "sql_invariant_validity": _ratio(counts["sql_invariant_valid"], total),
        "semantic_dimension_validity": _ratio(counts["semantic_dimension_valid"], total),
    }
    failures = [
        {
            "id": detail["id"],
            "query": detail["query"],
            "reasons": detail["failure_reasons"],
            "agent_error": (detail.get("agent") or {}).get("error"),
        }
        for detail in details
        if not detail["success"]
    ]
    return {
        "metrics": metrics,
        "counts": counts,
        "failures": failures,
        "details": details,
    }


def _evaluate_case(
    case: dict[str, Any],
    *,
    orchestrator: Any | None,
    agent_run_id: str,
    run_agent: bool,
) -> dict[str, Any]:
    expected = case["expected"]
    failure_reasons: list[str] = []
    raw_text_parts: list[str] = []
    semantic_summary: dict[str, Any] = {}
    chart_summary: dict[str, Any] = {}

    try:
        semantic_plan = build_semantic_plan(case["query"])
        semantic_summary = _summarize_semantic_plan(semantic_plan)
    except Exception as exc:
        semantic_plan = None
        raw_text_parts.append(str(exc))
        failure_reasons.append(f"semantic_plan_exception: {exc}")

    semantic_dimension_validity = _semantic_dimensions_valid(
        semantic_summary,
        expected.get("forbidden_dimensions") or [],
    )
    if not semantic_dimension_validity:
        failure_reasons.append("semantic_dimension_validity_failed")

    try:
        intent = detect_visualization_intent(case["query"])
        chart_plan = build_chart_plan(case["query"], intent)
        synthetic_spec = _build_synthetic_chart_spec(case, chart_plan, semantic_plan)
        echarts_option = chart_spec_to_echarts_option(synthetic_spec)
        chart_summary = {
            "intent_requested": intent.requested,
            "intent_source": intent.source,
            "chart_hint": intent.chart_hint,
            "chart_plan": chart_plan.model_dump(mode="json"),
            "synthetic_spec": synthetic_spec.model_dump(mode="json"),
            "echarts_valid": _echarts_valid_for_spec(synthetic_spec, echarts_option),
        }
        chart_contract_validity = _offline_chart_contract_valid(chart_summary, expected)
    except Exception as exc:
        chart_contract_validity = False
        raw_text_parts.append(str(exc))
        failure_reasons.append(f"chart_contract_exception: {exc}")

    agent_detail = None
    sql_invariant_validity = True
    if run_agent and orchestrator is not None:
        agent_detail = _evaluate_agent_case(
            orchestrator,
            case,
            agent_run_id=agent_run_id,
        )
        raw_text_parts.extend(_agent_raw_text(agent_detail))
        chart_contract_validity = _agent_chart_contract_valid(agent_detail, expected)
        sql_invariant_validity = _sql_invariants_valid(agent_detail.get("sql_query"), expected)
        if not agent_detail["success"] and not _allows_clarification(agent_detail, expected):
            failure_reasons.append("agent_success_failed")

    no_raw_internal_error = not _has_raw_internal_error("\n".join(raw_text_parts))
    if not no_raw_internal_error:
        failure_reasons.append("raw_internal_error_exposed")
    if not chart_contract_validity:
        failure_reasons.append("chart_contract_validity_failed")
    if not sql_invariant_validity:
        failure_reasons.append("sql_invariant_validity_failed")

    checks = {
        "no_raw_internal_error": no_raw_internal_error,
        "chart_contract_validity": chart_contract_validity,
        "sql_invariant_validity": sql_invariant_validity,
        "semantic_dimension_validity": semantic_dimension_validity,
    }
    success = all(checks.values())
    if run_agent and agent_detail is not None and not _allows_clarification(agent_detail, expected):
        success = success and agent_detail["success"]

    return {
        "id": case["id"],
        "query": case["query"],
        "tags": case.get("tags", []),
        "checks": checks,
        "success": success,
        "failure_reasons": sorted(set(failure_reasons)),
        "semantic": semantic_summary,
        "chart": chart_summary,
        "agent": agent_detail,
    }


def _build_synthetic_chart_spec(case: dict[str, Any], chart_plan: Any, semantic_plan: Any | None):
    expected = case["expected"]
    chart_type = _first(expected.get("chart_types")) or "bar"
    x = _first(expected.get("x_any"))
    y = _first(expected.get("y_any")) or "valor"
    series = _first(expected.get("series_any"))

    rows = _synthetic_rows(chart_type=chart_type, x=x, y=y, series=series)
    sql_query = _synthetic_sql(columns=list(rows[0].keys()))
    planning_input = build_chart_planning_input(
        user_query=case["query"],
        sql_query=sql_query,
        results=rows,
        row_count=len(rows),
        semantic_plan=semantic_plan.model_dump(mode="json") if semantic_plan is not None else None,
        chart_hint=chart_type,
        chart_plan=chart_plan,
    )
    return plan_chart(planning_input)


def _synthetic_rows(
    *,
    chart_type: str,
    x: str | None,
    y: str,
    series: str | None,
) -> list[dict[str, Any]]:
    if chart_type == "kpi" or not x:
        return [{y: 1234.5}]
    if chart_type == "scatter" or _looks_numeric_metric(x):
        return [{x: 1.0, y: 10.0}, {x: 2.0, y: 18.0}, {x: 3.0, y: 25.0}]
    if _looks_temporal_dimension(x):
        if series:
            return [
                {x: "2021", series: "A", y: 10},
                {x: "2021", series: "B", y: 12},
                {x: "2022", series: "A", y: 14},
                {x: "2022", series: "B", y: 17},
            ]
        return [{x: "2021", y: 10}, {x: "2022", y: 15}, {x: "2023", y: 19}]
    if series:
        return [
            {x: "Grupo A", series: "Serie 1", y: 10},
            {x: "Grupo A", series: "Serie 2", y: 12},
            {x: "Grupo B", series: "Serie 1", y: 15},
            {x: "Grupo B", series: "Serie 2", y: 18},
        ]
    return [{x: "Grupo A", y: 10}, {x: "Grupo B", y: 15}, {x: "Grupo C", y: 8}]


def _synthetic_sql(*, columns: list[str]) -> str:
    select_items = ", ".join(f'NULL AS "{column}"' for column in columns)
    return f"SELECT {select_items}"


def _offline_chart_contract_valid(chart_summary: dict[str, Any], expected: dict[str, Any]) -> bool:
    if bool(chart_summary.get("intent_requested")) is not bool(expected.get("requested")):
        return False
    plan = chart_summary.get("chart_plan") or {}
    spec = chart_summary.get("synthetic_spec") or {}
    allowed_chart_types = set(expected.get("chart_types") or [])
    plan_type = plan.get("chart_type")
    spec_type = spec.get("chart_type")
    if allowed_chart_types and plan_type not in allowed_chart_types and plan_type != "auto":
        return False
    if allowed_chart_types and spec_type not in allowed_chart_types:
        return False
    if spec.get("chartable") is not True:
        return False
    if not (spec.get("presentation") or {}).get("title"):
        return False
    if not chart_summary.get("echarts_valid"):
        return False
    return True


def _agent_chart_contract_valid(agent_detail: dict[str, Any], expected: dict[str, Any]) -> bool:
    if _allows_clarification(agent_detail, expected):
        return True
    if not agent_detail.get("success"):
        return False
    chart = agent_detail.get("chart") or {}
    spec = chart.get("spec") or {}
    if bool(chart.get("requested")) is not bool(expected.get("requested")):
        return False
    allowed_chart_types = set(expected.get("chart_types") or [])
    if allowed_chart_types and spec.get("chart_type") not in allowed_chart_types:
        return False
    if not spec.get("chartable"):
        return False
    if not (spec.get("presentation") or {}).get("title"):
        return False
    if spec.get("chart_type") != "table" and not chart.get("echarts"):
        return False
    return True


def _sql_invariants_valid(sql_query: str | None, expected: dict[str, Any]) -> bool:
    if not sql_query:
        return bool(expected.get("allow_clarification"))
    for pattern in expected.get("required_sql_patterns") or []:
        if not re.search(pattern, sql_query, re.I):
            return False
    for pattern in expected.get("forbidden_sql_patterns") or []:
        if re.search(pattern, sql_query, re.I):
            return False
    return True


def _semantic_dimensions_valid(summary: dict[str, Any], forbidden_dimensions: list[str]) -> bool:
    if not summary:
        return False
    forbidden = {item.lower() for item in forbidden_dimensions}
    if not forbidden:
        return True
    actual = {
        str(value).lower()
        for key in [
            "dimensions",
            "required_dimensions",
            "output_dimensions",
            "partition_dimensions",
            "ranked_dimensions",
        ]
        for value in summary.get(key, [])
    }
    return actual.isdisjoint(forbidden)


def _summarize_semantic_plan(plan: Any) -> dict[str, Any]:
    return {
        "intent": plan.intent,
        "metrics": [metric.name for metric in plan.metrics],
        "dimensions": [dimension.name for dimension in plan.dimensions],
        "required_dimensions": list(plan.answer_shape.required_dimensions),
        "output_dimensions": list(plan.answer_shape.output_dimensions),
        "partition_dimensions": list(plan.answer_shape.partition_dimensions),
        "ranked_dimensions": list(plan.answer_shape.ranked_dimensions),
        "constraints": list(plan.constraints),
        "filters": [semantic_filter.model_dump(mode="json") for semantic_filter in plan.filters],
    }


def _evaluate_agent_case(
    orchestrator: Any,
    case: dict[str, Any],
    *,
    agent_run_id: str,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    session_id = f"chart_prod_eval_{agent_run_id}_{case['id']}"
    setup_details = []
    try:
        for index, setup_query in enumerate(case["expected"].get("setup_queries") or []):
            setup_result = orchestrator.process_query(
                user_query=setup_query,
                session_id=session_id,
                streaming=False,
                force_single_query=True,
            )
            setup_details.append(
                {
                    "index": index,
                    "query": setup_query,
                    "success": bool(setup_result.get("success")),
                    "error": setup_result.get("error_message"),
                }
            )
        result = orchestrator.process_query(
            user_query=case["query"],
            session_id=session_id,
            streaming=False,
            force_single_query=True,
        )
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "response": None,
            "answer": None,
            "sql_query": None,
            "row_count": None,
            "chart": {},
            "setup": setup_details,
            "elapsed_seconds": (datetime.now(UTC) - started_at).total_seconds(),
        }

    return {
        "success": bool(result.get("success")),
        "error": result.get("error_message"),
        "response": result.get("response"),
        "answer": result.get("answer"),
        "sql_query": result.get("sql_query"),
        "row_count": result.get("row_count"),
        "chart": result.get("chart") or {},
        "setup": setup_details,
        "elapsed_seconds": (datetime.now(UTC) - started_at).total_seconds(),
    }


def _agent_raw_text(agent_detail: dict[str, Any] | None) -> list[str]:
    if not agent_detail:
        return []
    values = [
        agent_detail.get("error"),
        agent_detail.get("response"),
        agent_detail.get("answer"),
    ]
    values.extend(str(item.get("error") or "") for item in agent_detail.get("setup") or [])
    return [str(value) for value in values if value]


def _allows_clarification(agent_detail: dict[str, Any], expected: dict[str, Any]) -> bool:
    if not expected.get("allow_clarification"):
        return False
    text = "\n".join(_agent_raw_text(agent_detail)).lower()
    return any(token in text for token in ["esclare", "qual", "poderia", "especific"])


def _has_raw_internal_error(text: str) -> bool:
    return any(re.search(pattern, text or "", re.I) for pattern in RAW_INTERNAL_ERROR_PATTERNS)


def _echarts_valid_for_spec(spec: Any, option: dict[str, Any] | None) -> bool:
    if not spec.chartable:
        return False
    if spec.chart_type == "table":
        return True
    return bool(option and option.get("series"))


def _looks_temporal_dimension(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ["ano", "year", "mes", "month", "periodo", "data"])


def _looks_numeric_metric(value: str) -> bool:
    lowered = value.lower()
    return any(
        token in lowered
        for token in [
            "taxa",
            "valor",
            "receita",
            "custo",
            "media",
            "mortalidade",
            "permanencia",
            "pib",
            "leitos",
            "medicos",
        ]
    )


def _first(values: list[Any] | None) -> Any | None:
    return values[0] if values else None


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _create_orchestrator():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for --run-agent")
    from src.agent.orchestrator import LangGraphOrchestrator
    from src.application.config.simple_config import ApplicationConfig, OrchestratorConfig

    return LangGraphOrchestrator(ApplicationConfig(), OrchestratorConfig(), environment="development")


def main() -> int:
    args = parse_args()
    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = ROOT / cases_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    cases = select_cases(
        load_cases(cases_path),
        only=args.only,
        limit=args.limit,
        shuffle=args.shuffle,
        seed=args.seed,
    )
    report = evaluate_cases(cases, run_agent=args.run_agent)
    report["run"] = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "cases": str(cases_path.relative_to(ROOT)),
        "total": len(cases),
        "run_agent": args.run_agent,
        "only": args.only,
        "limit": args.limit,
        "shuffle": args.shuffle,
        "seed": args.seed,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"chart_agent_prod_eval_{timestamp}.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(report["metrics"], indent=2, ensure_ascii=False))
    print(f"Failures: {len(report['failures'])}")
    print(f"Report: {output_path}")
    return 0 if not report["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
