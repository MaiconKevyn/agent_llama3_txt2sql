from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.orchestrator import create_production_orchestrator  # noqa: E402
from src.interfaces.api.main import _build_debug_result_from_updates  # noqa: E402

CASES_PATH = Path("evaluation/cid_investigation/cid_probe_cases.jsonl")
RESULTS_DIR = Path("evaluation/cid_investigation/results")


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _latest_debug_value(debug: dict[str, Any], key: str, default: Any) -> Any:
    for step in reversed(debug.get("steps", [])):
        data = step.get("data", {})
        if key in data and data[key] not in (None, "", []):
            return data[key]
    return default


def _classify_initial_failure(case: dict[str, Any], result: dict[str, Any]) -> str | None:
    if result.get("error"):
        return "sql_runtime_error"

    selected_tables = set(result.get("selected_tables") or [])
    required_tables = set(case.get("required_tables") or [])
    if required_tables and not required_tables.issubset(selected_tables):
        return "wrong_table_selection"

    sql = (result.get("generated_sql") or "").upper()
    if "DIAG_SECUN" in sql or "CID_MORTE" in sql:
        return "unsafe_join"

    return None


def _empty_case_result(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "question": case["question"],
        "focus": case["focus"],
        "response_text": "",
        "generated_sql": "",
        "selected_tables": [],
        "debug": {},
        "error": None,
        "latency_ms": 0,
        "failure_category": None,
    }


def run_case(case: dict[str, Any], *, dry_run: bool, orchestrator: Any | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    result = _empty_case_result(case)

    if dry_run:
        result["response_text"] = "[dry-run]"
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    if orchestrator is None:
        raise ValueError("orchestrator is required for live CID agent evaluation")

    try:
        updates = orchestrator.process_query(
            case["question"],
            session_id=f"cid-eval-{case['id']}-{uuid4().hex[:8]}",
            streaming=True,
        )
        agent_result = _build_debug_result_from_updates(case["question"], updates)
        debug = agent_result.get("debug") or {}
        generated_sql = (
            agent_result.get("sql_query")
            or _latest_debug_value(debug, "final_sql_query", "")
            or _latest_debug_value(debug, "generated_sql", "")
        )
        selected_tables = _latest_debug_value(debug, "selected_tables", [])

        result.update(
            {
                "response_text": agent_result.get("response") or agent_result.get("answer") or "",
                "generated_sql": generated_sql or "",
                "selected_tables": selected_tables or [],
                "debug": debug,
                "error": agent_result.get("error_message"),
            }
        )
    except Exception as exc:  # pragma: no cover - exercised by live runs
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["failure_category"] = _classify_initial_failure(case, result)

    return result


def select_cases(cases: list[dict[str, Any]], *, case_id: str | None, limit: int | None) -> list[dict[str, Any]]:
    selected = cases
    if case_id:
        selected = [case for case in selected if case["id"] == case_id]
    if limit:
        selected = selected[:limit]
    return selected


def write_results(results: list[dict[str, Any]], output: Path | None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = output or RESULTS_DIR / f"cid_agent_eval_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "case_count": len(results),
        "results": results,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CID-focused agent evaluation corpus.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    cases = select_cases(load_cases(CASES_PATH), case_id=args.case_id, limit=args.limit)
    orchestrator = None if args.dry_run else create_production_orchestrator()
    results = [run_case(case, dry_run=args.dry_run, orchestrator=orchestrator) for case in cases]
    output = write_results(results, Path(args.output) if args.output else None)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
