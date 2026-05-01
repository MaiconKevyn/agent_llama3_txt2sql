import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..application.config.simple_config import ApplicationConfig


AVAILABLE_OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo-0125",
]


def build_application_config(
    base_config: ApplicationConfig,
    *,
    model_name: str,
    temperature: Optional[float] = None,
    timeout: Optional[int] = None,
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
) -> Tuple[Any, Any, sqlite3.Connection, Any, Any]:
    """Initialize workflow runtime components used by the orchestrator."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    from .llm_manager import OpenAILLMManager
    from .workflow import (
        create_development_sql_agent,
        create_production_sql_agent,
        create_testing_sql_agent,
    )

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

    workflow_factory = {
        "production": create_production_sql_agent,
        "development": create_development_sql_agent,
        "testing": create_testing_sql_agent,
    }.get(environment, create_production_sql_agent)
    workflow = workflow_factory(checkpointer=memory)

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


def build_langsmith_config(
    *,
    config: Optional[dict],
    session_id: str,
    query_number: int,
    current_model_metadata: Dict[str, Any],
    environment: str,
    run_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    """Build the LangSmith config used for workflow execution."""
    langsmith_config = dict(config or {})
    if run_name:
        langsmith_config["run_name"] = run_name
    if tags:
        langsmith_config["tags"] = tags
    if metadata:
        langsmith_config["metadata"] = metadata

    if "configurable" not in langsmith_config:
        langsmith_config["configurable"] = {}
    langsmith_config["configurable"]["thread_id"] = session_id

    default_metadata = {
        "session_id": session_id,
        "query_number": query_number,
        "model_provider": current_model_metadata["provider"],
        "model_name": current_model_metadata["model_name"],
        "environment": environment,
    }
    if "metadata" in langsmith_config:
        langsmith_config["metadata"].update(default_metadata)
    else:
        langsmith_config["metadata"] = default_metadata

    return langsmith_config


def build_tracing_context(
    *,
    user_query: str,
    project_name: str,
    current_model_metadata: Dict[str, Any],
    environment: str,
    query_number: int,
) -> Tuple[str, List[str], Dict[str, Any]]:
    """Build run name, tags and metadata for traced execution."""
    run_name = f"txt2sql_query_{query_number}"
    tags = [
        f"model:{current_model_metadata['model_name']}",
        f"provider:{current_model_metadata['provider']}",
        f"env:{environment}",
        "txt2sql",
        "langgraph-v3",
    ]
    metadata = {
        "project": project_name,
        "orchestrator_version": "3.0",
        "user_query_length": len(user_query),
        "user_query_preview": user_query[:100] + "..." if len(user_query) > 100 else user_query,
    }
    return run_name, tags, metadata


def build_orchestrator_error_result(
    *,
    user_query: str,
    execution_time: float,
    error: Exception,
    current_model_metadata: Dict[str, Any],
    environment: str,
) -> Dict[str, Any]:
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
    current_model_metadata: Dict[str, Any],
    workflow_available: bool,
    llm_health: Dict[str, Any],
    metrics,
) -> Dict[str, Any]:
    """Build the health payload returned by the orchestrator."""
    workflow_status = "healthy" if workflow_available else "failed"
    overall_status = (
        "healthy"
        if llm_health.get("status") == "healthy" and workflow_status == "healthy"
        else "degraded"
    )

    success_rate = (
        metrics.successful_queries / metrics.total_queries
        if metrics.total_queries > 0
        else 0
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


def resolve_database_url(database_url: Optional[str]) -> str:
    """Resolve the configured database URL or raise a clear error."""
    resolved_db_url = database_url or os.getenv("DATABASE_URL") or os.getenv("DATABASE_PATH")
    if not resolved_db_url:
        raise ValueError(
            "DATABASE_URL não definido. Defina no .env ou informe via --db-url."
        )
    return resolved_db_url


def build_factory_app_config(*, database_url: str, model_name: str) -> ApplicationConfig:
    """Build the application config used by orchestrator factory functions."""
    return ApplicationConfig(
        database_type="postgresql",
        database_path=database_url,
        llm_provider="openai",
        llm_model=model_name,
    )


__all__ = [
    "AVAILABLE_OPENAI_MODELS",
    "build_application_config",
    "build_factory_app_config",
    "build_health_report",
    "build_langsmith_config",
    "build_orchestrator_error_result",
    "build_tracing_context",
    "initialize_orchestrator_runtime",
    "resolve_database_url",
]
