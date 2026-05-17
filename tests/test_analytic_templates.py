from src.agent.plan_gate import plan_gate_node
from src.agent.state_helpers import create_initial_messages_state
from src.semantic.analytic_templates import analytic_metadata_for_plan, select_analytic_template
from src.semantic.planner import build_semantic_plan


def test_selects_numeric_factor_template_for_age_diagnosis_association():
    plan = build_semantic_plan("Existe relação entre idade e câncer de próstata?")

    template = select_analytic_template(plan)

    assert template is not None
    assert template.id == "numeric_factor_by_condition"
    assert "denominator" in template.required_sections
    assert "group_distribution" in template.required_sections


def test_selects_categorical_factor_template_for_race_mortality_association():
    plan = build_semantic_plan("Qual a relação entre raça/cor e mortalidade?")

    template = select_analytic_template(plan)

    assert plan.intent == "association"
    assert template is not None
    assert template.id == "categorical_factor_by_outcome"
    assert "raca_cor" in template.factor_dimensions


def test_selects_temporal_trend_template_for_annual_respiratory_disease_trend():
    plan = build_semantic_plan("Qual a tendência anual de doenças respiratórias?")

    template = select_analytic_template(plan)

    assert template is not None
    assert template.id == "temporal_trend_by_condition"
    assert "ano" in template.factor_dimensions


def test_analytic_metadata_exposes_template_and_concept_resolution():
    plan = build_semantic_plan("Existe relação entre idade e doenças pulmonares?")

    metadata = analytic_metadata_for_plan(plan)

    assert metadata["analytic_intent"] == "association"
    assert metadata["analytic_template"] == "numeric_factor_by_condition"
    assert metadata["concept_resolution"]["diagnosis_prefixes"] == ["J%"]
    assert metadata["denominator_policy"] == "same_scope_without_target_condition_by_age_band"


def test_plan_gate_adds_analytic_metadata_to_response_metadata():
    state = create_initial_messages_state(
        "Existe relação entre idade e doenças pulmonares?",
        session_id="analytic_metadata_test",
    )

    updated = plan_gate_node(state)
    metadata = updated["response_metadata"]

    assert metadata["analytic_intent"] == "association"
    assert metadata["analytic_template"] == "numeric_factor_by_condition"
    assert metadata["concept_resolution"]["diagnosis_prefixes"] == ["J%"]
