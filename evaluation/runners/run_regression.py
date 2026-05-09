#!/usr/bin/env python3
"""
Regression runner — executes the 40-query critical set and reports EX.

Usage
-----
# Full run (requires DATABASE_URL + OPENAI_API_KEY in env)
python -m evaluation.runners.run_regression

# Limit queries for a smoke-test
python -m evaluation.runners.run_regression --max-queries 10

# Only a specific tier
python -m evaluation.runners.run_regression --tier hard

# Save JSON report
python -m evaluation.runners.run_regression --output evaluation/agent/results/regression_<ts>.json

Exit code: 0 if EX >= threshold (default 0.90), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from evaluation.runners.result_matching import results_match  # noqa: E402


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _load_regression_set(tier: str | None) -> list[dict]:
    path = ROOT / "evaluation" / "regression_set.json"
    if not path.exists():
        sys.exit(f"[ERROR] regression_set.json not found at {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if tier:
        data = [q for q in data if q["difficulty"] == tier]
        if not data:
            sys.exit(f"[ERROR] No queries for tier '{tier}'")
    return data


def _run_gold_sql(sql: str, db_manager) -> Any:
    """Execute gold SQL and return raw result rows."""
    try:
        tools = db_manager.get_sql_tools()
        query_tool = next((t for t in tools if t.name == "sql_db_query"), None)
        if not query_tool:
            return None
        return query_tool.invoke(sql)
    except Exception as exc:
        return f"__GOLD_ERROR__: {exc}"


def _results_match(agent_rows: Any, gold_raw: Any) -> bool:
    """Execution accuracy: agent result == gold result (row-set comparison)."""
    return results_match(agent_rows, gold_raw)


def run_regression(
    max_queries: int | None = None,
    tier: str | None = None,
    ex_threshold: float = 0.90,
    per_query_timeout: int = 60,
    output_path: str | None = None,
    verbose: bool = True,
) -> dict:
    """Run the regression suite and return a results dict."""

    # ── env guards ────────────────────────────────────────────────────────────
    if not os.getenv("DATABASE_URL") and not os.getenv("DATABASE_PATH"):
        sys.exit(
            "[ERROR] DATABASE_URL or DATABASE_PATH not set. Regression requires a live database."
        )
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("[ERROR] OPENAI_API_KEY not set.")

    from src.agent.orchestrator import LangGraphOrchestrator
    from src.application.config.simple_config import ApplicationConfig

    queries = _load_regression_set(tier)
    if max_queries:
        queries = queries[:max_queries]

    config = ApplicationConfig()
    orchestrator = LangGraphOrchestrator(config)
    db_manager = orchestrator._llm_manager  # type: ignore[attr-defined]

    run_ts = datetime.utcnow().isoformat() + "Z"
    git_sha = _git_sha()
    prompt_version = getattr(config, "prompt_version", "v1")
    model_id = config.llm_model

    results: list[dict] = []
    n_correct = 0
    by_tier: dict[str, dict] = {}

    print(f"\n{'─' * 60}")
    print(f"  Regression Suite — {len(queries)} queries | model={model_id} | sha={git_sha}")
    print(f"{'─' * 60}\n")

    for i, q in enumerate(queries, 1):
        qid = q["id"]
        difficulty = q["difficulty"]
        question = q["question"]
        gold_sql = q["query"]

        t0 = time.time()
        ex = False
        generated_sql = ""
        error_msg = ""
        taxonomy: list[str] = []

        try:
            result = orchestrator.process_query(
                question,
                session_id=f"regression_{qid}",
                force_single_query=True,
            )
            generated_sql = result.get("sql_query", "")
            agent_rows = result.get("final_result_rows")
            if agent_rows is None:
                agent_rows = result.get("results", [])
            taxonomy = result.get("failure_taxonomy", [])

            if result.get("success"):
                gold_raw = _run_gold_sql(gold_sql, db_manager)
                ex = _results_match(agent_rows, gold_raw)
        except Exception as exc:
            error_msg = str(exc)

        elapsed = round(time.time() - t0, 2)
        if ex:
            n_correct += 1

        tier_stats = by_tier.setdefault(difficulty, {"correct": 0, "total": 0})
        tier_stats["total"] += 1
        if ex:
            tier_stats["correct"] += 1

        status = "✓" if ex else "✗"
        if verbose:
            print(
                f"  [{i:02d}/{len(queries)}] {status} {qid} ({difficulty:6}) {elapsed:5.1f}s  {question[:55]}"
            )
            if not ex and (error_msg or taxonomy):
                detail = error_msg[:80] if error_msg else f"taxonomy={taxonomy}"
                print(f"           → {detail}")

        results.append(
            {
                "id": qid,
                "difficulty": difficulty,
                "question": question,
                "gold_sql": gold_sql,
                "generated_sql": generated_sql,
                "ex": ex,
                "elapsed_s": elapsed,
                "failure_taxonomy": taxonomy,
                "error": error_msg,
                "critical_rule": q.get("critical_rule"),
            }
        )

    overall_ex = n_correct / len(queries) if queries else 0.0

    print(f"\n{'─' * 60}")
    print(f"  EX overall : {overall_ex:.1%}  ({n_correct}/{len(queries)})")
    for tier_name in ("easy", "medium", "hard"):
        ts = by_tier.get(tier_name)
        if ts:
            pct = ts["correct"] / ts["total"] if ts["total"] else 0
            print(f"  EX {tier_name:6} : {pct:.1%}  ({ts['correct']}/{ts['total']})")
    passed = overall_ex >= ex_threshold
    print(f"\n  {'PASS ✓' if passed else 'FAIL ✗'}  (threshold={ex_threshold:.0%})")
    print(f"{'─' * 60}\n")

    report = {
        "run_ts": run_ts,
        "git_sha": git_sha,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "n_queries": len(queries),
        "ex_overall": round(overall_ex, 4),
        "ex_threshold": ex_threshold,
        "passed": passed,
        "by_tier": {
            k: {"ex": round(v["correct"] / v["total"], 4) if v["total"] else 0, **v}
            for k, v in by_tier.items()
        },
        "queries": results,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Report saved → {output_path}\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="TXT2SQL regression runner")
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument("--tier", choices=["easy", "medium", "hard"], default=None)
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.output is None:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        tier_suffix = f"_{args.tier}" if args.tier else ""
        args.output = str(ROOT / f"evaluation/agent/results/regression{tier_suffix}_{ts}.json")

    report = run_regression(
        max_queries=args.max_queries,
        tier=args.tier,
        ex_threshold=args.threshold,
        per_query_timeout=args.timeout,
        output_path=args.output,
        verbose=not args.quiet,
    )

    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
