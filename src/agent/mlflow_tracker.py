"""MLflow tracking helpers for the TXT2SQL agent.

All public functions are no-ops when MLflow is not installed or
MLFLOW_TRACKING_URI is not set — the agent never fails because of tracking.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()

_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "txt2sql-agent")
_ABLATION_EXPERIMENT = "txt2sql-ablation"

_mlflow_available = False
try:
    import mlflow  # noqa: F401

    _mlflow_available = True
except ImportError:
    pass


def _is_enabled() -> bool:
    return _mlflow_available and bool(_TRACKING_URI)


def _normalize_tracking_uri(uri: str) -> str:
    """Convert plain local paths to MLflow file-store URIs.

    MLflow interprets Windows paths like C:\\... as a URI with scheme "c"
    unless they are passed as file:/// URIs.
    """
    parsed = urlparse(uri)
    if parsed.scheme:
        return uri
    return Path(uri).resolve().as_uri()


def init_mlflow(
    tracking_uri: str | None = None,
    experiment_name: str | None = None,
) -> bool:
    """Configure MLflow tracking URI and experiment.

    Returns True if successfully initialised, False otherwise.
    """
    if not _mlflow_available:
        return False

    uri = tracking_uri or _TRACKING_URI
    if not uri:
        return False
    uri = _normalize_tracking_uri(uri)

    try:
        import mlflow

        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(experiment_name or _EXPERIMENT)
        return True
    except Exception as exc:
        logger.warning("MLflow init failed", extra={"error": str(exc)})
        return False


def log_query_run(
    *,
    result: dict[str, Any],
    session_id: str,
    model: str,
    environment: str,
    query: str,
) -> None:
    """Log a single query execution as an MLflow run.

    Logged metrics: success, execution_time, retry_count, row_count, error_count.
    No-op if MLflow is not configured.
    """
    if not _is_enabled():
        return

    try:
        import mlflow

        init_mlflow()
        meta = result.get("metadata", {}) or {}
        wf_metrics = meta.get("workflow_metrics", {}) or {}

        with mlflow.start_run(run_name=f"query_{session_id}"):
            mlflow.set_tags(
                {
                    "session_id": session_id,
                    "model": model,
                    "environment": environment,
                    "query_preview": query[:120],
                }
            )
            mlflow.log_metrics(
                {
                    "success": int(result.get("success", False)),
                    "execution_time_s": round(result.get("execution_time", 0.0), 3),
                    "retry_count": wf_metrics.get("retry_count", 0),
                    "row_count": result.get("row_count", 0),
                    "error_count": wf_metrics.get("error_count", 0),
                }
            )
    except Exception as exc:
        logger.warning("MLflow log_query_run failed", extra={"error": str(exc)})


def log_ablation_run(
    *,
    variant_id: str,
    variant_name: str,
    flags: dict[str, Any],
    ex_overall: float,
    ex_by_tier: dict[str, float],
    delta_ex_pp: float,
    mcnemar_chi2: float | None,
    mcnemar_p: float | None,
    n_queries: int,
    git_sha: str,
    model_id: str,
    results_csv_path: str | None = None,
    total_tokens: int = 0,
    total_cost_usd: float = 0.0,
    avg_latency_s: float = 0.0,
    p50_latency_s: float = 0.0,
    p95_latency_s: float = 0.0,
) -> None:
    """Log one ablation variant as an MLflow run under the ablation experiment.

    No-op if MLflow is not configured.
    """
    if not _is_enabled():
        return

    try:
        import mlflow

        uri = _normalize_tracking_uri(_TRACKING_URI)
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(_ABLATION_EXPERIMENT)

        with mlflow.start_run(run_name=variant_name):
            mlflow.set_tags(
                {
                    "variant_id": variant_id,
                    "variant_name": variant_name,
                    "git_sha": git_sha,
                    "model_id": model_id,
                    "n_queries": str(n_queries),
                    **{f"flag_{k}": str(v) for k, v in flags.items()},
                }
            )

            metrics: dict[str, float] = {
                "ex_overall": ex_overall,
                "delta_ex_pp": delta_ex_pp,
            }
            for tier, val in ex_by_tier.items():
                metrics[f"ex_{tier}"] = val
            if mcnemar_chi2 is not None:
                metrics["mcnemar_chi2"] = mcnemar_chi2
            if mcnemar_p is not None:
                metrics["mcnemar_p"] = mcnemar_p
            if total_tokens:
                metrics["total_tokens"] = float(total_tokens)
            if total_cost_usd:
                metrics["total_cost_usd"] = total_cost_usd
            if avg_latency_s:
                metrics["avg_latency_s"] = avg_latency_s
            if p50_latency_s:
                metrics["p50_latency_s"] = p50_latency_s
            if p95_latency_s:
                metrics["p95_latency_s"] = p95_latency_s

            mlflow.log_metrics(metrics)

            if results_csv_path and Path(results_csv_path).exists():
                mlflow.log_artifact(results_csv_path, artifact_path="ablation")

    except Exception as exc:
        logger.warning(
            "MLflow log_ablation_run failed",
            extra={"variant": variant_name, "error": str(exc)},
        )


__all__ = [
    "init_mlflow",
    "log_ablation_run",
    "log_query_run",
]
