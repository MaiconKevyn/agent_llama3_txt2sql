from src.agent.intent_plan import build_intent_plan


def test_intent_plan_extracts_target_chart_slots():
    plan = build_intent_plan(
        "gere um grafico mostrando o numero de mortes de crianca por causas respiratorias nos ultimos 5 anos"
    )

    assert plan.presentation == "chart"
    assert plan.primary_task == "trend"
    assert plan.temporal_scope is not None
    assert plan.temporal_scope.type == "last_n_available_years"
    assert plan.temporal_scope.n == 5
    assert any(metric.name == "total_mortes" for metric in plan.metric_slots)
    assert any(slot.concept_type == "clinical" for slot in plan.concept_slots)
    assert any(slot.name == "population_group" for slot in plan.cohort_slots)
    assert any(group.name == "ano" for group in plan.grouping_slots)


def test_intent_plan_marks_out_of_scope_questions_for_refusal():
    plan = build_intent_plan("qual antibiotico foi administrado para pneumonia?")

    assert plan.primary_task == "out_of_scope"
    assert plan.requires_clarification is True
    assert plan.uncertainty


def test_intent_plan_keeps_direct_question_as_text_metric():
    plan = build_intent_plan("quantas mortes por doencas respiratorias ocorreram em 2021?")

    assert plan.presentation == "text"
    assert plan.primary_task == "direct_metric"
    assert any(metric.name == "total_mortes" for metric in plan.metric_slots)
    assert plan.temporal_scope is not None
    assert plan.temporal_scope.type == "year"
