from evaluation.agent.intent_generalization_rubric import (
    build_intent_generalization_trace,
    load_intent_generalization_questions,
    score_intent_generalization,
)


def _question_by_id(question_id: str):
    return next(item for item in load_intent_generalization_questions() if item.id == question_id)


def test_rubric_passes_target_chart_contract_without_exact_query_matching():
    item = _question_by_id("resp_child_deaths_chart_002")

    trace = build_intent_generalization_trace(item.question)
    score = score_intent_generalization(item, trace)

    assert score["passed"], score
    assert "child_age_policy" in score["resolved_concepts"]
    assert "respiratory_cid" in score["resolved_concepts"]
    assert trace.chart_sql_valid is True
    assert trace.generated_chart_sql


def test_rubric_rejects_near_miss_respiratory_overtrigger():
    item = _question_by_id("near_miss_external_causes_001")

    trace = build_intent_generalization_trace(item.question)
    score = score_intent_generalization(item, trace)

    assert score["passed"], score
    assert "respiratory_cid" not in score["resolved_concepts"]


def test_rubric_identifies_safe_refusal_scope():
    item = _question_by_id("out_scope_antibiotic_001")

    trace = build_intent_generalization_trace(item.question)
    score = score_intent_generalization(item, trace)

    assert score["passed"], score
    assert "unsupported_medication" in score["resolved_concepts"]
