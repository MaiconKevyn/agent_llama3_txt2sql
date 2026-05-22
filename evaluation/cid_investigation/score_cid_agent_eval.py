from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.orchestrator_support import resolve_database_url  # noqa: E402

CASES_PATH = Path("evaluation/cid_investigation/cid_probe_cases.jsonl")
GOLD_PATH = Path("evaluation/cid_investigation/cid_gold_sql.jsonl")
RESULTS_DIR = Path("evaluation/cid_investigation/results")
AMBIGUITY_CAVEAT_TERMS = ("escopo", "confirm", "candidat", "limita", "especific")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def index_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in items}


def classify_join(sql: str) -> str:
    normalized = " ".join(sql.upper().split())
    if "DIAG_PRINC" in normalized and "CID" in normalized:
        return "allowed_primary_diagnosis_join"
    if "DIAG_SECUN" in normalized or "CID_MORTE" in normalized:
        return "unsafe_or_audit_only_join"
    return "no_cid_join"


def normalize_sql(sql: str) -> str:
    return " ".join((sql or "").upper().replace('"', "").split())


def normalize_sql_loose(sql: str) -> str:
    normalized = normalize_sql(sql)
    return normalized.replace("I.", "").replace("C.", "").replace("CID.", "")


def sql_mentions(sql: str, value: str) -> bool:
    return normalize_sql_loose(value) in normalize_sql_loose(sql)


def check_expected_sql_features(sql: str, expected_values: list[str]) -> bool:
    if not expected_values:
        return True
    normalized = normalize_sql(sql)
    checks = []
    for value in expected_values:
        value_upper = value.upper()
        if " OR " in value_upper:
            checks.append(any(sql_mentions(sql, part.strip()) for part in value_upper.split(" OR ")))
        elif value_upper.replace(" ", "") == "SUM(MORTE)":
            checks.append("MORTE" in normalized and ("SUM(" in normalized or "COUNT(" in normalized))
        elif value_upper == "RATE":
            checks.append(
                "TAXA" in normalized
                or "RATE" in normalized
                or ("/" in normalized and "COUNT(" in normalized)
            )
        elif value_upper == "UTI_INT_TO":
            checks.append(sql_mentions(sql, "UTI_INT_TO") or sql_mentions(sql, "VAL_UTI"))
        elif value_upper == "YEAR(DT_INTER)":
            checks.append(sql_mentions(sql, "EXTRACT(YEAR FROM") and sql_mentions(sql, "DT_INTER"))
        else:
            checks.append(sql_mentions(sql, value))
    return all(checks)


def cid_prefix_resolution_satisfies_search(sql: str, expected_values: list[str]) -> bool:
    """Accept deterministic CID-family prefix resolution as a concept search equivalent."""

    if not expected_values:
        return False
    normalized = normalize_sql_loose(sql)
    expects_cid_text_search = bool(
        {"DESCRICAO", "DS_CATEGORIA", "DS_GRUPO"} & {normalize_sql_loose(value) for value in expected_values}
    )
    has_prefix_filter = bool(
        re.search(r"\b(?:CID|DIAG_PRINC)\s+LIKE\s+'[A-Z]\d{2}%'", normalized)
    )
    return expects_cid_text_search and has_prefix_filter


def check_sql_runtime(sql: str, engine: Any | None) -> tuple[bool | None, str | None]:
    if not sql:
        return None, None
    if engine is None:
        return None, "sql_runtime_skipped_no_engine"
    try:
        with engine.connect() as connection:
            connection.execute(text(f"EXPLAIN {sql.rstrip(';')}"))
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def required_tables_satisfied(required_tables: set[str], selected_tables: set[str], sql: str) -> bool:
    missing = set(required_tables) - set(selected_tables)
    if not missing:
        return True
    normalized = normalize_sql(sql)
    selected_normalized = {table.upper() for table in selected_tables}
    if missing == {"sexo"} and "INTERNACOES" in selected_normalized and "SEXO" in normalized:
        return True
    if missing == {"car_int"} and "INTERNACOES" in selected_normalized and "CAR_INT" in normalized:
        return True
    return False


def build_engine(skip_sql_runtime: bool) -> Any | None:
    if skip_sql_runtime:
        return None
    load_dotenv(ROOT / ".env")
    try:
        return create_engine(resolve_database_url(None))
    except Exception:
        return None


def score_item(
    result: dict[str, Any],
    case: dict[str, Any],
    gold: dict[str, Any],
    *,
    engine: Any | None,
) -> dict[str, Any]:
    sql = result.get("generated_sql") or ""
    selected_tables = set(result.get("selected_tables") or [])
    required_tables = set(case.get("required_tables") or gold.get("required_tables") or [])
    forbidden_tables = set(case.get("forbidden_tables") or [])
    expected_columns = (
        case.get("expected_columns")
        or case.get("expected_group_by")
        or case.get("expected_search_columns")
        or case.get("expected_filters")
        or case.get("expected_metrics")
        or []
    )

    expected_columns_ok = check_expected_sql_features(sql, expected_columns)
    if not expected_columns_ok and cid_prefix_resolution_satisfies_search(sql, expected_columns):
        expected_columns_ok = True

    checks: dict[str, Any] = {
        "required_tables": required_tables_satisfied(required_tables, selected_tables, sql),
        "forbidden_tables": not (forbidden_tables & selected_tables),
        "unsafe_join": classify_join(sql) != "unsafe_or_audit_only_join",
        "expected_columns": expected_columns_ok,
        "expected_sql_features": check_expected_sql_features(sql, case.get("expected_sql_features", [])),
    }

    if case.get("required_join") or gold.get("required_join") or "internacoes" in required_tables:
        checks["required_join"] = classify_join(sql) == "allowed_primary_diagnosis_join"
    else:
        checks["required_join"] = True

    if "sql" in gold:
        runtime_ok, runtime_error = check_sql_runtime(sql, engine)
        checks["sql_runtime"] = runtime_ok is not False and not result.get("error")
    else:
        runtime_ok, runtime_error = None, None
        checks["sql_runtime"] = not result.get("error")

    if case.get("focus") == "ambiguity":
        response = (result.get("response_text") or "").lower()
        checks["ambiguity_caveat"] = any(term in response for term in AMBIGUITY_CAVEAT_TERMS)
    else:
        checks["ambiguity_caveat"] = True

    failure_categories = []
    if not checks["required_tables"]:
        failure_categories.append("wrong_table_selection")
    if not checks["forbidden_tables"] or not checks["unsafe_join"]:
        failure_categories.append("unsafe_join")
    if not checks["required_join"]:
        failure_categories.append("missing_join")
    if not checks["expected_columns"] or not checks["expected_sql_features"]:
        failure_categories.append("wrong_column_selection")
    if checks["sql_runtime"] is False:
        failure_categories.append("sql_runtime_error")
    if not checks["ambiguity_caveat"]:
        failure_categories.append("response_grounding_gap")

    passed = not failure_categories
    return {
        "id": result["id"],
        "focus": case.get("focus"),
        "difficulty": case.get("difficulty"),
        "passed": passed,
        "checks": checks,
        "join_classification": classify_join(sql),
        "failure_categories": failure_categories,
        "sql_runtime_error": runtime_error,
    }


def summarize(scored: list[dict[str, Any]]) -> dict[str, Any]:
    by_focus: dict[str, Counter] = defaultdict(Counter)
    by_difficulty: dict[str, Counter] = defaultdict(Counter)
    failure_categories: Counter = Counter()

    for item in scored:
        status = "passed" if item["passed"] else "failed"
        by_focus[item.get("focus") or "unknown"][status] += 1
        by_difficulty[item.get("difficulty") or "unknown"][status] += 1
        failure_categories.update(item.get("failure_categories") or [])

    passed = sum(1 for item in scored if item["passed"])
    total = len(scored)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "overall_pass_rate": round(passed / total, 4) if total else 0.0,
        "by_focus": {key: dict(value) for key, value in sorted(by_focus.items())},
        "by_difficulty": {key: dict(value) for key, value in sorted(by_difficulty.items())},
        "failure_categories": dict(failure_categories),
    }


def score_file(input_path: Path, *, skip_sql_runtime: bool = False) -> dict[str, Any]:
    payload = load_result(input_path)
    cases = index_by_id(load_jsonl(CASES_PATH))
    gold = index_by_id(load_jsonl(GOLD_PATH))
    engine = build_engine(skip_sql_runtime)
    scored = [
        score_item(result, cases[result["id"]], gold.get(result["id"], {}), engine=engine)
        for result in payload.get("results", [])
    ]
    return {
        "generated_at": datetime.now().isoformat(),
        "input": str(input_path),
        "summary": summarize(scored),
        "results": scored,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a CID-focused agent evaluation result.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-sql-runtime", action="store_true")
    args = parser.parse_args()

    report = score_file(args.input, skip_sql_runtime=args.skip_sql_runtime)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
