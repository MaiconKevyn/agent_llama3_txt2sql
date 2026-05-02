from src.agent.orchestrator_support import (
    AVAILABLE_OPENAI_MODELS,
    build_application_config,
    build_health_report,
    build_orchestrator_error_result,
    build_workflow_config,
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


def test_build_workflow_config_sets_thread_id():
    config = build_workflow_config(
        config={"recursion_limit": 50},
        session_id="session-42",
    )

    assert config["configurable"]["thread_id"] == "session-42"
    assert config["recursion_limit"] == 50


def test_build_workflow_config_no_extra_config():
    config = build_workflow_config(config=None, session_id="abc")

    assert config["configurable"]["thread_id"] == "abc"
    assert set(config.keys()) == {"configurable"}


def test_build_health_report():
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
