from types import SimpleNamespace

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from src.agent.routing import (
    route_after_classification,
    route_after_multi_verifier,
    route_after_plan_gate,
    route_after_query_planner,
    route_after_repair,
    route_after_schema,
    route_after_sql_execution,
    route_after_sql_generation,
    route_after_sql_validation,
)
from src.agent.state_models import QueryRoute


def test_route_after_classification_handles_conversational_threshold():
    state = {
        "current_error": None,
        "query_route": QueryRoute.CONVERSATIONAL,
        "classification": SimpleNamespace(confidence_score=0.8),
        "needs_clarification": False,
    }
    assert route_after_classification(state) == "conversational"

    state["classification"] = SimpleNamespace(confidence_score=0.5)
    assert route_after_classification(state) == "database"


def test_route_after_schema_routes_schema_queries_to_response():
    assert route_after_schema({"query_route": QueryRoute.SCHEMA}) == "generate_response"
    assert route_after_schema({"query_route": QueryRoute.DATABASE}) == "plan_gate"


def test_route_after_plan_gate_and_query_planner_cover_multi_and_cot():
    assert route_after_plan_gate(
        {"multi_query_allowed": True, "force_single_query": False, "plan_type": None}
    ) == "query_planner"
    assert route_after_plan_gate(
        {"multi_query_allowed": False, "force_single_query": False, "plan_type": "single_window"}
    ) == "reasoning"
    assert route_after_query_planner(
        {"is_multi_query": True, "force_single_query": False, "plan_type": None}
    ) == "multi"
    assert route_after_query_planner(
        {"is_multi_query": False, "force_single_query": False, "plan_type": "single_cte"}
    ) == "reasoning"


def test_route_after_multi_verifier_and_repair():
    assert route_after_multi_verifier({"single_fallback_active": True}) == "generate_sql"
    assert route_after_multi_verifier({"single_fallback_active": False}) == "result_synthesizer"
    assert route_after_repair({"schema_refreshed": True}) == "reasoning"
    assert route_after_repair({"schema_refreshed": False}) == "validate_sql"


def test_route_after_sql_generation_and_validation_retry_logic():
    assert route_after_sql_generation(
        {
            "total_workflow_cycles": 1,
            "generation_retry_count": 0,
            "generated_sql": "select 1",
            "current_error": None,
        }
    ) == "validate"
    assert route_after_sql_generation(
        {
            "total_workflow_cycles": 1,
            "generation_retry_count": 0,
            "generated_sql": None,
            "current_error": "boom",
            "retry_count": 0,
            "max_retries": 3,
        }
    ) == "retry"

    assert route_after_sql_validation(
        {
            "total_workflow_cycles": 1,
            "validation_retry_count": 0,
            "validated_sql": None,
            "current_error": "syntax error",
            "retry_count": 0,
            "max_retries": 3,
        }
    ) == "retry_generation"
    assert route_after_sql_validation(
        {
            "total_workflow_cycles": 1,
            "validation_retry_count": 0,
            "validated_sql": None,
            "current_error": "business rule mismatch",
            "retry_count": 0,
            "max_retries": 3,
        }
    ) == "retry_validation"


def test_route_after_sql_execution_routes_success_and_infra_retries():
    success_result = SimpleNamespace(success=True)
    assert route_after_sql_execution(
        {
            "total_workflow_cycles": 0,
            "sql_execution_result": success_result,
            "current_error": None,
        }
    ) == "response"

    assert route_after_sql_execution(
        {
            "total_workflow_cycles": 0,
            "sql_execution_result": None,
            "current_error": "database timeout",
            "retry_count": 0,
            "max_retries": 3,
        }
    ) == "retry_execution"
