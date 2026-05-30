"""Small support helpers for the simple SQL orchestrator."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from ..application.config.simple_config import ApplicationConfig, infer_database_type

AVAILABLE_OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo-0125",
]


def build_application_config(
    base_config: ApplicationConfig,
    *,
    model_name: str,
    temperature: float | None = None,
    timeout: int | None = None,
) -> ApplicationConfig:
    """Create a new application config for model switching."""
    return ApplicationConfig(
        database_type=base_config.database_type,
        database_path=base_config.database_path,
        llm_provider="openai",
        llm_model=model_name,
        llm_temperature=temperature if temperature is not None else base_config.llm_temperature,
        llm_timeout=timeout if timeout is not None else base_config.llm_timeout,
        llm_max_retries=base_config.llm_max_retries,
        schema_type=base_config.schema_type,
        ui_type=base_config.ui_type,
        interface_type=base_config.interface_type,
        error_handling_type=base_config.error_handling_type,
        enable_error_logging=base_config.enable_error_logging,
        query_processing_type=base_config.query_processing_type,
    )


def build_orchestrator_error_result(
    *,
    user_query: str,
    execution_time: float,
    error: Exception,
    current_model_metadata: dict[str, Any],
    environment: str,
) -> dict[str, Any]:
    return {
        "success": False,
        "question": user_query,
        "sql_query": None,
        "results": [],
        "row_count": 0,
        "execution_time": execution_time,
        "error_message": f"Orchestrator error: {error}",
        "response": f"Erro do sistema: {error}",
        "timestamp": datetime.now().isoformat(),
        "metadata": {
            "orchestrator": "simple_agent",
            "orchestrator_error": True,
            "error_type": "orchestrator_execution_error",
            "current_model": current_model_metadata,
            "environment": environment,
        },
    }


def build_health_report(
    *,
    environment: str,
    current_model_metadata: dict[str, Any],
    workflow_available: bool,
    llm_health: dict[str, Any],
    metrics,
) -> dict[str, Any]:
    runtime_status = "healthy" if workflow_available else "failed"
    overall_status = (
        "healthy"
        if llm_health.get("status") == "healthy" and runtime_status == "healthy"
        else "degraded"
    )
    success_rate = metrics.successful_queries / metrics.total_queries if metrics.total_queries else 0
    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "orchestrator": {
            "version": "simple",
            "environment": environment,
            "runtime_status": runtime_status,
            "total_queries": metrics.total_queries,
            "success_rate": success_rate,
        },
        "llm_manager": llm_health,
        "current_model": {
            "provider": current_model_metadata["provider"],
            "model_name": current_model_metadata["model_name"],
            "available": llm_health.get("status") == "healthy",
        },
    }


def resolve_database_url(database_url: str | None) -> str:
    """Resolve the configured database URL or raise a clear error."""
    resolved_db_url = database_url or os.getenv("DATABASE_URL") or os.getenv("DATABASE_PATH")
    if not resolved_db_url:
        raise ValueError(
            "DATABASE_PATH ou DATABASE_URL nao definido. Defina no .env ou informe via --db-url."
        )
    return resolved_db_url


def build_factory_app_config(*, database_url: str, model_name: str) -> ApplicationConfig:
    return ApplicationConfig(
        database_type=infer_database_type(database_url),
        database_path=database_url,
        llm_provider="openai",
        llm_model=model_name,
    )


__all__ = [
    "AVAILABLE_OPENAI_MODELS",
    "build_application_config",
    "build_factory_app_config",
    "build_health_report",
    "build_orchestrator_error_result",
    "resolve_database_url",
]
