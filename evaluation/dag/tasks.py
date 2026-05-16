"""
Task Functions for Evaluation Pipeline DAG

This module contains all task functions used in the evaluation pipeline.
Each task is a standalone function that takes inputs from previous tasks
and returns data for downstream tasks.
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

TRACE_PREVIEW_ROW_LIMIT = 20
TRACE_SCHEMA_VERSION = 2

from evaluation.metrics.base_metrics import EvaluationContext  # noqa: E402
from evaluation.metrics.execution_accuracy import ExecutionAccuracyMetric  # noqa: E402
from src.agent.llamaindex_context import normalize_llamaindex_mode  # noqa: E402
from src.agent.orchestrator import LangGraphOrchestrator  # noqa: E402
from src.application.config.simple_config import ApplicationConfig, OrchestratorConfig  # noqa: E402

# ============================================================================
# Configuration and Initialization Tasks
# ============================================================================


def load_configuration(**kwargs) -> Dict[str, Any]:
    """
    Load application configuration

    Returns:
        Dict containing configuration objects
    """
    print("  Loading application configuration...")

    config = ApplicationConfig()

    return {"config": config, "llm_provider": config.llm_provider, "llm_model": config.llm_model}


def load_ground_truth(**kwargs) -> Dict[str, Any]:
    """
    Load ground truth questions from JSON file

    Returns:
        Dict containing questions list and metadata
    """
    print("  Loading ground truth data...")

    ground_truth_path = kwargs.get("ground_truth_path") or "evaluation/ground_truth.json"
    gt_path = Path(ground_truth_path)
    if not gt_path.is_absolute():
        gt_path = project_root / gt_path

    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    with open(gt_path, "r", encoding="utf-8") as f:
        raw_questions = json.load(f)

    if isinstance(raw_questions, dict):
        questions_data = raw_questions.get("questions")
        if questions_data is None:
            raise ValueError("Ground truth JSON object must contain a 'questions' list")
    else:
        questions_data = raw_questions

    if not isinstance(questions_data, list):
        raise ValueError("Ground truth data must be a list of question objects")

    questions = [
        _normalize_ground_truth_question(item, index)
        for index, item in enumerate(questions_data, start=1)
    ]

    # Calculate statistics
    difficulty_counts = {}
    for q in questions:
        diff = q.get("difficulty", "unknown")
        difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1

    print(f"    Loaded {len(questions)} questions")
    print(f"    Difficulty breakdown: {difficulty_counts}")

    return {
        "questions": questions,
        "ground_truth_path": str(gt_path),
        "total_count": len(questions),
        "difficulty_breakdown": difficulty_counts,
    }


def _normalize_ground_truth_question(item: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Normalize supported ground-truth schemas to the DAG contract."""
    if not isinstance(item, dict):
        raise ValueError(f"Ground truth item #{index} must be an object")

    normalized = dict(item)
    normalized.setdefault(
        "id",
        item.get("question_id") or item.get("qid") or f"GT_{index:03d}",
    )

    question = item.get("question") or item.get("question_pt") or item.get("user_question")
    query = item.get("query") or item.get("sql") or item.get("ground_truth_sql")

    if question is not None:
        normalized["question"] = question
    if query is not None:
        normalized["query"] = query

    if "difficulty" not in normalized:
        normalized["difficulty"] = item.get("level") or item.get("complexity") or "unknown"

    if "tables" not in normalized:
        tables = item.get("tables_used") or item.get("gold_tables")
        if tables is not None:
            normalized["tables"] = tables

    missing = [
        key
        for key in ("id", "question", "query", "difficulty")
        if normalized.get(key) in (None, "")
    ]
    if missing:
        raise ValueError(
            f"Ground truth item #{index} is missing required fields after "
            f"normalization: {', '.join(missing)}"
        )

    return normalized


def initialize_database(load_configuration: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    Initialize database connection

    Args:
        load_configuration: Configuration from load_configuration task

    Returns:
        Dict containing database connection wrapper
    """
    print("  Initializing database connection...")

    # Simple database wrapper (supports PostgreSQL and DuckDB)
    class SimpleDatabaseConnection:
        def __init__(self, db_url: str):
            self.db_url = db_url
            self.is_duckdb = db_url.startswith("duckdb")
            if self.is_duckdb:
                from sqlalchemy import create_engine

                # Use the same SQLAlchemy/duckdb-engine pathway as the agent
                # so both connections share identical DuckDB configuration
                self._engine = create_engine(db_url)
            else:
                import psycopg2

                self.connection = psycopg2.connect(db_url)

        def execute_query(self, sql: str):
            if self.is_duckdb:
                from sqlalchemy import text

                try:
                    with self._engine.connect() as conn:
                        result = conn.execute(text(sql))
                        try:
                            rows = [tuple(row) for row in result.fetchall()]
                            return rows, None
                        except Exception:
                            return [], None
                except Exception as e:
                    return None, str(e)
            else:
                try:
                    cursor = self.connection.cursor()
                    cursor.execute(sql)
                    try:
                        results = cursor.fetchall()
                        self.connection.commit()
                        return results, None
                    except Exception:
                        self.connection.commit()
                        return [], None
                except Exception as e:
                    self.connection.rollback()
                    return None, str(e)

        def execute_query_with_columns(self, sql: str):
            if self.is_duckdb:
                from sqlalchemy import text

                try:
                    with self._engine.connect() as conn:
                        result = conn.execute(text(sql))
                        columns = list(result.keys())
                        try:
                            rows = [tuple(row) for row in result.fetchall()]
                            return rows, columns, None
                        except Exception:
                            return [], columns, None
                except Exception as e:
                    return None, [], str(e)
            else:
                try:
                    cursor = self.connection.cursor()
                    cursor.execute(sql)
                    columns = [desc[0] for desc in cursor.description or []]
                    try:
                        results = cursor.fetchall()
                        self.connection.commit()
                        return results, columns, None
                    except Exception:
                        self.connection.commit()
                        return [], columns, None
                except Exception as e:
                    self.connection.rollback()
                    return None, [], str(e)

        def get_raw_connection(self):
            if self.is_duckdb:
                return self._engine.raw_connection()
            return self.connection

        def close(self):
            if self.is_duckdb:
                self._engine.dispose()
            elif hasattr(self, "connection") and self.connection:
                self.connection.close()

    # Get database URL
    db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PATH")

    if not db_url:
        raise ValueError("DATABASE_URL or DATABASE_PATH not found in environment")

    # Convert SQLAlchemy format to psycopg2 format if needed (PostgreSQL only)
    if "postgresql+psycopg2://" in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")

    db_connection = SimpleDatabaseConnection(db_url)

    print("    Database connected successfully")

    return {
        "db_connection": db_connection,
        "db_url_masked": db_url.split("@")[1] if "@" in db_url else db_url.split("///")[-1],
    }


def initialize_metrics(load_configuration: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    Initialize evaluation metrics

    Args:
        load_configuration: Configuration from load_configuration task

    Returns:
        Dict containing metric instances
    """
    print("  Initializing evaluation metrics...")

    ex_metric = ExecutionAccuracyMetric(execution_timeout=60)
    metrics = [ex_metric]

    print(f"    Initialized {len(metrics)} metrics:")
    for metric in metrics:
        print(f"      - {metric.name}")

    return {
        "metrics": metrics,
        "metric_names": [m.name for m in metrics],
        "ex_metric": ex_metric,
    }


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _build_llamaindex_orchestrator_config(**kwargs) -> OrchestratorConfig:
    raw_mode = kwargs.get("llamaindex_mode")
    if raw_mode is None:
        raw_mode = os.getenv("LLAMAINDEX_MODE") or "context"
    mode = normalize_llamaindex_mode(raw_mode)

    top_k = kwargs.get("llamaindex_top_k_tables")
    if top_k is None:
        top_k = _env_int("LLAMAINDEX_TOP_K_TABLES", 6)

    index_dir = (
        kwargs.get("llamaindex_index_dir")
        or os.getenv("LLAMAINDEX_INDEX_DIR")
        or ".llamaindex_schema"
    )

    rebuild_index = bool(kwargs.get("llamaindex_rebuild_index")) or _env_bool(
        "LLAMAINDEX_REBUILD_INDEX"
    )
    verify_schema_with_db = bool(kwargs.get("verify_llamaindex_schema_with_db")) or _env_bool(
        "VERIFY_LLAMAINDEX_SCHEMA_WITH_DB"
    )

    return OrchestratorConfig(
        enable_llamaindex_context=_env_bool("ENABLE_LLAMAINDEX_CONTEXT")
        or mode in {"context", "sql_draft", "hybrid"},
        enable_llamaindex_sql_draft=_env_bool("ENABLE_LLAMAINDEX_SQL_DRAFT") or mode == "sql_draft",
        llamaindex_mode=mode,
        llamaindex_top_k_tables=int(top_k),
        llamaindex_index_dir=str(index_dir),
        llamaindex_rebuild_index=rebuild_index,
        verify_llamaindex_schema_with_db=verify_schema_with_db,
    )


def initialize_agent(load_configuration: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    Initialize LangGraph agent orchestrator

    Args:
        load_configuration: Configuration from load_configuration task

    Returns:
        Dict containing agent instance
    """
    print("  Initializing LangGraph agent...")

    app_config = load_configuration["config"]
    orchestrator_config = _build_llamaindex_orchestrator_config(**kwargs)
    agent = LangGraphOrchestrator(app_config, orchestrator_config=orchestrator_config)

    print("    Agent initialized:")
    print(f"      Provider: {app_config.llm_provider}")
    print(f"      Model: {app_config.llm_model}")
    print(f"      LlamaIndex mode: {orchestrator_config.llamaindex_mode}")

    return {
        "agent": agent,
        "agent_config": {
            "provider": app_config.llm_provider,
            "model": app_config.llm_model,
            "llamaindex_mode": orchestrator_config.llamaindex_mode,
            "llamaindex_top_k_tables": orchestrator_config.llamaindex_top_k_tables,
            "llamaindex_index_dir": orchestrator_config.llamaindex_index_dir,
            "llamaindex_rebuild_index": orchestrator_config.llamaindex_rebuild_index,
            "verify_llamaindex_schema_with_db": orchestrator_config.verify_llamaindex_schema_with_db,
            "enable_llamaindex_context": orchestrator_config.enable_llamaindex_context,
            "enable_llamaindex_sql_draft": orchestrator_config.enable_llamaindex_sql_draft,
        },
    }


def preflight_ground_truth(
    load_ground_truth: Dict[str, Any], initialize_database: Dict[str, Any], **kwargs
) -> Dict[str, Any]:
    """
    Validate gold SQL against the active database before expensive agent calls.
    """
    print("  Preflighting ground truth SQL against active database...")

    db_connection = initialize_database["db_connection"]
    failures = []

    for question in load_ground_truth["questions"]:
        query = str(question.get("query", "")).strip()
        if not query:
            failures.append(
                {
                    "id": question.get("id", "UNKNOWN_ID"),
                    "error": "empty ground-truth SQL",
                }
            )
            continue

        explain_sql = f"EXPLAIN {query.rstrip(';')}"
        _rows, error = db_connection.execute_query(explain_sql)
        if error:
            failures.append(
                {
                    "id": question.get("id", "UNKNOWN_ID"),
                    "error": error,
                    "sql": query,
                }
            )

    if failures:
        preview = "; ".join(f"{item['id']}: {item['error']}" for item in failures[:5])
        raise ValueError(
            f"Ground truth SQL preflight failed for {len(failures)} question(s): {preview}"
        )

    print(f"    Preflight OK: {len(load_ground_truth['questions'])} SQL query(ies)")

    return {
        "checked_count": len(load_ground_truth["questions"]),
        "failed_count": 0,
        "failures": [],
    }


def _resolve_output_dir(run_id: str, requested_output_dir: str | None = None) -> Path:
    output_dir = (
        Path(requested_output_dir)
        if requested_output_dir
        else project_root / "evaluation" / "results" / f"dag_evaluation_{run_id}"
    )
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    return output_dir


def _safe_trace_id(question_id: Any) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(question_id or "UNKNOWN_ID")).strip("_")
    return safe_id or "UNKNOWN_ID"


def _query_trace_path(output_dir: Path, question_id: Any) -> Path:
    return output_dir / "queries" / _safe_trace_id(question_id) / "trace.json"


def _question_fingerprint(question_data: dict[str, Any]) -> str:
    payload = {
        "id": str(question_data.get("id") or ""),
        "question": str(question_data.get("question") or ""),
        "query": str(question_data.get("query") or ""),
        "difficulty": str(question_data.get("difficulty") or ""),
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _question_from_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result.get("question_id") or result.get("id") or "UNKNOWN_ID",
        "question": result.get("question") or "",
        "query": result.get("ground_truth_sql") or "",
        "difficulty": result.get("difficulty") or "unknown",
    }


def _question_counts_as_agent_success(result: dict[str, Any]) -> bool:
    return bool(result.get("agent_success")) and (
        bool((result.get("predicted_sql") or "").strip())
        or result.get("stored_rows") is not None
    )


def _accumulate_result_stats(
    *,
    result: dict[str, Any],
    metric_scores: dict[str, list],
    metrics: list,
    agent_stats: dict[str, Any],
) -> None:
    if _question_counts_as_agent_success(result):
        agent_stats["success_count"] += 1
    else:
        agent_stats["failure_count"] += 1

    try:
        agent_stats["total_time"] += float(result.get("agent_execution_time") or 0.0)
    except (TypeError, ValueError):
        pass

    result_metrics = result.get("metrics") or {}
    for metric in metrics:
        metric_result = result_metrics.get(metric.name)
        if not metric_result:
            continue
        try:
            metric_scores[metric.name].append(float(metric_result.get("score", 0.0)))
        except (TypeError, ValueError):
            metric_scores[metric.name].append(0.0)


def _summarize_agent_result(agent_result: Any) -> dict[str, Any]:
    if not isinstance(agent_result, dict):
        return {
            "type": type(agent_result).__name__,
            "text": str(agent_result),
        }

    rows = agent_result.get("results") or []
    return _json_safe(
        {
            "success": agent_result.get("success"),
            "sql_query": agent_result.get("sql_query"),
            "response": agent_result.get("response"),
            "row_count": agent_result.get("row_count"),
            "results_preview": list(rows[:TRACE_PREVIEW_ROW_LIMIT])
            if isinstance(rows, list)
            else rows,
            "final_result_rows_preview": list(
                (agent_result.get("final_result_rows") or [])[:TRACE_PREVIEW_ROW_LIMIT]
            )
            if isinstance(agent_result.get("final_result_rows"), list)
            else agent_result.get("final_result_rows"),
            "error": agent_result.get("error") or agent_result.get("error_message"),
            "cost": agent_result.get("cost"),
            "chart": agent_result.get("chart"),
        }
    )


def _load_completed_query_trace(
    *,
    output_dir: Path,
    question_data: dict[str, Any],
) -> dict[str, Any] | None:
    trace_path = _query_trace_path(output_dir, question_data.get("id"))
    if not trace_path.exists():
        return None

    try:
        with open(trace_path, encoding="utf-8") as f:
            trace_record = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    if trace_record.get("status") != "completed":
        return None
    if trace_record.get("question_fingerprint") != _question_fingerprint(question_data):
        return None

    detailed_result = trace_record.get("detailed_result")
    if not isinstance(detailed_result, dict):
        return None

    detailed_result = dict(detailed_result)
    detailed_result["trace_path"] = str(trace_path)
    detailed_result["resumed_from_trace"] = True
    return detailed_result


# ============================================================================
# Evaluation Execution Tasks
# ============================================================================


def evaluate_questions(
    load_ground_truth: Dict[str, Any],
    initialize_metrics: Dict[str, Any],
    initialize_agent: Dict[str, Any],
    initialize_database: Dict[str, Any],
    **kwargs,
) -> Dict[str, Any]:
    """
    Evaluate all questions using the agent and metrics

    Supports parallel execution to speed up evaluation.

    Args:
        load_ground_truth: Ground truth data
        initialize_metrics: Metric instances
        initialize_agent: Agent instance
        initialize_database: Database connection
        **kwargs: Can include 'max_workers' (default=1)
                  1=sequential, 2+=parallel
                  Recommended: 1-2 for GPU, 2-4 for CPU-only

    Returns:
        Dict containing detailed evaluation results
    """
    questions = load_ground_truth["questions"]
    metrics = initialize_metrics["metrics"]
    ex_metric = initialize_metrics.get("ex_metric")
    agent = initialize_agent["agent"]
    db_connection = initialize_database["db_connection"]

    # Get max_workers from kwargs (default to 1 for sequential)
    max_workers = kwargs.get("max_workers", 1)
    run_id = str(kwargs.get("run_id") or datetime.now().strftime("%Y%m%d_%H%M%S"))
    output_dir = _resolve_output_dir(run_id, kwargs.get("output_dir"))
    resume_enabled = bool(kwargs.get("resume") or kwargs.get("resume_run_id"))
    force_rerun = bool(kwargs.get("force_rerun"))

    total = len(questions)

    # Determine execution mode
    if max_workers > 1:
        print(f"  Evaluating {total} questions with {max_workers} parallel workers...")
        print("    ⚠️  Using parallel mode - monitor GPU memory!")
        return _evaluate_questions_parallel(
            questions,
            metrics,
            agent,
            db_connection,
            max_workers,
            ex_metric=ex_metric,
            run_id=run_id,
            output_dir=output_dir,
            resume_enabled=resume_enabled,
            force_rerun=force_rerun,
        )
    else:
        print(f"  Evaluating {total} questions sequentially...")
        return _evaluate_questions_sequential(
            questions,
            metrics,
            agent,
            db_connection,
            ex_metric=ex_metric,
            run_id=run_id,
            output_dir=output_dir,
            resume_enabled=resume_enabled,
            force_rerun=force_rerun,
        )


def _evaluate_ex_with_stored_rows(
    ex_metric: ExecutionAccuracyMetric,
    gt_sql: str,
    final_result_rows: list,
    db_connection,
) -> dict:
    """
    Compare stored result rows (from multi-query synthesizer) against GT execution.
    Returns a metrics dict compatible with the standard metric result format.
    """
    gt_result, gt_error = db_connection.execute_query(gt_sql)
    if gt_error or gt_result is None:
        return {
            "score": 0.0,
            "is_correct": False,
            "error": f"GT execution failed: {gt_error}",
            "details": {"reason": "ground_truth_execution_failed"},
        }
    results_match, details = ex_metric._compare_results(gt_result, final_result_rows)
    return {
        "score": 1.0 if results_match else 0.0,
        "is_correct": results_match,
        "error": None,
        "details": details,
    }


def _evaluate_questions_sequential(
    questions: List[Dict],
    metrics: List,
    agent,
    db_connection,
    ex_metric: ExecutionAccuracyMetric | None = None,
    run_id: str | None = None,
    output_dir: Path | None = None,
    resume_enabled: bool = False,
    force_rerun: bool = False,
) -> Dict[str, Any]:
    """Sequential evaluation (original implementation)"""
    run_id = str(run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    output_dir = output_dir or _resolve_output_dir(run_id)
    results = []
    metric_scores = {metric.name: [] for metric in metrics}

    # Agent statistics
    agent_stats = {"success_count": 0, "failure_count": 0, "total_time": 0.0}
    resume_stats = {"enabled": resume_enabled, "reused_count": 0, "evaluated_count": 0}

    total = len(questions)

    for i, question_data in enumerate(questions, 1):
        if i % 10 == 0:
            print(f"      Progress: {i}/{total} ({i / total * 100:.1f}%)")

        if resume_enabled and not force_rerun:
            resumed_result = _load_completed_query_trace(
                output_dir=output_dir,
                question_data=question_data,
            )
            if resumed_result is not None:
                _accumulate_result_stats(
                    result=resumed_result,
                    metric_scores=metric_scores,
                    metrics=metrics,
                    agent_stats=agent_stats,
                )
                results.append(resumed_result)
                resume_stats["reused_count"] += 1
                continue

        # Generate prediction with agent
        start_time = time.time()
        question_started_at = datetime.now().isoformat()
        agent_result = {}
        agent_success = False
        stored_rows = None
        agent_metadata = {}
        multi_metadata = {}
        agent_error = None
        agent_output = {}

        try:
            agent_result = agent.process_query(question_data["question"])
            agent_output = _summarize_agent_result(agent_result)
            agent_metadata = (
                agent_result.get("metadata", {}) if isinstance(agent_result, dict) else {}
            )
            multi_metadata = (
                agent_metadata.get("multi_query", {}) if isinstance(agent_metadata, dict) else {}
            )
            stored_rows = (
                agent_result.get("final_result_rows") if isinstance(agent_result, dict) else None
            )
            agent_error = agent_result.get("error") if isinstance(agent_result, dict) else None

            # Extract SQL
            if isinstance(agent_result, dict):
                predicted_sql = agent_result.get("sql_query", "")
                agent_success = agent_result.get("success", False)
            else:
                predicted_sql = str(agent_result)
                agent_success = bool(predicted_sql.strip())

            execution_time = time.time() - start_time
            agent_stats["total_time"] += execution_time

            if agent_success and (predicted_sql.strip() or stored_rows is not None):
                agent_stats["success_count"] += 1
            else:
                agent_stats["failure_count"] += 1
                predicted_sql = ""

        except Exception as e:
            execution_time = time.time() - start_time
            agent_stats["failure_count"] += 1
            agent_stats["total_time"] += execution_time
            predicted_sql = ""
            stored_rows = None
            multi_metadata = {}
            agent_metadata = {}
            agent_error = str(e)
            agent_output = {"error": str(e), "type": type(e).__name__}

        # Evaluate with metrics
        context = EvaluationContext(
            question_id=question_data["id"],
            question=question_data["question"],
            ground_truth_sql=question_data["query"],
            predicted_sql=predicted_sql,
            database_connection=db_connection,
        )

        question_results = {
            "question_id": question_data["id"],
            "difficulty": question_data["difficulty"],
            "question": question_data["question"],
            "ground_truth_sql": question_data["query"],
            "predicted_sql": predicted_sql,
            "agent_success": agent_success,
            "agent_execution_time": execution_time,
            "question_started_at": question_started_at,
            "question_completed_at": datetime.now().isoformat(),
            "evaluation_source": "merged_rows" if stored_rows is not None else "sql_query",
            "stored_rows": stored_rows,
            "agent_output": agent_output,
            "agent_metadata": agent_metadata,
            "multi_query": multi_metadata,
            "agent_error": agent_error,
            "metrics": {},
        }

        for metric in metrics:
            try:
                # For EX: use stored rows when available (multi-query path)
                if (
                    ex_metric is not None
                    and metric.name == ex_metric.name
                    and stored_rows is not None
                ):
                    metric_result_dict = _evaluate_ex_with_stored_rows(
                        ex_metric, question_data["query"], stored_rows, db_connection
                    )
                    question_results["metrics"][metric.name] = metric_result_dict
                    # Count as evaluated regardless of sql presence
                    metric_scores[metric.name].append(metric_result_dict["score"])
                else:
                    result = metric.evaluate(context)
                    question_results["metrics"][metric.name] = {
                        "score": result.score,
                        "is_correct": result.is_correct,
                        "error": result.error_message,
                        "details": result.details,
                    }
                    metric_scores[metric.name].append(result.score)

            except Exception as e:
                question_results["metrics"][metric.name] = {
                    "score": 0.0,
                    "is_correct": False,
                    "error": str(e),
                }

        trace_path = _write_query_trace_checkpoint(
            result=question_results,
            question_data=question_data,
            db_connection=db_connection,
            output_dir=output_dir,
            run_id=run_id,
            question_index=i,
            total_questions=total,
        )
        question_results["trace_path"] = str(trace_path)
        results.append(question_results)
        resume_stats["evaluated_count"] += 1

    print("    Evaluation completed:")
    print(
        f"      Agent success: {agent_stats['success_count']}/{total} ({agent_stats['success_count'] / total * 100:.1f}%)"
    )
    print(f"      Total time: {agent_stats['total_time']:.1f}s")
    if resume_enabled:
        print(f"      Resumed from trace: {resume_stats['reused_count']}/{total}")

    return {
        "detailed_results": results,
        "agent_stats": agent_stats,
        "metric_scores": metric_scores,
        "total_questions": total,
        "future_errors": [],
        "resume": resume_stats,
    }


def _evaluate_questions_parallel(
    questions: List[Dict],
    metrics: List,
    agent,
    db_connection,
    max_workers: int,
    ex_metric: ExecutionAccuracyMetric | None = None,
    run_id: str | None = None,
    output_dir: Path | None = None,
    resume_enabled: bool = False,
    force_rerun: bool = False,
) -> Dict[str, Any]:
    """
    Parallel evaluation using ThreadPoolExecutor

    Args:
        questions: List of question dictionaries
        metrics: List of metric instances
        agent: Agent orchestrator
        db_connection: Database connection
        max_workers: Number of parallel workers
        ex_metric: ExecutionAccuracyMetric instance for stored-rows comparison

    Returns:
        Dict containing detailed evaluation results
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    run_id = str(run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    output_dir = output_dir or _resolve_output_dir(run_id)
    results = []
    metric_scores = {metric.name: [] for metric in metrics}

    # Agent statistics (thread-safe)
    agent_stats = {"success_count": 0, "failure_count": 0, "total_time": 0.0}
    stats_lock = threading.Lock()
    results_lock = threading.Lock()

    total = len(questions)
    resume_stats = {"enabled": resume_enabled, "reused_count": 0, "evaluated_count": 0}
    pending_questions = []
    for index, question in enumerate(questions, 1):
        question_with_index = dict(question)
        question_with_index["_evaluation_index"] = index
        if resume_enabled and not force_rerun:
            resumed_result = _load_completed_query_trace(
                output_dir=output_dir,
                question_data=question_with_index,
            )
            if resumed_result is not None:
                _accumulate_result_stats(
                    result=resumed_result,
                    metric_scores=metric_scores,
                    metrics=metrics,
                    agent_stats=agent_stats,
                )
                results.append(resumed_result)
                resume_stats["reused_count"] += 1
                continue
        pending_questions.append(question_with_index)

    completed_count = resume_stats["reused_count"]
    count_lock = threading.Lock()
    future_errors = []

    def evaluate_single_question(question_data):
        """Evaluate a single question (runs in thread)"""
        nonlocal completed_count

        start_time = time.time()
        agent_result_dict = {}
        agent_success = False
        stored_rows = None
        agent_metadata = {}
        multi_metadata = {}
        agent_error = None
        agent_output = {}
        question_started_at = datetime.now().isoformat()

        try:
            agent_result_dict = agent.process_query(question_data["question"])
            agent_output = _summarize_agent_result(agent_result_dict)
            agent_metadata = (
                agent_result_dict.get("metadata", {}) if isinstance(agent_result_dict, dict) else {}
            )
            multi_metadata = (
                agent_metadata.get("multi_query", {}) if isinstance(agent_metadata, dict) else {}
            )
            stored_rows = (
                agent_result_dict.get("final_result_rows")
                if isinstance(agent_result_dict, dict)
                else None
            )
            agent_error = (
                agent_result_dict.get("error") if isinstance(agent_result_dict, dict) else None
            )

            # Extract SQL
            if isinstance(agent_result_dict, dict):
                predicted_sql = agent_result_dict.get("sql_query", "")
                agent_success = agent_result_dict.get("success", False)
            else:
                predicted_sql = str(agent_result_dict)
                agent_success = bool(predicted_sql.strip())

            execution_time = time.time() - start_time

            # Update stats (thread-safe)
            with stats_lock:
                agent_stats["total_time"] += execution_time
                if agent_success and (predicted_sql.strip() or stored_rows is not None):
                    agent_stats["success_count"] += 1
                else:
                    agent_stats["failure_count"] += 1
                    predicted_sql = ""

        except Exception as e:
            execution_time = time.time() - start_time
            with stats_lock:
                agent_stats["failure_count"] += 1
                agent_stats["total_time"] += execution_time
            predicted_sql = ""
            stored_rows = None
            multi_metadata = {}
            agent_metadata = {}
            agent_error = str(e)
            agent_output = {"error": str(e), "type": type(e).__name__}

        # Evaluate with metrics
        context = EvaluationContext(
            question_id=question_data["id"],
            question=question_data["question"],
            ground_truth_sql=question_data["query"],
            predicted_sql=predicted_sql,
            database_connection=db_connection,
        )

        question_results = {
            "question_id": question_data["id"],
            "difficulty": question_data["difficulty"],
            "question": question_data["question"],
            "ground_truth_sql": question_data["query"],
            "predicted_sql": predicted_sql,
            "agent_success": agent_success,
            "agent_execution_time": execution_time,
            "question_started_at": question_started_at,
            "question_completed_at": datetime.now().isoformat(),
            "evaluation_source": "merged_rows" if stored_rows is not None else "sql_query",
            "stored_rows": stored_rows,
            "agent_output": agent_output,
            "agent_metadata": agent_metadata,
            "multi_query": multi_metadata,
            "agent_error": agent_error,
            "metrics": {},
        }

        for metric in metrics:
            try:
                if (
                    ex_metric is not None
                    and metric.name == ex_metric.name
                    and stored_rows is not None
                ):
                    metric_result_dict = _evaluate_ex_with_stored_rows(
                        ex_metric, question_data["query"], stored_rows, db_connection
                    )
                    question_results["metrics"][metric.name] = metric_result_dict
                    with results_lock:
                        metric_scores[metric.name].append(metric_result_dict["score"])
                else:
                    result = metric.evaluate(context)
                    question_results["metrics"][metric.name] = {
                        "score": result.score,
                        "is_correct": result.is_correct,
                        "error": result.error_message,
                        "details": result.details,
                    }
                    with results_lock:
                        metric_scores[metric.name].append(result.score)

            except Exception as e:
                question_results["metrics"][metric.name] = {
                    "score": 0.0,
                    "is_correct": False,
                    "error": str(e),
                }

        trace_path = _write_query_trace_checkpoint(
            result=question_results,
            question_data=question_data,
            db_connection=db_connection,
            output_dir=output_dir,
            run_id=run_id,
            question_index=question_data.get("_evaluation_index"),
            total_questions=total,
        )
        question_results["trace_path"] = str(trace_path)

        # Update progress (thread-safe)
        with count_lock:
            completed_count += 1
            if completed_count % 10 == 0:
                print(
                    f"      Progress: {completed_count}/{total} ({completed_count / total * 100:.1f}%)"
                )

        return question_results

    # Execute in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(evaluate_single_question, q): q for q in pending_questions}

        # Collect results as they complete
        for future in as_completed(futures):
            try:
                result = future.result()
                with results_lock:
                    results.append(result)
                resume_stats["evaluated_count"] += 1
            except Exception as e:
                question = futures[future]
                question_id = (
                    question.get("id", "unknown") if isinstance(question, dict) else "unknown"
                )
                error_record = {
                    "question_id": question_id,
                    "question": question.get("question") if isinstance(question, dict) else None,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
                future_errors.append(error_record)
                print(f"      Error processing {question_id}: {e}")

                failure_metrics = {}
                for metric in metrics:
                    failure_metrics[metric.name] = {
                        "score": 0.0,
                        "is_correct": False,
                        "error": str(e),
                        "details": {"reason": "future_exception"},
                    }
                    with results_lock:
                        metric_scores[metric.name].append(0.0)

                failure_result = {
                    "question_id": question_id,
                    "difficulty": question.get("difficulty", "unknown")
                    if isinstance(question, dict)
                    else "unknown",
                    "question": question.get("question") if isinstance(question, dict) else None,
                    "ground_truth_sql": question.get("query", "") if isinstance(question, dict) else "",
                    "predicted_sql": "",
                    "agent_success": False,
                    "agent_execution_time": 0.0,
                    "question_started_at": None,
                    "question_completed_at": datetime.now().isoformat(),
                    "evaluation_source": "future_exception",
                    "stored_rows": None,
                    "agent_output": {"error": str(e), "type": type(e).__name__},
                    "agent_metadata": {},
                    "multi_query": {},
                    "agent_error": str(e),
                    "metrics": failure_metrics,
                }
                trace_path = _write_query_trace_checkpoint(
                    result=failure_result,
                    question_data=question,
                    db_connection=db_connection,
                    output_dir=output_dir,
                    run_id=run_id,
                    question_index=question.get("_evaluation_index")
                    if isinstance(question, dict)
                    else None,
                    total_questions=total,
                )
                failure_result["trace_path"] = str(trace_path)

                with results_lock:
                    results.append(failure_result)
                resume_stats["evaluated_count"] += 1

    print("    Evaluation completed:")
    print(
        f"      Agent success: {agent_stats['success_count']}/{total} ({agent_stats['success_count'] / total * 100:.1f}%)"
    )
    print(f"      Total time: {agent_stats['total_time']:.1f}s")
    print(f"      Speedup: {max_workers}x workers")
    if resume_enabled:
        print(f"      Resumed from trace: {resume_stats['reused_count']}/{total}")

    return {
        "detailed_results": results,
        "agent_stats": agent_stats,
        "metric_scores": metric_scores,
        "total_questions": total,
        "future_errors": future_errors,
        "resume": resume_stats,
    }


def aggregate_results(evaluate_questions: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    Aggregate evaluation results and calculate statistics

    Args:
        evaluate_questions: Results from evaluation

    Returns:
        Dict containing aggregated statistics
    """
    print("  Aggregating results...")

    results = evaluate_questions["detailed_results"]
    agent_stats = evaluate_questions["agent_stats"]
    metric_scores = evaluate_questions["metric_scores"]
    total = evaluate_questions["total_questions"]

    # Calculate metric statistics
    aggregated_metrics = {}

    for metric_name, scores in metric_scores.items():
        if scores:
            avg_score = sum(scores) / len(scores)
            accuracy = sum(1 for s in scores if s >= 0.8) / len(scores)
            perfect = sum(1 for s in scores if s == 1.0)

            aggregated_metrics[metric_name] = {
                "average_score": avg_score,
                "accuracy": accuracy,
                "perfect_matches": perfect,
                "total_evaluated": len(scores),
            }
        else:
            aggregated_metrics[metric_name] = {
                "average_score": 0.0,
                "accuracy": 0.0,
                "perfect_matches": 0,
                "total_evaluated": 0,
            }

    # Difficulty breakdown
    difficulties = {}
    for r in results:
        diff = r["difficulty"]
        if diff not in difficulties:
            difficulties[diff] = {"total": 0, "agent_success": 0, "metrics": {}}

        difficulties[diff]["total"] += 1

        if r["agent_success"]:
            difficulties[diff]["agent_success"] += 1

        # Collect metric stats for ALL queries (failures count as score=0)
        for metric_name, metric_result in r["metrics"].items():
            if metric_name not in difficulties[diff]["metrics"]:
                difficulties[diff]["metrics"][metric_name] = {
                    "correct": 0,
                    "total": 0,
                    "scores": [],
                }

            difficulties[diff]["metrics"][metric_name]["total"] += 1
            difficulties[diff]["metrics"][metric_name]["scores"].append(metric_result["score"])

            if metric_result["is_correct"]:
                difficulties[diff]["metrics"][metric_name]["correct"] += 1

    print(f"    Aggregated {len(results)} results")
    print("    Metrics:")
    for metric_name, stats in aggregated_metrics.items():
        print(
            f"      {metric_name}: {stats['average_score']:.3f} avg, {stats['accuracy']:.1%} accuracy"
        )

    return {
        "summary": {
            "total_questions": total,
            "agent_success_rate": agent_stats["success_count"] / total if total > 0 else 0,
            "agent_failure_rate": agent_stats["failure_count"] / total if total > 0 else 0,
            "total_execution_time": agent_stats["total_time"],
            "avg_execution_time": agent_stats["total_time"] / total if total > 0 else 0,
        },
        "metrics": aggregated_metrics,
        "difficulty_breakdown": difficulties,
        "timestamp": datetime.now().isoformat(),
    }


def generate_report(
    aggregate_results: Dict[str, Any], evaluate_questions: Dict[str, Any], **kwargs
) -> Dict[str, Any]:
    """
    Generate human-readable report

    Args:
        aggregate_results: Aggregated statistics
        evaluate_questions: Detailed results

    Returns:
        Dict containing report text
    """
    print("  Generating evaluation report...")

    summary = aggregate_results["summary"]
    metrics = aggregate_results["metrics"]
    difficulties = aggregate_results["difficulty_breakdown"]
    detailed_results = evaluate_questions.get("detailed_results", [])
    multi_count = sum(
        1
        for r in detailed_results
        if ((r.get("multi_query") or {}).get("query_plan") or {}).get("strategy") == "multi"
    )
    multi_eval_count = sum(
        1 for r in detailed_results if r.get("evaluation_source") == "merged_rows"
    )
    fallback_count = sum(
        1 for r in detailed_results if (r.get("multi_query") or {}).get("single_fallback_active")
    )

    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("TEXT-TO-SQL EVALUATION REPORT")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Overall summary
    report_lines.append("OVERALL SUMMARY")
    report_lines.append("-" * 80)
    report_lines.append(f"Total Questions: {summary['total_questions']}")
    report_lines.append(f"Agent Success Rate: {summary['agent_success_rate']:.1%}")
    report_lines.append(f"Total Execution Time: {summary['total_execution_time']:.1f}s")
    report_lines.append(f"Avg Time per Question: {summary['avg_execution_time']:.2f}s")
    report_lines.append(f"Multi Plans Triggered: {multi_count}")
    report_lines.append(f"EX Evaluated via merged_rows: {multi_eval_count}")
    report_lines.append(f"Single Fallbacks Triggered: {fallback_count}")
    report_lines.append("")

    # Metrics
    report_lines.append("METRICS PERFORMANCE")
    report_lines.append("-" * 80)
    for metric_name, stats in metrics.items():
        report_lines.append(f"\n{metric_name}:")
        report_lines.append(f"  Average Score: {stats['average_score']:.3f}")
        report_lines.append(f"  Accuracy (≥0.8): {stats['accuracy']:.1%}")
        report_lines.append(
            f"  Perfect Matches: {stats['perfect_matches']}/{stats['total_evaluated']}"
        )

    report_lines.append("")

    # Difficulty breakdown
    report_lines.append("DIFFICULTY BREAKDOWN")
    report_lines.append("-" * 80)
    for diff, stats in sorted(difficulties.items()):
        report_lines.append(f"\n{diff.upper()}:")
        report_lines.append(f"  Questions: {stats['total']}")
        report_lines.append(
            f"  Agent Success: {stats['agent_success']}/{stats['total']} "
            f"({stats['agent_success'] / stats['total'] * 100:.1f}%)"
        )

        for metric_name, metric_stats in stats["metrics"].items():
            if metric_stats["total"] > 0:
                avg_score = sum(metric_stats["scores"]) / len(metric_stats["scores"])
                accuracy = metric_stats["correct"] / metric_stats["total"]
                report_lines.append(f"  {metric_name}: {avg_score:.3f} ({accuracy:.1%})")

    report_lines.append("")
    report_lines.append("=" * 80)

    report_text = "\n".join(report_lines)

    print("    Report generated successfully")

    return {"report_text": report_text, "report_lines": report_lines}


def _json_safe(value: Any) -> Any:
    """Convert DB/agent values to JSONL-safe primitives."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _row_to_values(row: Any, columns: Optional[list[str]] = None) -> list[Any]:
    if isinstance(row, dict):
        ordered_columns = columns or list(row.keys())
        return [_json_safe(row.get(column)) for column in ordered_columns]
    if hasattr(row, "_mapping"):
        mapping = row._mapping
        ordered_columns = columns or list(mapping.keys())
        return [_json_safe(mapping[column]) for column in ordered_columns]
    if isinstance(row, (list, tuple)):
        return [_json_safe(value) for value in row]
    return [_json_safe(row)]


def _columns_from_rows(rows: list[Any]) -> list[str]:
    if not rows:
        return []
    first_row = rows[0]
    if isinstance(first_row, dict):
        return [str(column) for column in first_row.keys()]
    if hasattr(first_row, "_mapping"):
        return [str(column) for column in first_row._mapping.keys()]
    return []


def _preview_from_rows(
    rows: Optional[list[Any]],
    columns: Optional[list[str]] = None,
    *,
    status: str = "passed",
    error: Optional[str] = None,
    latency_seconds: Optional[float] = None,
    row_limit: int = TRACE_PREVIEW_ROW_LIMIT,
) -> dict[str, Any]:
    safe_rows = list(rows or [])
    safe_columns = [str(column) for column in (columns or _columns_from_rows(safe_rows))]
    preview_values = [
        _row_to_values(row, safe_columns if safe_columns else None) for row in safe_rows[:row_limit]
    ]
    return {
        "status": status,
        "columns": safe_columns,
        "preview_values": preview_values,
        "row_count": len(safe_rows),
        "truncated": len(safe_rows) > row_limit,
        "error": error,
        "latency_seconds": latency_seconds,
    }


def _execute_sql_for_trace(db_connection, sql: Optional[str]) -> dict[str, Any]:
    if not sql or not sql.strip():
        return _preview_from_rows(
            [],
            [],
            status="skipped",
            error="SQL not available",
            latency_seconds=0.0,
        )

    started_at = time.time()
    if hasattr(db_connection, "execute_query_with_columns"):
        rows, columns, error = db_connection.execute_query_with_columns(sql)
    else:
        rows, error = db_connection.execute_query(sql)
        columns = []
    latency_seconds = time.time() - started_at

    if error:
        return _preview_from_rows(
            [],
            columns,
            status="failed",
            error=error,
            latency_seconds=latency_seconds,
        )
    return _preview_from_rows(
        rows,
        columns,
        status="passed",
        error=None,
        latency_seconds=latency_seconds,
    )


def _step_status(success: Any) -> str:
    if success is True:
        return "passed"
    if success is False:
        return "failed"
    return "unknown"


def _build_trace_steps(
    *,
    result: dict[str, Any],
    ex_metric: dict[str, Any],
    gt_execution: dict[str, Any],
    generated_execution: dict[str, Any],
) -> list[dict[str, Any]]:
    metadata = result.get("agent_metadata") or {}
    latency_by_component = metadata.get("latency_by_component") or {}
    steps: list[dict[str, Any]] = [
        {
            "name": "evaluation_input",
            "status": "passed",
            "details": {
                "question_id": result.get("question_id"),
                "difficulty": result.get("difficulty"),
                "question_pt": result.get("question"),
                "ground_truth_sql": result.get("ground_truth_sql"),
            },
        },
        {
            "name": "agent.process_query",
            "status": "passed" if result.get("agent_success") else "failed",
            "latency_seconds": result.get("agent_execution_time"),
            "input": {"question": result.get("question")},
            "output": result.get("agent_output"),
            "error": result.get("agent_error"),
        },
    ]

    for phase in metadata.get("phases_completed") or []:
        phase_name = str(phase)
        steps.append(
            {
                "name": f"workflow.{phase_name}",
                "status": "passed",
                "latency_seconds": latency_by_component.get(phase_name),
                "details": {
                    "current_phase": metadata.get("current_phase"),
                    "semantic_plan": metadata.get("semantic_plan")
                    if phase_name == "reasoning"
                    else None,
                    "semantic_validation": metadata.get("semantic_validation")
                    if phase_name == "sql_validation"
                    else None,
                },
            }
        )

    for tool_call in metadata.get("tool_calls") or []:
        tool_name = tool_call.get("name") or "unknown"
        steps.append(
            {
                "name": f"tool.{tool_name}",
                "status": _step_status(tool_call.get("success")),
                "latency_seconds": tool_call.get("execution_time"),
                "details": tool_call,
            }
        )

    for metric_name, metric_result in (result.get("metrics") or {}).items():
        steps.append(
            {
                "name": f"metric.{metric_name}",
                "status": "passed" if metric_result.get("is_correct") else "failed",
                "score": metric_result.get("score"),
                "error": metric_result.get("error"),
                "details": metric_result.get("details"),
            }
        )

    steps.append(
        {
            "name": "final_result",
            "status": "passed" if ex_metric.get("is_correct") else "failed",
            "details": {
                "generated_sql": result.get("predicted_sql"),
                "generated_execution_status": generated_execution.get("status"),
                "ground_truth_execution_status": gt_execution.get("status"),
                "result_match": ex_metric.get("is_correct"),
                "ex_score": ex_metric.get("score"),
            },
        }
    )

    return _json_safe(steps)


def _ex_metric(result: dict[str, Any]) -> dict[str, Any]:
    return result.get("metrics", {}).get("Execution Accuracy (EX)", {}) or {}


def _comparison_details(ex_metric: dict[str, Any]) -> dict[str, Any]:
    details = ex_metric.get("details") or {}
    return details.get("comparison_details") or {}


def _trace_error_category(
    result: dict[str, Any],
    gt_execution: dict[str, Any],
    generated_execution: dict[str, Any],
    ex_metric: dict[str, Any],
) -> Optional[str]:
    comparison = _comparison_details(ex_metric)
    if not result.get("agent_success"):
        return "agent_failed"
    if gt_execution.get("status") == "failed":
        return "ground_truth_execution_error"
    if generated_execution.get("status") == "failed":
        return "generated_execution_error"
    if ex_metric.get("error"):
        return "metric_error"
    if ex_metric and not ex_metric.get("is_correct", False):
        if comparison.get("size_mismatch"):
            return "row_count_mismatch"
        if comparison.get("normalized_match") is False:
            return "result_mismatch"
        return "execution_mismatch"
    return None


def _trace_error_message(
    result: dict[str, Any],
    gt_execution: dict[str, Any],
    generated_execution: dict[str, Any],
    ex_metric: dict[str, Any],
) -> Optional[str]:
    if result.get("agent_error"):
        return str(result["agent_error"])
    if gt_execution.get("error"):
        return str(gt_execution["error"])
    if generated_execution.get("error"):
        return str(generated_execution["error"])
    if ex_metric.get("error"):
        return str(ex_metric["error"])
    details = ex_metric.get("details") or {}
    if details.get("reason") and not ex_metric.get("is_correct", False):
        return str(details["reason"])
    return None


def _build_trace_record(result: dict[str, Any], db_connection) -> dict[str, Any]:
    ex_metric = _ex_metric(result)
    metric_details = ex_metric.get("details") or {}
    comparison = _comparison_details(ex_metric)
    metadata = result.get("agent_metadata") or {}
    multi_query = result.get("multi_query") or metadata.get("multi_query") or {}

    gt_execution = _execute_sql_for_trace(db_connection, result.get("ground_truth_sql"))
    if result.get("agent_success") and result.get("stored_rows") is not None:
        generated_execution = _preview_from_rows(
            result.get("stored_rows") or [],
            status="passed",
        )
    elif result.get("agent_success"):
        generated_execution = _execute_sql_for_trace(db_connection, result.get("predicted_sql"))
    else:
        generated_execution = _preview_from_rows(
            [],
            [],
            status="skipped",
            error="Agent failed before SQL execution",
            latency_seconds=0.0,
        )

    has_generated_sql = bool((result.get("predicted_sql") or "").strip())
    expected_columns = gt_execution["columns"]
    actual_columns = generated_execution["columns"]
    row_count_match = gt_execution["row_count"] == generated_execution["row_count"]
    column_shape_known = bool(expected_columns and actual_columns)
    shape_match = row_count_match and (
        not column_shape_known or len(expected_columns) == len(actual_columns)
    )
    error_category = _trace_error_category(
        result,
        gt_execution,
        generated_execution,
        ex_metric,
    )

    record = {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "status": "completed",
        "run_id": result.get("run_id"),
        "question_index": result.get("question_index"),
        "total_questions": result.get("total_questions"),
        "question_fingerprint": result.get("question_fingerprint"),
        "trace_path": result.get("trace_path"),
        "written_at": datetime.now().isoformat(),
        "id": result.get("question_id"),
        "difficulty": result.get("difficulty"),
        "question_pt": result.get("question"),
        "question_started_at": result.get("question_started_at"),
        "question_completed_at": result.get("question_completed_at"),
        "ground_truth_sql": result.get("ground_truth_sql"),
        "generated_sql": result.get("predicted_sql"),
        "agent_success": bool(result.get("agent_success")),
        "agent_error": result.get("agent_error"),
        "agent_output": result.get("agent_output"),
        "evaluation_source": result.get("evaluation_source"),
        "latency_seconds": result.get("agent_execution_time"),
        "generated_sql_valid": has_generated_sql and generated_execution["status"] == "passed",
        "generated_sql_validation_errors": (
            [generated_execution["error"]] if generated_execution.get("error") else []
        ),
        "generated_sql_validation_warnings": [],
        "generated_execution_status": generated_execution["status"],
        "ground_truth_execution_status": gt_execution["status"],
        "comparison_mode": "execution_accuracy",
        "result_match": ex_metric.get("is_correct"),
        "ex_score": ex_metric.get("score"),
        "shape_match": shape_match,
        "projected_match": bool(comparison.get("projected_match")),
        "expected_columns": expected_columns,
        "actual_columns": actual_columns,
        "expected_preview_values": gt_execution["preview_values"],
        "actual_preview_values": generated_execution["preview_values"],
        "expected_row_count": gt_execution["row_count"],
        "actual_row_count": generated_execution["row_count"],
        "expected_truncated": gt_execution["truncated"],
        "actual_truncated": generated_execution["truncated"],
        "ground_truth_execution_error": gt_execution["error"],
        "generated_execution_error": generated_execution["error"],
        "ground_truth_execution_latency_seconds": gt_execution["latency_seconds"],
        "generated_execution_latency_seconds": generated_execution["latency_seconds"],
        "error_category": error_category,
        "error_message": _trace_error_message(
            result,
            gt_execution,
            generated_execution,
            ex_metric,
        ),
        "metric_details": metric_details,
        "comparison_details": comparison,
        "multi_query": multi_query,
        "tables_used": metadata.get("tables_used"),
        "selected_tables": {
            "llamaindex": metadata.get("llamaindex_selected_tables"),
            "raw": metadata.get("raw_selected_tables"),
            "validated": metadata.get("validated_selected_tables"),
        },
        "table_selection": {
            "mode": metadata.get("table_selection_mode"),
            "llamaindex_enabled": metadata.get("llamaindex_enabled"),
            "llamaindex_mode": metadata.get("llamaindex_mode"),
            "llamaindex_confidence": metadata.get("llamaindex_confidence"),
            "llamaindex_error": metadata.get("llamaindex_error"),
        },
        "semantic_plan": metadata.get("semantic_plan"),
        "semantic_planner": metadata.get("semantic_planner"),
        "semantic_validation": metadata.get("semantic_validation"),
        "chart_plan": metadata.get("chart_plan"),
        "chart_plan_validation": metadata.get("chart_plan_validation"),
        "workflow_metrics": metadata.get("workflow_metrics"),
        "latency_by_component": metadata.get("latency_by_component"),
        "tool_calls": metadata.get("tool_calls"),
        "phases_completed": metadata.get("phases_completed"),
        "agent_metadata": metadata,
        "steps": _build_trace_steps(
            result=result,
            ex_metric=ex_metric,
            gt_execution=gt_execution,
            generated_execution=generated_execution,
        ),
        "detailed_result": result,
    }
    return _json_safe(record)


def _write_query_trace_record(trace_path: Path, trace_record: dict[str, Any]) -> None:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = trace_path.with_name(f"{trace_path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(trace_record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, trace_path)


def _write_query_trace_checkpoint(
    *,
    result: dict[str, Any],
    question_data: dict[str, Any],
    db_connection,
    output_dir: Path,
    run_id: str,
    question_index: int | None,
    total_questions: int,
) -> Path:
    trace_path = _query_trace_path(output_dir, question_data.get("id"))
    result["run_id"] = run_id
    result["question_index"] = question_index
    result["total_questions"] = total_questions
    result["question_fingerprint"] = _question_fingerprint(question_data)
    result["trace_path"] = str(trace_path)

    trace_record = _build_trace_record(result, db_connection)
    _write_query_trace_record(trace_path, trace_record)
    return trace_path


def _load_query_trace_record(output_dir: Path, result: dict[str, Any]) -> dict[str, Any] | None:
    trace_path_value = result.get("trace_path")
    if trace_path_value:
        trace_path = Path(trace_path_value)
    else:
        trace_path = _query_trace_path(output_dir, result.get("question_id"))
    if not trace_path.is_absolute():
        trace_path = project_root / trace_path
    if not trace_path.exists():
        return None
    try:
        with open(trace_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _build_trace_records(
    detailed_results: list[dict[str, Any]],
    db_connection,
    output_dir: Path | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    records = []
    for index, result in enumerate(detailed_results, 1):
        existing_record = _load_query_trace_record(output_dir, result) if output_dir else None
        if existing_record is not None:
            records.append(existing_record)
            continue

        question_data = _question_from_result(result)
        trace_path = _write_query_trace_checkpoint(
            result=result,
            question_data=question_data,
            db_connection=db_connection,
            output_dir=output_dir or _resolve_output_dir(str(run_id or "unknown")),
            run_id=str(run_id or result.get("run_id") or "unknown"),
            question_index=result.get("question_index") or index,
            total_questions=len(detailed_results),
        )
        loaded_record = _load_query_trace_record(output_dir or trace_path.parents[2], result)
        records.append(loaded_record or _build_trace_record(result, db_connection))
    return records


def _write_trace_jsonl(trace_records: list[dict[str, Any]], output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for record in trace_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _format_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{numerator / denominator:.1%}"


def _generate_trace_analysis(
    trace_records: list[dict[str, Any]],
    aggregate_results: dict[str, Any],
) -> str:
    total = len(trace_records)
    agent_success_count = sum(1 for record in trace_records if record.get("agent_success"))
    ex_match_count = sum(1 for record in trace_records if record.get("result_match") is True)
    generated_failures = sum(
        1 for record in trace_records if record.get("generated_execution_status") == "failed"
    )
    ground_truth_failures = sum(
        1 for record in trace_records if record.get("ground_truth_execution_status") == "failed"
    )
    latencies = [
        record["latency_seconds"]
        for record in trace_records
        if isinstance(record.get("latency_seconds"), (int, float))
    ]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    difficulty_rows: dict[str, dict[str, int]] = {}
    for record in trace_records:
        difficulty = str(record.get("difficulty") or "unknown")
        stats = difficulty_rows.setdefault(
            difficulty,
            {"total": 0, "agent_success": 0, "ex_match": 0, "generated_failed": 0},
        )
        stats["total"] += 1
        stats["agent_success"] += int(bool(record.get("agent_success")))
        stats["ex_match"] += int(record.get("result_match") is True)
        stats["generated_failed"] += int(record.get("generated_execution_status") == "failed")

    lines = [
        "# DAG Evaluation Analysis",
        "",
        "## Summary",
        f"- Total: {total}",
        (
            f"- Agent success: {agent_success_count}/{total} "
            f"({_format_pct(agent_success_count, total)})"
        ),
        (f"- Execution matches: {ex_match_count}/{total} ({_format_pct(ex_match_count, total)})"),
        f"- Generated SQL execution failures: {generated_failures}",
        f"- Ground truth execution failures: {ground_truth_failures}",
        f"- Average latency seconds: {avg_latency:.2f}",
        "",
        "## Aggregate Metrics",
    ]

    aggregate_metrics = aggregate_results.get("metrics") or {}
    for metric_name, stats in sorted(aggregate_metrics.items()):
        lines.append(
            "- "
            f"{metric_name}: average={stats.get('average_score', 0):.3f}, "
            f"accuracy={stats.get('accuracy', 0):.1%}, "
            f"perfect={stats.get('perfect_matches', 0)}/{stats.get('total_evaluated', 0)}"
        )
    if not aggregate_metrics:
        lines.append("- No aggregate metrics available")

    lines.extend(
        [
            "",
            "## Difficulty Breakdown",
            "",
            "| difficulty | total | agent_success | ex_match | generated_failed |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for difficulty, stats in sorted(difficulty_rows.items()):
        lines.append(
            "| "
            f"{_markdown_cell(difficulty)} | "
            f"{stats['total']} | "
            f"{stats['agent_success']} | "
            f"{stats['ex_match']} | "
            f"{stats['generated_failed']} |"
        )

    lines.extend(
        [
            "",
            "## Records",
            "",
            (
                "| id | difficulty | match | agent | generated_status | "
                "expected_rows | actual_rows | latency_s | error_category |"
            ),
            "|---|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for record in trace_records:
        latency = record.get("latency_seconds")
        latency_text = f"{latency:.2f}" if isinstance(latency, (int, float)) else ""
        lines.append(
            "| "
            f"{_markdown_cell(record.get('id'))} | "
            f"{_markdown_cell(record.get('difficulty'))} | "
            f"{_markdown_cell(record.get('result_match'))} | "
            f"{_markdown_cell(record.get('agent_success'))} | "
            f"{_markdown_cell(record.get('generated_execution_status'))} | "
            f"{_markdown_cell(record.get('expected_row_count'))} | "
            f"{_markdown_cell(record.get('actual_row_count'))} | "
            f"{_markdown_cell(latency_text)} | "
            f"{_markdown_cell(record.get('error_category'))} |"
        )

    failures = [
        record
        for record in trace_records
        if record.get("error_category") or record.get("result_match") is False
    ]
    lines.extend(["", "## Failure Details"])
    if not failures:
        lines.append("")
        lines.append("No failures found.")
    for record in failures:
        lines.extend(
            [
                "",
                f"### {record.get('id')} ({record.get('difficulty')})",
                f"- Question: {record.get('question_pt')}",
                f"- Error category: {record.get('error_category')}",
                f"- Error message: {record.get('error_message')}",
                f"- Expected rows: {record.get('expected_row_count')}",
                f"- Actual rows: {record.get('actual_row_count')}",
                (
                    "- Comparison details: "
                    f"`{json.dumps(record.get('comparison_details') or {}, ensure_ascii=False)}`"
                ),
                "",
                "Ground truth SQL:",
                "```sql",
                str(record.get("ground_truth_sql") or ""),
                "```",
                "",
                "Generated SQL:",
                "```sql",
                str(record.get("generated_sql") or ""),
                "```",
            ]
        )

    return "\n".join(lines) + "\n"


def _collect_pre_aggregation_failures(
    detailed_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    failures = []
    for result in detailed_results:
        metric_errors = {
            metric_name: metric_result.get("error")
            for metric_name, metric_result in result.get("metrics", {}).items()
            if metric_result.get("error")
        }
        if result.get("agent_success") and not metric_errors and not result.get("agent_error"):
            continue
        failures.append(
            {
                "question_id": result.get("question_id"),
                "difficulty": result.get("difficulty"),
                "agent_success": result.get("agent_success"),
                "agent_error": result.get("agent_error"),
                "predicted_sql_present": bool(result.get("predicted_sql")),
                "evaluation_source": result.get("evaluation_source"),
                "metric_errors": metric_errors,
            }
        )
    return failures


def _build_run_context(
    *,
    kwargs: dict[str, Any],
    run_id: str,
    output_dir: Path,
    initialize_agent: dict[str, Any],
    load_ground_truth: dict[str, Any] | None,
) -> dict[str, Any]:
    agent_config = initialize_agent.get("agent_config", {})
    requested_mode = kwargs.get("llamaindex_mode")
    effective_mode = agent_config.get("llamaindex_mode") or normalize_llamaindex_mode(
        requested_mode or os.getenv("LLAMAINDEX_MODE") or "context"
    )
    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "ground_truth_path": kwargs.get("ground_truth_path")
        or (load_ground_truth or {}).get("ground_truth_path"),
        "max_workers": kwargs.get("max_workers", 1),
        "resume": bool(kwargs.get("resume")),
        "resume_run_id": kwargs.get("resume_run_id"),
        "force_rerun": bool(kwargs.get("force_rerun")),
        "llamaindex_mode": effective_mode,
        "llamaindex_requested_mode": requested_mode,
        "llamaindex_top_k_tables": agent_config.get(
            "llamaindex_top_k_tables", kwargs.get("llamaindex_top_k_tables")
        ),
        "llamaindex_index_dir": agent_config.get(
            "llamaindex_index_dir", kwargs.get("llamaindex_index_dir")
        ),
        "llamaindex_rebuild_index": agent_config.get(
            "llamaindex_rebuild_index", kwargs.get("llamaindex_rebuild_index")
        ),
        "verify_llamaindex_schema_with_db": agent_config.get(
            "verify_llamaindex_schema_with_db",
            bool(kwargs.get("verify_llamaindex_schema_with_db"))
            or _env_bool("VERIFY_LLAMAINDEX_SCHEMA_WITH_DB"),
        ),
        "enable_llamaindex_context": agent_config.get("enable_llamaindex_context"),
        "enable_llamaindex_sql_draft": agent_config.get("enable_llamaindex_sql_draft"),
    }


def save_results(
    evaluate_questions: dict[str, Any],
    aggregate_results: dict[str, Any],
    generate_report: dict[str, Any],
    load_configuration: dict[str, Any],
    initialize_agent: dict[str, Any],
    initialize_database: dict[str, Any],
    load_ground_truth: dict[str, Any] | None = None,
    preflight_ground_truth: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """
    Save results to JSON file and print report

    Args:
        evaluate_questions: Detailed results
        aggregate_results: Aggregated statistics
        generate_report: Report text
        load_configuration: Configuration data
        initialize_agent: Agent configuration
        initialize_database: Database connection

    Returns:
        Dict containing output paths
    """
    print("  Saving results...")

    run_id = str(kwargs.get("run_id") or datetime.now().strftime("%Y%m%d_%H%M%S"))
    output_dir = _resolve_output_dir(run_id, kwargs.get("output_dir"))
    output_dir.mkdir(parents=True, exist_ok=True)

    detailed_results = evaluate_questions.get("detailed_results", [])
    pre_aggregation_failures = evaluate_questions.get(
        "pre_aggregation_failures"
    ) or _collect_pre_aggregation_failures(detailed_results)

    # Prepare complete results
    complete_results = {
        "evaluation_timestamp": aggregate_results["timestamp"],
        "run_context": _build_run_context(
            kwargs=kwargs,
            run_id=run_id,
            output_dir=output_dir,
            initialize_agent=initialize_agent,
            load_ground_truth=load_ground_truth,
        ),
        "ground_truth": {
            "requested_path": kwargs.get("ground_truth_path"),
            "loaded_path": (load_ground_truth or {}).get("ground_truth_path"),
            "total_count": (load_ground_truth or {}).get("total_count"),
            "difficulty_breakdown": (load_ground_truth or {}).get("difficulty_breakdown"),
        },
        "preflight": preflight_ground_truth or {},
        "configuration": {
            "llm_provider": load_configuration["llm_provider"],
            "llm_model": load_configuration["llm_model"],
        },
        "agent_config": initialize_agent["agent_config"],
        "summary": aggregate_results["summary"],
        "metrics": aggregate_results["metrics"],
        "difficulty_breakdown": aggregate_results["difficulty_breakdown"],
        "evaluation_diagnostics": {
            "agent_stats": evaluate_questions.get("agent_stats", {}),
            "future_errors": evaluate_questions.get("future_errors", []),
            "resume": evaluate_questions.get("resume", {}),
            "pre_aggregation_failures": pre_aggregation_failures,
            "detailed_result_count": len(detailed_results),
            "metric_score_counts": {
                metric_name: len(scores)
                for metric_name, scores in evaluate_questions.get("metric_scores", {}).items()
            },
        },
        "detailed_results": detailed_results,
    }

    # Save JSON results
    json_path = output_dir / f"dag_evaluation_{run_id}.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(complete_results, f, indent=2, ensure_ascii=False)

    # Save report text
    report_path = output_dir / f"dag_evaluation_report_{run_id}.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(generate_report["report_text"])

    # Save per-question traces and a markdown analysis for manual validation.
    trace_records = _build_trace_records(
        detailed_results=evaluate_questions["detailed_results"],
        db_connection=initialize_database["db_connection"],
        output_dir=output_dir,
        run_id=run_id,
    )
    trace_path = output_dir / "trace.jsonl"
    _write_trace_jsonl(trace_records, trace_path)

    analysis_path = output_dir / "analysis.md"
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(_generate_trace_analysis(trace_records, aggregate_results))

    print("    Results saved:")
    print(f"      JSON: {json_path}")
    print(f"      Report: {report_path}")
    print(f"      Trace: {trace_path}")
    print(f"      Analysis: {analysis_path}")

    # Print report to console
    print("\n")
    print(generate_report["report_text"])

    return {
        "json_path": str(json_path),
        "report_path": str(report_path),
        "trace_path": str(trace_path),
        "analysis_path": str(analysis_path),
        "output_dir": str(output_dir),
        "run_id": run_id,
        "saved_successfully": True,
    }


# Cleanup task
def cleanup_resources(initialize_database: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    Cleanup resources (close database connections, etc.)

    Args:
        initialize_database: Database connection to close

    Returns:
        Dict with cleanup status
    """
    print("  Cleaning up resources...")

    db_connection = initialize_database["db_connection"]

    try:
        db_connection.close()
        print("    Database connection closed")
        return {"cleanup_successful": True}
    except Exception as e:
        print(f"    Warning: Cleanup error - {e}")
        return {"cleanup_successful": False, "error": str(e)}
