from src.semantic.plan_reconciler import reconcile_semantic_plans
from src.semantic.plan_schema import (
    AnswerShape,
    SemanticDimension,
    SemanticFilter,
    SemanticMetric,
    SemanticPlan,
)


def _count_metric() -> SemanticMetric:
    return SemanticMetric(name="total", expression_type="count")


def _weak_scalar_year_filter_plan() -> SemanticPlan:
    return SemanticPlan(
        intent="count",
        base_grain="internacao",
        metrics=[_count_metric()],
        filters=[SemanticFilter(field="ano", values=["2021", "2022", "2023"], operator="IN")],
        answer_shape=AnswerShape(
            row_grain="single_scalar",
            answer_kind="scalar",
            expected_row_count="one",
        ),
    )


def _candidate_time_series_plan() -> SemanticPlan:
    return SemanticPlan(
        intent="trend",
        base_grain="internacao",
        metrics=[_count_metric()],
        dimensions=[
            SemanticDimension(
                name="ano",
                source='EXTRACT(YEAR FROM internacoes."DT_INTER")',
            )
        ],
        filters=[SemanticFilter(field="ano", values=["2021", "2022", "2023"], operator="IN")],
        answer_shape=AnswerShape(
            row_grain="time_series",
            required_dimensions=["ano"],
            requires_group_by=True,
            answer_kind="time_series",
            expected_row_count="one_per_group",
            output_dimensions=["ano"],
        ),
    )


def test_weak_scalar_heuristic_accepts_valid_time_series_candidate():
    result = reconcile_semantic_plans(
        _weak_scalar_year_filter_plan(),
        _candidate_time_series_plan(),
        chart_plan={"requested": True, "required_columns": ["ano", "total_mortes"]},
    )

    assert result.reconciled_plan.answer_shape.row_grain == "time_series"
    assert result.reconciled_plan.answer_shape.required_dimensions == ["ano"]
    assert result.reconciled_plan.answer_shape.requires_group_by is True
    assert "answer_shape.row_grain" in result.accepted_llm_fields
    assert "answer_shape.row_grain" in result.accepted_llm_field_reasons
    assert "answer_shape.row_grain" not in result.rejected_llm_fields


def test_explicit_scalar_heuristic_rejects_grouped_candidate():
    result = reconcile_semantic_plans(
        _weak_scalar_year_filter_plan(),
        _candidate_time_series_plan(),
        user_query="me mostre o total de mortes somando 2021, 2022 e 2023",
        chart_plan={"requested": True, "required_columns": ["total_mortes"]},
    )

    assert result.reconciled_plan.answer_shape.row_grain == "single_scalar"
    assert result.reconciled_plan.answer_shape.required_dimensions == []
    assert "answer_shape.row_grain" in result.rejected_llm_fields
    assert "answer_shape.row_grain" in result.rejected_llm_field_reasons


def test_weak_scalar_heuristic_accepts_valid_grouped_candidate_from_query_evidence():
    heuristic = SemanticPlan(
        intent="count",
        base_grain="internacao",
        metrics=[_count_metric()],
        answer_shape=AnswerShape(
            row_grain="single_scalar",
            answer_kind="scalar",
            expected_row_count="one",
        ),
    )
    candidate = SemanticPlan(
        intent="distribution",
        base_grain="internacao",
        metrics=[_count_metric()],
        dimensions=[SemanticDimension(name="sexo", source='internacoes."SEXO"')],
        answer_shape=AnswerShape(
            row_grain="one_row_per_group",
            required_dimensions=["sexo"],
            requires_group_by=True,
            answer_kind="grouped_table",
            expected_row_count="one_per_group",
            output_dimensions=["sexo"],
        ),
    )

    result = reconcile_semantic_plans(
        heuristic,
        candidate,
        user_query="quantas mortes por sexo",
    )

    assert result.reconciled_plan.answer_shape.row_grain == "one_row_per_group"
    assert result.reconciled_plan.answer_shape.required_dimensions == ["sexo"]
    assert "dimensions" in result.accepted_llm_fields
    assert "dimensions" in result.accepted_llm_field_reasons


def test_semantic_planner_metadata_records_original_scalar_time_series_upgrade(monkeypatch):
    from src.agent.semantic_planner import semantic_planner_node
    from src.agent.state_helpers import create_initial_messages_state

    query = (
        "me mostre um grafico mostrando o numero total de mortes por causa respiratorias "
        "em 2021, 2022 e 2023"
    )

    class FakeLLMManager:
        def invoke_chat_structured(self, _messages, schema):
            return schema(
                semantic_plan=_candidate_time_series_plan(),
                reasoning="O grafico precisa de uma linha por ano.",
                confidence=0.91,
            )

    monkeypatch.setattr(
        "src.agent.semantic_planner.get_llm_manager",
        lambda: FakeLLMManager(),
    )

    state = create_initial_messages_state(
        query,
        session_id="test-session",
        chart_plan={
            "requested": True,
            "required_columns": ["ano", "total_mortes"],
            "x_dimension": "ano",
        },
    )
    state["semantic_plan"] = _weak_scalar_year_filter_plan().model_dump(exclude_none=True)
    state["selected_tables"] = ["internacoes"]

    updated = semantic_planner_node(state)
    planner_meta = updated["response_metadata"]["semantic_planner"]

    assert planner_meta["mode"] == "llm_reconciled"
    assert updated["semantic_plan"]["answer_shape"]["row_grain"] == "time_series"
    assert updated["semantic_plan"]["answer_shape"]["required_dimensions"] == ["ano"]
    assert planner_meta["accepted_llm_field_reasons"]["answer_shape.row_grain"]
    assert "answer_shape.row_grain" not in planner_meta["rejected_llm_fields"]
