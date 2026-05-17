import os
import sqlite3
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
        llm_temperature=temperature or base_config.llm_temperature,
        llm_timeout=timeout or base_config.llm_timeout,
        llm_max_retries=base_config.llm_max_retries,
        schema_type=base_config.schema_type,
        ui_type=base_config.ui_type,
        interface_type=base_config.interface_type,
        error_handling_type=base_config.error_handling_type,
        enable_error_logging=base_config.enable_error_logging,
        query_processing_type=base_config.query_processing_type,
    )


def initialize_orchestrator_runtime(
    app_config: ApplicationConfig,
    environment: str,
    logger,
    model_config_factory,
    orchestrator_config=None,
) -> tuple[Any, Any, sqlite3.Connection, Any, Any]:
    """Initialize workflow runtime components used by the orchestrator."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    from .llm_manager import OpenAILLMManager
    from .workflow import create_langgraph_sql_workflow

    llm_manager = OpenAILLMManager(app_config)

    from .nodes import set_global_llm_manager

    set_global_llm_manager(llm_manager)
    logger.info(
        "LLM Manager created and injected into nodes",
        extra={"provider": "openai", "model": app_config.llm_model},
    )

    os.makedirs("data", exist_ok=True)
    memory_conn = sqlite3.connect("data/chatbot_memory.db", check_same_thread=False)
    memory = SqliteSaver(memory_conn)

    workflow = create_langgraph_sql_workflow(config=orchestrator_config).compile(
        checkpointer=memory
    )

    current_model = model_config_factory(
        model_name=app_config.llm_model,
        temperature=app_config.llm_temperature,
        timeout=app_config.llm_timeout,
        max_retries=app_config.llm_max_retries,
    )

    logger.info(
        "LangGraph Orchestrator initialized",
        extra={
            "environment": environment,
            "model": current_model.model_name,
            "provider": current_model.provider,
        },
    )
    return workflow, memory, memory_conn, llm_manager, current_model


def build_workflow_config(
    *,
    config: dict | None,
    session_id: str,
) -> dict:
    """Build the LangGraph workflow config.

    Provides the ``configurable.thread_id`` required by SqliteSaver for
    session checkpointing.  Any caller-supplied config keys are preserved.
    """
    workflow_config = dict(config or {})
    if "configurable" not in workflow_config:
        workflow_config["configurable"] = {}
    workflow_config["configurable"]["thread_id"] = session_id
    return workflow_config


def build_orchestrator_error_result(
    *,
    user_query: str,
    execution_time: float,
    error: Exception,
    current_model_metadata: dict[str, Any],
    environment: str,
) -> dict[str, Any]:
    """Build the standardized orchestrator-level error payload."""
    return {
        "success": False,
        "question": user_query,
        "sql_query": None,
        "results": [],
        "row_count": 0,
        "execution_time": execution_time,
        "error_message": f"Orchestrator error: {str(error)}",
        "response": f"Erro do sistema: {str(error)}",
        "timestamp": datetime.now().isoformat(),
        "metadata": {
            "orchestrator_v3": True,
            "orchestrator_error": True,
            "error_type": "orchestrator_execution_error",
            "current_model": {
                "provider": current_model_metadata["provider"],
                "model_name": current_model_metadata["model_name"],
            },
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
    """Build the health payload returned by the orchestrator."""
    workflow_status = "healthy" if workflow_available else "failed"
    overall_status = (
        "healthy"
        if llm_health.get("status") == "healthy" and workflow_status == "healthy"
        else "degraded"
    )

    success_rate = (
        metrics.successful_queries / metrics.total_queries if metrics.total_queries > 0 else 0
    )

    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "orchestrator": {
            "version": "3.0",
            "environment": environment,
            "workflow_status": workflow_status,
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
            "DATABASE_PATH ou DATABASE_URL não definido. Defina no .env ou informe via --db-url."
        )
    return resolved_db_url


def build_factory_app_config(*, database_url: str, model_name: str) -> ApplicationConfig:
    """Build the application config used by orchestrator factory functions."""
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
    "build_workflow_config",
    "initialize_orchestrator_runtime",
    "resolve_database_url",
]
