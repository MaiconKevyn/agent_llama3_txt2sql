from src.semantic.plan_reconciler import reconcile_semantic_plans
from src.semantic.plan_schema import AnswerShape, SemanticMetric, SemanticPlan
from src.semantic.planner import build_semantic_plan


def test_reconciler_preserves_heuristic_top_n_per_group_over_llm_global_top_n():
    heuristic = build_semantic_plan("Quais são os 5 procedimentos mais comuns para cada sexo?")
    llm = SemanticPlan(
        intent="ranking",
        base_grain="procedimento_ocorrencia",
        metrics=[SemanticMetric(name="total_internacoes", expression_type="count")],
        answer_shape=AnswerShape(
            row_grain="top_n_global",
            top_n=5,
            top_n_scope="global",
            required_dimensions=["sexo"],
            requires_group_by=True,
        ),
    )

    result = reconcile_semantic_plans(heuristic, llm)

    assert result.reconciled_plan.answer_shape.top_n_scope == "per_group"
    assert result.reconciled_plan.answer_shape.row_grain == "top_n_per_group"
    assert any("top_n_scope_mismatch" in conflict for conflict in result.conflicts)
    assert not any("top_n_scope_mismatch" in item for item in result.reconciled_plan.ambiguities)


def test_reconciler_keeps_rate_denominator_constraint_when_llm_omits_it():
    heuristic = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    llm = SemanticPlan(
        intent="trend",
        base_grain="internacao",
        metrics=[SemanticMetric(name="taxa_mortalidade", expression_type="rate")],
        answer_shape=AnswerShape(
            row_grain="time_series",
            required_dimensions=["estado", "ano"],
            requires_group_by=True,
        ),
    )

    result = reconcile_semantic_plans(heuristic, llm)

    assert "rate_denominator_must_preserve_full_scope" in result.reconciled_plan.constraints
    assert result.reconciled_plan.answer_shape.required_dimensions == ["estado", "ano"]


def test_reconciler_accepts_llm_dimension_when_heuristic_is_unknown():
    heuristic = SemanticPlan()
    llm = SemanticPlan(
        intent="count",
        base_grain="internacao",
        answer_shape=AnswerShape(row_grain="one_row_per_group", required_dimensions=["estado"]),
    )

    result = reconcile_semantic_plans(heuristic, llm)

    assert result.reconciled_plan.intent == "count"
    assert result.reconciled_plan.answer_shape.required_dimensions == ["estado"]
    assert "intent" in result.accepted_llm_fields
