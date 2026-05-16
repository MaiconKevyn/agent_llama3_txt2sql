#!/usr/bin/env python3
"""
Ablation runner — evaluates the configured pipeline variants over the 40-query
regression set and produces a paired comparison against the full pipeline.

Usage
-----
# All variants, full 40-query regression set
python -m evaluation.runners.run_ablation

# Specific variants only
python -m evaluation.runners.run_ablation --variants V0 V2 V3

# Smoke-test: 5 queries per variant
python -m evaluation.runners.run_ablation --max-queries 5

# Full ground truth with 4 parallel workers
python -m evaluation.runners.run_ablation --dataset evaluation/ground_truth_v2.json --workers 4

# Custom output directory
python -m evaluation.runners.run_ablation --output evaluation/ablation/results/ablation_custom/

Exit code: 0 always (results written to disk regardless).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Load .env before any env-guard checks
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from evaluation.runners.result_matching import compare_results, results_match  # noqa: E402
from src.agent.mlflow_tracker import init_mlflow, log_ablation_run  # noqa: E402

# ── Variant definitions ───────────────────────────────────────────────────────


@dataclass
class VariantSpec:
    id: str
    name: str
    description: str
    flags: dict[str, Any] = field(default_factory=dict)


VARIANTS: list[VariantSpec] = [
    VariantSpec(
        id="V0",
        name="full_pipeline",
        description="Full pipeline — baseline (all components enabled)",
        flags={},
    ),
    VariantSpec(
        id="V2",
        name="no_cot_reasoning",
        description="Remove reasoning_node (CoT planning before generation)",
        flags={"disable_cot_reasoning": True},
    ),
    VariantSpec(
        id="V3",
        name="no_validation",
        description="Remove validate_sql_node (7 semantic rules)",
        flags={"disable_validation": True},
    ),
    VariantSpec(
        id="V4",
        name="no_repair",
        description="Remove repair_sql_node (post-validation fix loop)",
        flags={"disable_repair": True},
    ),
    VariantSpec(
        id="V6",
        name="no_schema_enrichment",
        description="Remove _enhance_sus_schema_context (SUS-specific mappings)",
        flags={"disable_schema_enrichment": True},
    ),
    VariantSpec(
        id="V7",
        name="no_rules",
        description="Remove RULES A–O from SQL generation system prompt",
        flags={"disable_rules": True},
    ),
    VariantSpec(
        id="V8",
        name="zero_shot_raw",
        description="RULES + schema enrichment + CoT + validation all disabled",
        flags={
            "disable_rules": True,
            "disable_schema_enrichment": True,
            "disable_cot_reasoning": True,
            "disable_validation": True,
        },
    ),
    VariantSpec(
        id="V9",
        name="no_semantic_planner",
        description="Skip LLM-assisted SemanticPlan reconciliation; keep heuristic plan_gate",
        flags={"disable_semantic_planner": True},
    ),
    VariantSpec(
        id="V10",
        name="no_semantic_plan_validation",
        description="Skip SemanticPlan validation; keep DB validation, legacy rules, and repair",
        flags={"disable_semantic_plan_validation": True},
    ),
    VariantSpec(
        id="V11",
        name="no_semantic_contract_validator",
        description="Skip AST contract validator; keep higher-level SemanticPlan rules",
        flags={"disable_semantic_contract_validation": True},
    ),
    VariantSpec(
        id="V12",
        name="no_semantic_repair_guidance",
        description="Keep repair node, but remove semantic repair guidance and deterministic semantic repairs",
        flags={"disable_semantic_repair_guidance": True},
    ),
    VariantSpec(
        id="LI2",
        name="llamaindex_sql_draft",
        description="Use LlamaIndex SQL draft generation before validation/execution",
        flags={
            "enable_llamaindex_context": True,
            "enable_llamaindex_sql_draft": True,
            "llamaindex_mode": "sql_draft",
        },
    ),
]

VARIANT_MAP: dict[str, VariantSpec] = {v.id: v for v in VARIANTS}
_WORKER_LOCAL = threading.local()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _resolve_dataset_path(dataset_path: str | None = None) -> Path:
    if dataset_path:
        path = Path(dataset_path)
        return path if path.is_absolute() else ROOT / path
    return ROOT / "evaluation" / "regression_set.json"


def _load_regression_set(
    tier: str | None = None,
    max_queries: int | None = None,
    dataset_path: str | None = None,
) -> list[dict]:
    path = _resolve_dataset_path(dataset_path)
    if not path.exists():
        sys.exit(f"[ERROR] Evaluation dataset not found at {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        sys.exit(f"[ERROR] Evaluation dataset must be a JSON list: {path}")
    missing_fields = [
        q.get("id", f"#{idx}")
        for idx, q in enumerate(data, 1)
        if not all(k in q for k in ("id", "question", "query", "difficulty"))
    ]
    if missing_fields:
        sys.exit(
            "[ERROR] Evaluation dataset items must include id, question, query, difficulty. "
            f"Invalid items: {missing_fields[:5]}"
        )
    if tier:
        data = [q for q in data if q["difficulty"] == tier]
    if max_queries:
        data = data[:max_queries]
    return data


def _run_gold_sql(sql: str, db_manager) -> Any:
    try:
        tools = db_manager.get_sql_tools()
        query_tool = next((t for t in tools if t.name == "sql_db_query"), None)
        if not query_tool:
            return None
        return query_tool.invoke(sql)
    except Exception as exc:
        return f"__GOLD_ERROR__: {exc}"


def _results_match(agent_rows: Any, gold_raw: Any) -> bool:
    return results_match(agent_rows, gold_raw)


def _json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{uuid4().hex[:8]}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _query_sort_key(query_or_result: dict[str, Any]) -> tuple[int, str]:
    qid = str(query_or_result.get("id", ""))
    digits = "".join(ch for ch in qid if ch.isdigit())
    return (int(digits) if digits else 10**9, qid)


def _item_path(items_dir: Path, spec: VariantSpec, qid: str) -> Path:
    safe_qid = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in qid)
    return items_dir / f"{spec.id}_{safe_qid}.json"


def _gold_cache_key(q: dict[str, Any]) -> str:
    sql_hash = hashlib.sha256(q["query"].encode("utf-8")).hexdigest()[:16]
    return f"{q['id']}:{sql_hash}"


def _load_gold_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload.get("items", {}) if isinstance(payload, dict) else {}


def _save_gold_cache(path: Path, items: dict[str, Any], dataset_path: Path) -> None:
    _atomic_write_json(
        path,
        {
            "dataset_path": str(dataset_path),
            "updated_at": _utc_now_iso(),
            "items": items,
        },
    )


def _prepare_gold_cache(
    queries: list[dict],
    db_manager,
    cache_path: Path,
    dataset_path: Path,
    *,
    refresh: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    cache = {} if refresh else _load_gold_cache(cache_path)
    missing = [q for q in queries if _gold_cache_key(q) not in cache]
    if verbose:
        cached = len(queries) - len(missing)
        print(
            f"  Gold cache: {cached} cached, {len(missing)} missing"
        )
    for idx, q in enumerate(missing, 1):
        raw = _run_gold_sql(q["query"], db_manager)
        cache[_gold_cache_key(q)] = {
            "id": q["id"],
            "query_hash": hashlib.sha256(q["query"].encode("utf-8")).hexdigest(),
            "raw": _json_safe(raw),
            "created_at": _utc_now_iso(),
        }
        if verbose:
            print(f"    gold [{idx:02d}/{len(missing)}] {q['id']}")
    if missing or refresh:
        _save_gold_cache(cache_path, cache, dataset_path)
    return cache


def _get_gold_raw(
    q: dict[str, Any],
    db_manager,
    gold_cache: dict[str, Any] | None = None,
) -> Any:
    if gold_cache is not None:
        entry = gold_cache.get(_gold_cache_key(q))
        if entry is not None:
            return entry.get("raw")
    return _run_gold_sql(q["query"], db_manager)


# ── McNemar test ──────────────────────────────────────────────────────────────


def _mcnemar(v0_correct: list[bool], vi_correct: list[bool]) -> tuple[float, float]:
    """
    Return (chi2_stat, p_value) for the McNemar test between V0 and Vi.

    Uses mid-p correction when b+c < 25, chi2 continuity correction otherwise.
    b = V0 correct, Vi wrong
    c = V0 wrong,   Vi correct
    """
    if len(v0_correct) != len(vi_correct):
        raise ValueError("Result vectors must have equal length")

    b = sum(1 for a, b_ in zip(v0_correct, vi_correct) if a and not b_)
    c = sum(1 for a, b_ in zip(v0_correct, vi_correct) if not a and b_)
    n_discordant = b + c

    if n_discordant == 0:
        return 0.0, 1.0

    if n_discordant < 25:
        # Exact mid-p: P(X >= max(b,c)) where X ~ Binomial(n, 0.5)
        from math import comb

        k = max(b, c)
        n = n_discordant
        p_one_tail = sum(comb(n, i) * 0.5**n for i in range(k, n + 1))
        p_mid = p_one_tail - 0.5 * comb(n, k) * 0.5**n
        p_value = min(2.0 * p_mid, 1.0)
        chi2_stat = (b - c) ** 2 / n_discordant
    else:
        # Chi-square with continuity correction
        chi2_stat = (abs(b - c) - 1.0) ** 2 / n_discordant
        # Chi2 p-value with 1 df
        from math import erfc, sqrt

        p_value = erfc(sqrt(chi2_stat / 2.0))

    return round(chi2_stat, 4), round(p_value, 4)


# ── Single-variant runner ─────────────────────────────────────────────────────


def run_variant(
    spec: VariantSpec,
    queries: list[dict],
    orchestrator,
    db_manager,
    run_id: str,
    verbose: bool = True,
    gold_cache: dict[str, Any] | None = None,
) -> list[dict]:
    """Run one ablation variant over *queries*; return per-query result dicts."""
    results: list[dict] = []

    if verbose:
        print(f"\n  ── {spec.id}: {spec.name} ──")

    for i, q in enumerate(queries, 1):
        row = run_query_item(
            spec,
            q,
            orchestrator,
            db_manager,
            run_id=run_id,
            gold_cache=gold_cache,
        )
        elapsed = row["elapsed_s"]
        ex = row["ex"]
        status = "✓" if ex else "✗"

        if verbose:
            cost_str = (
                f"  ${row.get('total_cost_usd', 0):.4f}"
                if row.get("total_cost_usd", 0)
                else ""
            )
            print(
                f"    [{i:02d}/{len(queries)}] {status} {row['id']} "
                f"({row['difficulty']:6}) {elapsed:5.1f}s{cost_str}  "
                f"{row['question'][:45]}"
            )
            if not ex and row["error"]:
                print(f"           → {row['error'][:80]}")

        results.append(row)

    return results


def run_query_item(
    spec: VariantSpec,
    q: dict[str, Any],
    orchestrator,
    db_manager,
    *,
    run_id: str,
    gold_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one (variant, query) item and return the canonical detail row."""
    qid = q["id"]
    question = q["question"]
    gold_sql = q["query"]
    difficulty = q["difficulty"]

    t0 = time.time()
    ex = False
    generated_sql = ""
    error_msg = ""
    comparison: dict[str, Any] = {}
    agent_result_source = "results"
    session_id = f"ablation_{run_id}_{spec.id}_{qid}"

    cost: dict[str, Any] = {}
    agent_metadata: dict[str, Any] = {}
    try:
        result = orchestrator.process_query(
            question,
            session_id=session_id,
            force_single_query=True,
        )
        generated_sql = result.get("sql_query", "") or ""
        agent_metadata = result.get("metadata", {}) or {}
        agent_rows = result.get("final_result_rows")
        if agent_rows is None:
            agent_rows = result.get("results", [])
        else:
            agent_result_source = "final_result_rows"
        cost = result.get("cost", {})

        if result.get("success"):
            gold_raw = _get_gold_raw(q, db_manager, gold_cache)
            comparison = compare_results(agent_rows, gold_raw)
            ex = bool(comparison["match"])
    except Exception as exc:
        error_msg = str(exc)

    elapsed = round(time.time() - t0, 2)
    return {
        "id": qid,
        "difficulty": difficulty,
        "question": question,
        "gold_sql": gold_sql,
        "generated_sql": generated_sql,
        "ex": ex,
        "elapsed_s": elapsed,
        "error": error_msg,
        "session_id": session_id,
        "agent_result_source": agent_result_source,
        "gold_row_count": comparison.get("gold_row_count", 0),
        "predicted_row_count": comparison.get("predicted_row_count", 0),
        "gold_rows_sample": json.dumps(
            comparison.get("gold_rows_sample", []), ensure_ascii=False
        ),
        "predicted_rows_sample": json.dumps(
            comparison.get("predicted_rows_sample", []), ensure_ascii=False
        ),
        "comparison_details": json.dumps(comparison.get("details", {}), ensure_ascii=False),
        "variant_id": spec.id,
        "variant_name": spec.name,
        "critical_rule": q.get("critical_rule"),
        "workflow_success": bool(agent_metadata.get("workflow_metrics", {}).get("overall_success")),
        "semantic_plan": json.dumps(agent_metadata.get("semantic_plan", {}), ensure_ascii=False),
        "semantic_validation": json.dumps(
            agent_metadata.get("semantic_validation", {}), ensure_ascii=False
        ),
        "semantic_error": json.dumps(agent_metadata.get("semantic_error", {}), ensure_ascii=False),
        "semantic_repair": json.dumps(agent_metadata.get("semantic_repair", {}), ensure_ascii=False),
        "repair_attempts": json.dumps(agent_metadata.get("repair_attempts", []), ensure_ascii=False),
        "llamaindex_mode": agent_metadata.get("llamaindex_mode"),
        "llamaindex_retrieval_mode": agent_metadata.get("llamaindex_retrieval_mode"),
        "llamaindex_selected_tables": json.dumps(
            agent_metadata.get("llamaindex_selected_tables", []), ensure_ascii=False
        ),
        "sql_generation_source": agent_metadata.get("sql_generation_source"),
        "latency_by_component": json.dumps(
            agent_metadata.get("latency_by_component", {}), ensure_ascii=False
        ),
        "prompt_tokens": cost.get("prompt_tokens", 0),
        "completion_tokens": cost.get("completion_tokens", 0),
        "total_tokens": cost.get("total_tokens", 0),
        "total_cost_usd": cost.get("total_cost_usd", 0.0),
    }


def _get_worker_orchestrator(spec: VariantSpec):
    cache = getattr(_WORKER_LOCAL, "orchestrators", None)
    if cache is None:
        cache = {}
        _WORKER_LOCAL.orchestrators = cache
    if spec.id not in cache:
        from src.agent.orchestrator import LangGraphOrchestrator
        from src.application.config.simple_config import ApplicationConfig, OrchestratorConfig

        orch_config = OrchestratorConfig(**spec.flags) if spec.flags else OrchestratorConfig()
        orch_config.ablation_variant = spec.name
        orchestrator = LangGraphOrchestrator(
            ApplicationConfig(),
            orchestrator_config=orch_config,
        )
        db_manager = orchestrator._llm_manager  # type: ignore[attr-defined]
        cache[spec.id] = (orchestrator, db_manager)
    return cache[spec.id]


def _run_item_in_worker(
    spec_id: str,
    q: dict[str, Any],
    run_id: str,
    gold_cache: dict[str, Any] | None,
) -> dict[str, Any]:
    """Thread worker entrypoint; reuses one orchestrator per variant per worker."""
    spec = VARIANT_MAP[spec_id]
    t0 = time.time()
    try:
        orchestrator, db_manager = _get_worker_orchestrator(spec)
        return run_query_item(
            spec,
            q,
            orchestrator,
            db_manager,
            run_id=run_id,
            gold_cache=gold_cache,
        )
    except Exception as exc:
        elapsed = round(time.time() - t0, 2)
        return {
            "id": q["id"],
            "difficulty": q["difficulty"],
            "question": q["question"],
            "gold_sql": q["query"],
            "generated_sql": "",
            "ex": False,
            "elapsed_s": elapsed,
            "error": str(exc),
            "session_id": f"ablation_{run_id}_{spec.id}_{q['id']}",
            "agent_result_source": "results",
            "gold_row_count": 0,
            "predicted_row_count": 0,
            "gold_rows_sample": "[]",
            "predicted_rows_sample": "[]",
            "comparison_details": "{}",
            "variant_id": spec.id,
            "variant_name": spec.name,
            "critical_rule": q.get("critical_rule"),
            "workflow_success": False,
            "semantic_plan": "{}",
            "semantic_validation": "{}",
            "semantic_error": "{}",
            "semantic_repair": "{}",
            "repair_attempts": "[]",
            "llamaindex_mode": None,
            "llamaindex_retrieval_mode": None,
            "llamaindex_selected_tables": "[]",
            "sql_generation_source": None,
            "latency_by_component": "{}",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
        }


def _load_item_result(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    result = payload.get("result") if isinstance(payload, dict) else None
    return result if isinstance(result, dict) else None


def _write_item_result(
    path: Path,
    result: dict[str, Any],
    *,
    run_ts: str,
    run_id: str,
    git_sha: str,
    model_id: str,
) -> None:
    _atomic_write_json(
        path,
        {
            "schema_version": 1,
            "run_ts": run_ts,
            "run_id": run_id,
            "git_sha": git_sha,
            "model_id": model_id,
            "variant_id": result["variant_id"],
            "variant_name": result["variant_name"],
            "query_id": result["id"],
            "result": result,
        },
    )


def _collect_item_results(
    selected_specs: list[VariantSpec],
    queries: list[dict],
    items_dir: Path,
) -> dict[str, list[dict]]:
    all_results: dict[str, list[dict]] = {}
    for spec in selected_specs:
        variant_results: list[dict] = []
        for q in sorted(queries, key=_query_sort_key):
            result = _load_item_result(_item_path(items_dir, spec, q["id"]))
            if result is not None:
                variant_results.append(result)
        all_results[spec.id] = variant_results
    return all_results


def _write_variant_jsons(
    out_dir: Path,
    selected_specs: list[VariantSpec],
    all_results: dict[str, list[dict]],
    *,
    run_ts: str,
    run_id: str,
    git_sha: str,
    model_id: str,
) -> None:
    for spec in selected_specs:
        variant_results = all_results.get(spec.id, [])
        _atomic_write_json(
            out_dir / f"{spec.id}_{spec.name}.json",
            {
                "variant_id": spec.id,
                "variant_name": spec.name,
                "flags": spec.flags,
                "run_ts": run_ts,
                "run_id": run_id,
                "git_sha": git_sha,
                "model_id": model_id,
                "n_queries": len(variant_results),
                "ex_overall": _overall_ex(variant_results),
                "ex_by_tier": _ex_by_tier(variant_results),
                "queries": variant_results,
            },
        )


def _run_missing_items(
    selected_specs: list[VariantSpec],
    queries: list[dict],
    *,
    out_dir: Path,
    run_ts: str,
    run_id: str,
    git_sha: str,
    model_id: str,
    workers: int,
    resume: bool,
    gold_cache: dict[str, Any] | None,
    verbose: bool,
) -> None:
    items_dir = out_dir / "items"
    pending_by_spec: dict[str, list[tuple[VariantSpec, dict[str, Any], Path]]] = {}
    resumed = 0
    for spec in selected_specs:
        for q in queries:
            path = _item_path(items_dir, spec, q["id"])
            if resume and _load_item_result(path) is not None:
                resumed += 1
                continue
            pending_by_spec.setdefault(spec.id, []).append((spec, q, path))

    total_items = len(selected_specs) * len(queries)
    pending_count = sum(len(items) for items in pending_by_spec.values())
    if verbose:
        print(
            f"  Item checkpoints: {resumed}/{total_items} reusable, "
            f"{pending_count} pending"
        )
        if workers > 1:
            print("  Parallelism: queries run in parallel inside each variant; variants remain sequential")
    if not pending_count:
        return

    completed = 0
    for spec in selected_specs:
        pending = pending_by_spec.get(spec.id, [])
        if not pending:
            continue
        if verbose:
            print(f"\n  ── {spec.id}: {spec.name} ({len(pending)} pending) ──")

        if workers <= 1:
            for spec_, q, path in pending:
                result = _run_item_in_worker(spec_.id, q, run_id, gold_cache)
                _write_item_result(
                    path,
                    result,
                    run_ts=run_ts,
                    run_id=run_id,
                    git_sha=git_sha,
                    model_id=model_id,
                )
                completed += 1
                if verbose:
                    status = "✓" if result["ex"] else "✗"
                    print(
                        f"    [{completed:03d}/{pending_count}] {status} {spec_.id} {q['id']} "
                        f"{result['elapsed_s']:5.1f}s"
                    )
            continue

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(_run_item_in_worker, spec_.id, q, run_id, gold_cache): (
                    spec_,
                    q,
                    path,
                )
                for spec_, q, path in pending
            }
            for future in concurrent.futures.as_completed(future_map):
                spec_, q, path = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "id": q["id"],
                        "difficulty": q["difficulty"],
                        "question": q["question"],
                        "gold_sql": q["query"],
                        "generated_sql": "",
                        "ex": False,
                        "elapsed_s": 0,
                        "error": str(exc),
                        "session_id": f"ablation_{run_id}_{spec_.id}_{q['id']}",
                        "agent_result_source": "results",
                        "gold_row_count": 0,
                        "predicted_row_count": 0,
                        "gold_rows_sample": "[]",
                        "predicted_rows_sample": "[]",
                        "comparison_details": "{}",
                        "variant_id": spec_.id,
                        "variant_name": spec_.name,
                        "critical_rule": q.get("critical_rule"),
                        "workflow_success": False,
                        "semantic_plan": "{}",
                        "semantic_validation": "{}",
                        "semantic_error": "{}",
                        "semantic_repair": "{}",
                        "repair_attempts": "[]",
                        "llamaindex_mode": None,
                        "llamaindex_retrieval_mode": None,
                        "llamaindex_selected_tables": "[]",
                        "sql_generation_source": None,
                        "latency_by_component": "{}",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "total_cost_usd": 0.0,
                    }
                _write_item_result(
                    path,
                    result,
                    run_ts=run_ts,
                    run_id=run_id,
                    git_sha=git_sha,
                    model_id=model_id,
                )
                completed += 1
                if verbose:
                    status = "✓" if result["ex"] else "✗"
                    cost = result.get("total_cost_usd", 0.0)
                    cost_str = f" ${cost:.4f}" if cost else ""
                    print(
                        f"    [{completed:03d}/{pending_count}] {status} {spec_.id} {q['id']} "
                        f"{result['elapsed_s']:5.1f}s{cost_str}"
                    )


# ── Summary helpers ───────────────────────────────────────────────────────────


def _ex_by_tier(results: list[dict]) -> dict[str, float]:
    by_tier: dict[str, dict[str, int]] = {}
    for r in results:
        d = r["difficulty"]
        s = by_tier.setdefault(d, {"correct": 0, "total": 0})
        s["total"] += 1
        if r["ex"]:
            s["correct"] += 1
    return {
        tier: round(v["correct"] / v["total"], 4) if v["total"] else 0.0
        for tier, v in by_tier.items()
    }


def _overall_ex(results: list[dict]) -> float:
    if not results:
        return 0.0
    return round(sum(1 for r in results if r["ex"]) / len(results), 4)


# ── Report generation ─────────────────────────────────────────────────────────


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    path: Path,
    summary_rows: list[dict],
    run_ts: str,
    run_id: str,
    git_sha: str,
    model_id: str,
    n_queries: int,
) -> None:
    lines = [
        "# Ablation Study Report",
        "",
        f"- **Date**: {run_ts}",
        f"- **Run ID**: {run_id}",
        f"- **Git SHA**: {git_sha}",
        f"- **Model**: {model_id}",
        f"- **Queries per variant**: {n_queries}",
        "",
        "## Results",
        "",
        "| ID | Variant | EX (%) | ΔEX (pp) | Easy | Medium | Hard | χ² | p-value | Tokens | Cost ($) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    v0_row = next((r for r in summary_rows if r["variant_id"] == "V0"), None)
    v0_ex = v0_row["ex_overall"] if v0_row else 0.0

    for r in summary_rows:
        delta = round((r["ex_overall"] - v0_ex) * 100, 1) if r["variant_id"] != "V0" else "—"
        delta_str = f"{delta:+.1f}" if isinstance(delta, float) else delta
        chi2 = r.get("mcnemar_chi2", "—")
        pval = r.get("mcnemar_p", "—")
        chi2_str = f"{chi2:.3f}" if isinstance(chi2, float) else chi2
        pval_str = f"{pval:.3f}" if isinstance(pval, float) else pval
        tokens = r.get("total_tokens", 0)
        cost = r.get("total_cost_usd", 0.0)
        lines.append(
            f"| {r['variant_id']} | {r['variant_name']} "
            f"| {r['ex_overall'] * 100:.1f} | {delta_str} "
            f"| {r.get('ex_easy', 0) * 100:.1f} "
            f"| {r.get('ex_medium', 0) * 100:.1f} "
            f"| {r.get('ex_hard', 0) * 100:.1f} "
            f"| {chi2_str} | {pval_str} "
            f"| {tokens:,} | {cost:.4f} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- ΔEX = variant EX − V0 EX (full pipeline)",
        "- Session IDs include Run ID to avoid LangGraph checkpoint reuse across ablation runs",
        "- results_detail.csv includes EX comparison row counts, samples, and mismatch details",
        "- McNemar mid-p test (exact) when discordant pairs < 25, chi-square continuity correction otherwise",
        "- p < 0.05 suggests the component has a statistically significant impact on EX",
        "",
        "## Decision Table",
        "",
        "| Result | Decision |",
        "|---|---|",
        "| ΔEX ≈ 0 pp, p > 0.05 | Candidate for removal / simplification |",
        "| ΔEX < −3 pp, p < 0.05 | Keep component |",
        "| ΔEX < −3 pp, p > 0.05 | Effect present but not significant — keep, rerun with more queries |",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_summary_and_detail_rows(
    selected_specs: list[VariantSpec],
    all_results: dict[str, list[dict]],
    run_id: str,
) -> tuple[list[dict], list[dict]]:
    """Build aggregate CSV rows from per-variant result dictionaries."""
    v0_results = all_results.get("V0", [])
    v0_correct = [r["ex"] for r in v0_results]
    v0_ex = _overall_ex(v0_results)

    summary_rows: list[dict] = []
    detail_rows: list[dict] = []

    for spec in selected_specs:
        results = all_results[spec.id]
        ex_overall = _overall_ex(results)
        tier_ex = _ex_by_tier(results)
        vi_correct = [r["ex"] for r in results]

        chi2, pval = (None, None)
        if spec.id != "V0" and v0_correct and len(v0_correct) == len(vi_correct):
            chi2, pval = _mcnemar(v0_correct, vi_correct)

        total_tokens = sum(r.get("total_tokens", 0) for r in results)
        total_cost = round(sum(r.get("total_cost_usd", 0.0) for r in results), 6)
        avg_tokens = round(total_tokens / len(results)) if results else 0

        summary_rows.append(
            {
                "variant_id": spec.id,
                "variant_name": spec.name,
                "run_id": run_id,
                "description": spec.description,
                "flags": json.dumps(spec.flags),
                "n_queries": len(results),
                "ex_overall": ex_overall,
                "ex_easy": tier_ex.get("easy", 0.0),
                "ex_medium": tier_ex.get("medium", 0.0),
                "ex_hard": tier_ex.get("hard", 0.0),
                "delta_ex_pp": round((ex_overall - v0_ex) * 100, 2)
                if spec.id != "V0"
                else 0.0,
                "mcnemar_chi2": chi2,
                "mcnemar_p": pval,
                "total_tokens": total_tokens,
                "avg_tokens_per_query": avg_tokens,
                "total_cost_usd": total_cost,
            }
        )

        for r in results:
            detail_rows.append({**r, "flags": json.dumps(spec.flags)})

    return summary_rows, detail_rows


def _print_summary_table(summary_rows: list[dict]) -> None:
    has_cost = any(r.get("total_cost_usd", 0) > 0 for r in summary_rows)
    print(f"\n{'━' * 72}")
    header = f"  {'ID':<4} {'Variant':<28} {'EX':>6} {'ΔEX':>7} {'p':>7}"
    if has_cost:
        header += f"  {'Tokens':>8}  {'Cost $':>8}"
    print(header)
    print(f"  {'─' * 68}")
    for row in summary_rows:
        delta_str = f"{row['delta_ex_pp']:+.1f}" if row["variant_id"] != "V0" else "  —  "
        pval_str = f"{row['mcnemar_p']:.3f}" if row["mcnemar_p"] is not None else "  —  "
        line = (
            f"  {row['variant_id']:<4} {row['variant_name']:<28} "
            f"{row['ex_overall'] * 100:>5.1f}% {delta_str:>7}pp {pval_str:>7}"
        )
        if has_cost:
            line += f"  {row.get('total_tokens', 0):>8,}  {row.get('total_cost_usd', 0):>8.4f}"
        print(line)
    print(f"{'━' * 62}\n")


SUMMARY_FIELDS = [
    "variant_id",
    "variant_name",
    "run_id",
    "description",
    "flags",
    "n_queries",
    "ex_overall",
    "ex_easy",
    "ex_medium",
    "ex_hard",
    "delta_ex_pp",
    "mcnemar_chi2",
    "mcnemar_p",
    "total_tokens",
    "avg_tokens_per_query",
    "total_cost_usd",
]

DETAIL_FIELDS = [
    "variant_id",
    "variant_name",
    "id",
    "difficulty",
    "question",
    "gold_sql",
    "generated_sql",
    "ex",
    "elapsed_s",
    "error",
    "session_id",
    "agent_result_source",
    "gold_row_count",
    "predicted_row_count",
    "gold_rows_sample",
    "predicted_rows_sample",
    "comparison_details",
    "critical_rule",
    "workflow_success",
    "semantic_plan",
    "semantic_validation",
    "semantic_error",
    "semantic_repair",
    "repair_attempts",
    "llamaindex_mode",
    "llamaindex_retrieval_mode",
    "llamaindex_selected_tables",
    "sql_generation_source",
    "latency_by_component",
    "flags",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "total_cost_usd",
]


def _write_aggregate_outputs(
    out_dir: Path,
    summary_rows: list[dict],
    detail_rows: list[dict],
    *,
    run_ts: str,
    run_id: str,
    git_sha: str,
    model_id: str,
    n_queries: int,
) -> None:
    _write_csv(out_dir / "results.csv", summary_rows, SUMMARY_FIELDS)
    _write_csv(out_dir / "results_detail.csv", detail_rows, DETAIL_FIELDS)
    _write_report(
        out_dir / "report.md",
        summary_rows,
        run_ts=run_ts,
        run_id=run_id,
        git_sha=git_sha,
        model_id=model_id,
        n_queries=n_queries,
    )


def rebuild_outputs_from_variant_jsons(
    output_dir: str,
    variant_ids: list[str] | None = None,
    verbose: bool = True,
) -> dict:
    """Rebuild summary CSVs/report from existing per-variant JSON files."""
    out_dir = Path(output_dir)
    if not out_dir.exists():
        sys.exit(f"[ERROR] Output directory not found: {out_dir}")

    selected_specs = (
        [VARIANT_MAP[vid] for vid in variant_ids if vid in VARIANT_MAP] if variant_ids else VARIANTS
    )
    metadata_path = out_dir / "run_metadata.json"
    items_dir = out_dir / "items"
    if metadata_path.exists() and items_dir.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        dataset_path = metadata.get("dataset_path")
        queries = _load_regression_set(
            tier=metadata.get("tier"),
            max_queries=metadata.get("max_queries"),
            dataset_path=dataset_path,
        )
        if variant_ids is None and metadata.get("variants"):
            selected_specs = [VARIANT_MAP[vid] for vid in metadata["variants"] if vid in VARIANT_MAP]
        all_results = _collect_item_results(selected_specs, queries, items_dir)
        loaded_specs = [spec for spec in selected_specs if all_results.get(spec.id)]
        if loaded_specs:
            run_id = str(metadata.get("run_id") or "unknown")
            run_ts = str(metadata.get("run_ts") or _utc_now_iso())
            git_sha = str(metadata.get("git_sha") or _git_sha())
            model_id = str(metadata.get("model_id") or "unknown")
            _write_variant_jsons(
                out_dir,
                loaded_specs,
                all_results,
                run_ts=run_ts,
                run_id=run_id,
                git_sha=git_sha,
                model_id=model_id,
            )
            summary_rows, detail_rows = _build_summary_and_detail_rows(
                loaded_specs,
                all_results,
                run_id,
            )
            _print_summary_table(summary_rows)
            _write_aggregate_outputs(
                out_dir,
                summary_rows,
                detail_rows,
                run_ts=run_ts,
                run_id=run_id,
                git_sha=git_sha,
                model_id=model_id,
                n_queries=max((len(results) for results in all_results.values()), default=0),
            )
            print(f"  Rebuilt aggregate outputs from item checkpoints → {out_dir}/")
            print("    report.md | results.csv | results_detail.csv | per-variant JSON\n")
            return {
                "run_ts": run_ts,
                "run_id": run_id,
                "git_sha": git_sha,
                "model_id": model_id,
                "output_dir": str(out_dir),
                "summary": summary_rows,
                "missing_variants": [spec.id for spec in selected_specs if not all_results.get(spec.id)],
            }

    all_results: dict[str, list[dict]] = {}
    metadata: dict[str, Any] | None = None
    loaded_specs: list[VariantSpec] = []
    missing: list[str] = []

    for spec in selected_specs:
        variant_json = out_dir / f"{spec.id}_{spec.name}.json"
        if not variant_json.exists():
            missing.append(spec.id)
            continue
        with open(variant_json, encoding="utf-8") as f:
            payload = json.load(f)
        if metadata is None:
            metadata = payload
        all_results[spec.id] = payload.get("queries", [])
        loaded_specs.append(spec)

    if not loaded_specs:
        sys.exit(f"[ERROR] No per-variant JSON files found in {out_dir}")

    if missing and verbose:
        print(f"[WARN] Missing variant JSON files: {', '.join(missing)}")

    run_id = str((metadata or {}).get("run_id") or "unknown")
    run_ts = str((metadata or {}).get("run_ts") or _utc_now_iso())
    git_sha = str((metadata or {}).get("git_sha") or _git_sha())
    model_id = str((metadata or {}).get("model_id") or "unknown")
    n_queries = max((len(results) for results in all_results.values()), default=0)

    summary_rows, detail_rows = _build_summary_and_detail_rows(
        loaded_specs,
        all_results,
        run_id,
    )
    _print_summary_table(summary_rows)
    _write_aggregate_outputs(
        out_dir,
        summary_rows,
        detail_rows,
        run_ts=run_ts,
        run_id=run_id,
        git_sha=git_sha,
        model_id=model_id,
        n_queries=n_queries,
    )

    print(f"  Rebuilt aggregate outputs from {len(loaded_specs)} variant JSON files → {out_dir}/")
    print("    report.md | results.csv | results_detail.csv\n")

    return {
        "run_ts": run_ts,
        "run_id": run_id,
        "git_sha": git_sha,
        "model_id": model_id,
        "output_dir": str(out_dir),
        "summary": summary_rows,
        "missing_variants": missing,
    }


# ── Main runner ───────────────────────────────────────────────────────────────


def run_ablation(
    variant_ids: list[str] | None = None,
    max_queries: int | None = None,
    tier: str | None = None,
    dataset_path: str | None = None,
    output_dir: str | None = None,
    run_id: str | None = None,
    workers: int = 1,
    resume: bool = True,
    use_gold_cache: bool = True,
    refresh_gold_cache: bool = False,
    verbose: bool = True,
) -> dict:
    if not os.getenv("DATABASE_URL") and not os.getenv("DATABASE_PATH"):
        sys.exit(
            "[ERROR] DATABASE_URL or DATABASE_PATH not set. Ablation requires a live database."
        )
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("[ERROR] OPENAI_API_KEY not set.")

    from src.agent.orchestrator import LangGraphOrchestrator
    from src.application.config.simple_config import ApplicationConfig

    run_ts = _utc_now_iso()
    git_sha = _git_sha()

    ts_tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    explicit_run_id = run_id is not None
    run_id = run_id or f"{ts_tag}_{uuid4().hex[:8]}"
    out_dir = (
        Path(output_dir)
        if output_dir
        else ROOT / "evaluation" / "ablation" / "results" / f"ablation_{ts_tag}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = out_dir / "run_metadata.json"
    if resume and metadata_path.exists():
        try:
            previous_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_metadata = {}
        if not explicit_run_id and previous_metadata.get("run_id"):
            run_id = str(previous_metadata["run_id"])
        if previous_metadata.get("run_ts"):
            run_ts = str(previous_metadata["run_ts"])

    selected_specs = (
        [VARIANT_MAP[vid] for vid in variant_ids if vid in VARIANT_MAP] if variant_ids else VARIANTS
    )
    if not selected_specs:
        sys.exit(f"[ERROR] No valid variant IDs in: {variant_ids}")

    dataset = _resolve_dataset_path(dataset_path)
    queries = _load_regression_set(tier=tier, max_queries=max_queries, dataset_path=str(dataset))
    if not queries:
        sys.exit("[ERROR] No queries loaded.")

    base_app_config = ApplicationConfig()
    model_id = base_app_config.llm_model

    init_mlflow(experiment_name="txt2sql-ablation")

    print(f"\n{'━' * 62}")
    print("  Ablation Study")
    print(f"  Variants : {[s.id for s in selected_specs]}")
    print(f"  Dataset  : {dataset}")
    print(f"  Queries  : {len(queries)}")
    print(f"  Workers  : {max(workers, 1)}  |  Resume: {resume}  |  Gold cache: {use_gold_cache}")
    print(f"  Run ID   : {run_id}")
    print(f"  Model    : {model_id}  |  SHA: {git_sha}")
    print(f"  Output   : {out_dir}")
    print(f"{'━' * 62}")

    _atomic_write_json(
        metadata_path,
        {
            "run_ts": run_ts,
            "run_id": run_id,
            "git_sha": git_sha,
            "model_id": model_id,
            "dataset_path": str(dataset),
            "max_queries": max_queries,
            "tier": tier,
            "variants": [spec.id for spec in selected_specs],
            "workers": max(workers, 1),
            "resume": resume,
            "gold_cache": use_gold_cache,
        },
    )

    gold_cache: dict[str, Any] | None = None
    if use_gold_cache:
        gold_cache_path = out_dir / "gold_cache.json"
        existing_cache = {} if refresh_gold_cache else _load_gold_cache(gold_cache_path)
        missing_gold = [q for q in queries if _gold_cache_key(q) not in existing_cache]
        if missing_gold or refresh_gold_cache:
            base_orchestrator = LangGraphOrchestrator(ApplicationConfig())
            db_manager = base_orchestrator._llm_manager  # type: ignore[attr-defined]
            gold_cache = _prepare_gold_cache(
                queries,
                db_manager,
                gold_cache_path,
                dataset,
                refresh=refresh_gold_cache,
                verbose=verbose,
            )
        else:
            gold_cache = existing_cache
            if verbose:
                print(f"  Gold cache: {len(queries)} cached, 0 missing")

    _run_missing_items(
        selected_specs,
        queries,
        out_dir=out_dir,
        run_ts=run_ts,
        run_id=run_id,
        git_sha=git_sha,
        model_id=model_id,
        workers=max(workers, 1),
        resume=resume,
        gold_cache=gold_cache,
        verbose=verbose,
    )

    all_results = _collect_item_results(selected_specs, queries, out_dir / "items")
    _write_variant_jsons(
        out_dir,
        selected_specs,
        all_results,
        run_ts=run_ts,
        run_id=run_id,
        git_sha=git_sha,
        model_id=model_id,
    )

    # ── Summary + outputs ────────────────────────────────────────────────────
    summary_rows, detail_rows = _build_summary_and_detail_rows(
        selected_specs,
        all_results,
        run_id,
    )
    _print_summary_table(summary_rows)
    _write_aggregate_outputs(
        out_dir,
        summary_rows,
        detail_rows,
        run_ts=run_ts,
        run_id=run_id,
        git_sha=git_sha,
        model_id=model_id,
        n_queries=len(queries),
    )

    # ── Log each variant to MLflow ────────────────────────────────────────────
    for row in summary_rows:
        log_ablation_run(
            variant_id=row["variant_id"],
            variant_name=row["variant_name"],
            flags=json.loads(row["flags"]),
            ex_overall=row["ex_overall"],
            ex_by_tier={
                "easy": row.get("ex_easy", 0.0),
                "medium": row.get("ex_medium", 0.0),
                "hard": row.get("ex_hard", 0.0),
            },
            delta_ex_pp=row["delta_ex_pp"],
            mcnemar_chi2=row.get("mcnemar_chi2"),
            mcnemar_p=row.get("mcnemar_p"),
            n_queries=row["n_queries"],
            git_sha=git_sha,
            model_id=model_id,
            results_csv_path=str(out_dir / "results.csv"),
            total_tokens=row.get("total_tokens", 0),
            total_cost_usd=row.get("total_cost_usd", 0.0),
        )

    print(f"  Results saved → {out_dir}/")
    print("    report.md | results.csv | results_detail.csv")
    print(f"    + {len(selected_specs)} per-variant JSON files\n")

    return {
        "run_ts": run_ts,
        "run_id": run_id,
        "git_sha": git_sha,
        "model_id": model_id,
        "output_dir": str(out_dir),
        "summary": summary_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="TXT2SQL ablation runner")
    parser.add_argument(
        "--variants",
        nargs="+",
        default=None,
        metavar="ID",
        help="Variant IDs to run (e.g. V0 V2 V3). Default: all.",
    )
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument("--tier", choices=["easy", "medium", "hard"], default=None)
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Evaluation dataset JSON. Default: evaluation/regression_set.json.",
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel query workers inside each variant. Variants remain sequential.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional unique run ID for LangGraph session IDs. Defaults to timestamp + random suffix.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Rerun all items even when item checkpoints already exist.",
    )
    parser.add_argument(
        "--no-gold-cache",
        action="store_true",
        help="Disable shared gold SQL result cache and execute gold SQL per item.",
    )
    parser.add_argument(
        "--refresh-gold-cache",
        action="store_true",
        help="Recompute gold SQL cache before running agent items.",
    )
    parser.add_argument(
        "--rebuild-report-only",
        action="store_true",
        help="Rebuild results.csv, results_detail.csv, and report.md from existing per-variant JSON files.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.rebuild_report_only:
        if not args.output:
            sys.exit("[ERROR] --rebuild-report-only requires --output")
        rebuild_outputs_from_variant_jsons(
            output_dir=args.output,
            variant_ids=args.variants,
            verbose=not args.quiet,
        )
        sys.exit(0)

    run_ablation(
        variant_ids=args.variants,
        max_queries=args.max_queries,
        tier=args.tier,
        dataset_path=args.dataset,
        output_dir=args.output,
        run_id=args.run_id,
        workers=args.workers,
        resume=not args.no_resume,
        use_gold_cache=not args.no_gold_cache,
        refresh_gold_cache=args.refresh_gold_cache,
        verbose=not args.quiet,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
