from src.agent.orchestrator_support import (
    AVAILABLE_OPENAI_MODELS,
    build_application_config,
    build_health_report,
    build_langsmith_config,
    build_orchestrator_error_result,
    build_tracing_context,
)
from src.application.config.simple_config import ApplicationConfig


class DummyMetrics:
    total_queries = 4
    successful_queries = 3


def test_build_application_config_preserves_base_settings():
    base = ApplicationConfig(
        database_type="postgresql",
        database_path="db-url",
        llm_model="gpt-4o-mini",
        llm_temperature=0.0,
        llm_timeout=120,
    )

    updated = build_application_config(
        base,
        model_name="gpt-4o",
        temperature=0.3,
        timeout=45,
    )

    assert updated.database_path == "db-url"
    assert updated.llm_model == "gpt-4o"
    assert updated.llm_temperature == 0.3
    assert updated.llm_timeout == 45


def test_build_langsmith_config_merges_defaults_and_user_metadata():
    config = build_langsmith_config(
        config={"metadata": {"source": "test"}},
        session_id="session-1",
        query_number=7,
        current_model_metadata={"provider": "openai", "model_name": "gpt-4o-mini"},
        environment="testing",
        run_name="custom-run",
        tags=["tag-a"],
    )

    assert config["run_name"] == "custom-run"
    assert config["tags"] == ["tag-a"]
    assert config["configurable"]["thread_id"] == "session-1"
    assert config["metadata"]["source"] == "test"
    assert config["metadata"]["query_number"] == 7


def test_build_tracing_context_and_health_report():
    run_name, tags, metadata = build_tracing_context(
        user_query="Quantas internações ocorreram em 2020?",
        project_name="txt2sql-agent",
        current_model_metadata={"provider": "openai", "model_name": "gpt-4o-mini"},
        environment="development",
        query_number=9,
    )

    assert run_name == "txt2sql_query_9"
    assert "langgraph-v3" in tags
    assert metadata["project"] == "txt2sql-agent"

    report = build_health_report(
        environment="development",
        current_model_metadata={"provider": "openai", "model_name": "gpt-4o-mini"},
        workflow_available=True,
        llm_health={"status": "healthy"},
        metrics=DummyMetrics(),
    )
    assert report["status"] == "healthy"
    assert report["orchestrator"]["success_rate"] == 0.75
    assert report["current_model"]["available"] is True


def test_build_orchestrator_error_result_and_model_list():
    payload = build_orchestrator_error_result(
        user_query="teste",
        execution_time=1.2,
        error=RuntimeError("boom"),
        current_model_metadata={"provider": "openai", "model_name": "gpt-4o-mini"},
        environment="testing",
    )

    assert payload["success"] is False
    assert "boom" in payload["error_message"]
    assert "gpt-4o-mini" in AVAILABLE_OPENAI_MODELS
