from types import SimpleNamespace

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from evaluation.runners.run_ablation import VARIANT_MAP
from src.agent.plan_gate import plan_gate_node
from src.agent.response import clarification_node
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
from src.agent.state_helpers import create_initial_messages_state
from src.agent.state_models import QueryRoute
from src.application.config.simple_config import OrchestratorConfig


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
    assert (
        route_after_schema(
            {
                "query_route": QueryRoute.DATABASE,
                "current_error": "LlamaIndex table selection failed",
                "schema_context": "",
            }
        )
        == "generate_response"
    )


def test_ablation_variants_cover_semantic_layer_components():
    assert OrchestratorConfig(disable_semantic_planner=True).disable_semantic_planner
    assert "V9" in VARIANT_MAP
    assert VARIANT_MAP["V9"].flags == {"disable_semantic_planner": True}
    assert VARIANT_MAP["V10"].flags == {"disable_semantic_plan_validation": True}
    assert VARIANT_MAP["V11"].flags == {"disable_semantic_contract_validation": True}
    assert VARIANT_MAP["V12"].flags == {"disable_semantic_repair_guidance": True}


def test_route_after_plan_gate_and_query_planner_cover_multi_and_cot():
    assert route_after_plan_gate({"needs_clarification": True}) == "clarification"
    assert (
        route_after_plan_gate(
            {"multi_query_allowed": True, "force_single_query": False, "plan_type": None}
        )
        == "query_planner"
    )


def test_plan_gate_routes_unsupported_schema_metric_to_clarification():
    state = create_initial_messages_state(
        "Qual o IDHM medio dos municipios do RS?",
        session_id="test-unsupported-schema-metric",
    )

    new_state = plan_gate_node(state)

    assert new_state["needs_clarification"] is True
    assert "schema atual" in (new_state["clarification_question"] or "")
    assert new_state["generated_sql"] is None
    assert new_state["response_metadata"]["unsupported_schema_metric"] == ["idhm"]

    clarified_state = clarification_node(new_state)
    assert clarified_state["final_response"] == new_state["clarification_question"]

    assert (
        route_after_plan_gate(
            {
                "multi_query_allowed": False,
                "force_single_query": False,
                "plan_type": "single_window",
            }
        )
        == "reasoning"
    )
    assert (
        route_after_query_planner(
            {"is_multi_query": True, "force_single_query": False, "plan_type": None}
        )
        == "multi"
    )
    assert (
        route_after_query_planner(
            {"is_multi_query": False, "force_single_query": False, "plan_type": "single_cte"}
        )
        == "reasoning"
    )


@pytest.mark.parametrize(
    ("question", "metric_name"),
    [
        ("Qual foi a cobertura vacinal dos internados?", "vacina"),
        ("Qual antibiótico foi usado em pneumonia?", "medicacao"),
        ("Qual o resultado dos exames laboratoriais?", "exames_laboratoriais"),
        ("Existe relação entre resultado de hemograma e mortalidade hospitalar?", "exames_laboratoriais"),
        ("Compare internações em área rural e urbana em 2021.", "area_rural_urbana"),
        ("Quais bairros de residencia aparecem com mais internacoes?", "bairro"),
        ("Compare renda individual do paciente entre MA e RS.", "renda_individual"),
        ("Existe relação entre plano de saude do paciente e mortalidade?", "plano_saude"),
        ("Qual a sobrevida após alta?", "sobrevida_pos_alta"),
        ("Qual a reinternação em 30 dias?", "reinternacao"),
        ("Qual o tempo ate consulta ambulatorial depois da internacao?", "consulta_ambulatorial"),
        ("Qual foi o resultado de imagem dos pacientes com pneumonia?", "resultado_imagem"),
        ("Compare pressao arterial na admissao entre MA e RS.", "sinais_vitais"),
    ],
)
def test_plan_gate_routes_new_unavailable_schema_metrics_to_clarification(
    question, metric_name
):
    state = create_initial_messages_state(
        question,
        session_id=f"test-unsupported-{metric_name}",
    )

    new_state = plan_gate_node(state)

    assert new_state["needs_clarification"] is True
    assert "schema atual" in (new_state["clarification_question"] or "")
    assert new_state["generated_sql"] is None
    assert metric_name in new_state["response_metadata"]["unsupported_schema_metric"]


def test_plan_gate_uses_user_facing_label_for_medication_unavailable_message():
    state = create_initial_messages_state(
        "Qual antibiotico foi usado em pneumonia?",
        session_id="test-unsupported-medication-label",
    )

    new_state = plan_gate_node(state)

    assert new_state["needs_clarification"] is True
    assert "medicamentos" in (new_state["clarification_question"] or "")
    assert "medicacao" not in (new_state["clarification_question"] or "")
    assert new_state["response_metadata"]["unsupported_schema_metric"] == ["medicacao"]


def test_plan_gate_explains_longitudinal_followup_unavailable_context():
    cases = [
        ("Qual a readmissao em 30 dias?", "identificador longitudinal", "reinternacao"),
        ("Qual a sobrevida um ano apos alta?", "seguimento", "sobrevida_pos_alta"),
    ]

    for question, expected_term, metric_name in cases:
        state = create_initial_messages_state(
            question,
            session_id=f"test-unsupported-context-{metric_name}",
        )

        new_state = plan_gate_node(state)

        assert new_state["needs_clarification"] is True
        assert expected_term in (new_state["clarification_question"] or "")
        assert new_state["response_metadata"]["unsupported_schema_metric"] == [metric_name]


def test_route_after_multi_verifier_and_repair():
    assert route_after_multi_verifier({"single_fallback_active": True}) == "generate_sql"
    assert route_after_multi_verifier({"single_fallback_active": False}) == "result_synthesizer"
    assert route_after_repair({"schema_refreshed": True}) == "reasoning"
    assert route_after_repair({"schema_refreshed": False}) == "validate_sql"


def test_route_after_sql_generation_and_validation_retry_logic():
    assert (
        route_after_sql_generation(
            {
                "total_workflow_cycles": 1,
                "generation_retry_count": 0,
                "generated_sql": "select 1",
                "current_error": None,
            }
        )
        == "validate"
    )
    assert (
        route_after_sql_generation(
            {
                "total_workflow_cycles": 1,
                "generation_retry_count": 0,
                "generated_sql": None,
                "current_error": "boom",
                "retry_count": 0,
                "max_retries": 3,
            }
        )
        == "retry"
    )

    assert (
        route_after_sql_validation(
            {
                "total_workflow_cycles": 1,
                "validation_retry_count": 0,
                "validated_sql": None,
                "current_error": "syntax error",
                "retry_count": 0,
                "max_retries": 3,
            }
        )
        == "retry_generation"
    )
    assert (
        route_after_sql_validation(
            {
                "total_workflow_cycles": 1,
                "validation_retry_count": 0,
                "validated_sql": None,
                "current_error": "CHART PLAN ERROR: last_n_available_years charts must use max year",
                "retry_count": 0,
                "max_retries": 3,
            }
        )
        == "retry_generation"
    )
    assert (
        route_after_sql_validation(
            {
                "total_workflow_cycles": 1,
                "validation_retry_count": 0,
                "validated_sql": None,
                "current_error": "AST CONTRACT ERROR: SQL join path for estado is invalid",
                "retry_count": 0,
                "max_retries": 3,
            }
        )
        == "retry_generation"
    )
    assert (
        route_after_sql_validation(
            {
                "total_workflow_cycles": 1,
                "validation_retry_count": 0,
                "validated_sql": None,
                "current_error": "SEMANTIC PLAN ERROR: Time-series SQL filters metric values",
                "retry_count": 0,
                "max_retries": 3,
            }
        )
        == "retry_generation"
    )
    assert (
        route_after_sql_validation(
            {
                "total_workflow_cycles": 1,
                "validation_retry_count": 0,
                "validated_sql": None,
                "current_error": "business rule mismatch",
                "retry_count": 0,
                "max_retries": 3,
            }
        )
        == "retry_validation"
    )


def test_route_after_sql_execution_routes_success_and_infra_retries():
    success_result = SimpleNamespace(success=True)
    assert (
        route_after_sql_execution(
            {
                "total_workflow_cycles": 0,
                "sql_execution_result": success_result,
                "current_error": None,
            }
        )
        == "response"
    )

    assert (
        route_after_sql_execution(
            {
                "total_workflow_cycles": 0,
                "sql_execution_result": None,
                "current_error": "database timeout",
                "retry_count": 0,
                "max_retries": 3,
            }
        )
        == "retry_execution"
    )
