from src.agent.execution import repair_sql_node
from src.agent.state_helpers import create_initial_messages_state
from src.semantic.plan_schema import AnswerShape, SemanticFilter, SemanticMetric, SemanticPlan


class _FakeLLMManager:
    def invoke_chat(self, _messages):
        raise AssertionError("shape-aware deterministic repair should not fall back to LLM")


def _patch_llm(monkeypatch):
    monkeypatch.setattr("src.agent.execution.get_llm_manager", lambda: _FakeLLMManager())


def _repair_state(query: str, plan: SemanticPlan, *, chart_plan: dict | None = None):
    state = create_initial_messages_state(query, session_id="repair-test", chart_plan=chart_plan)
    state["generated_sql"] = "SELECT broken_sql"
    state["semantic_plan"] = plan.model_dump(exclude_none=True)
    state["current_error"] = "SEMANTIC PLAN ERROR: percentage denominator must match filtered category."
    state["ablation_flags"] = {"enable_analytic_response_templates": False}
    return state


def test_shape_preserving_repair_candidate_is_accepted_with_metadata(monkeypatch):
    _patch_llm(monkeypatch)
    plan = SemanticPlan(
        intent="distribution",
        base_grain="internacao",
        metrics=[SemanticMetric(name="percentual", expression_type="rate")],
        filters=[
            SemanticFilter(field="diagnostico_principal_prefix", values=["J%"], operator="LIKE")
        ],
        answer_shape=AnswerShape(
            row_grain="one_row_per_group",
            required_dimensions=["trimestre"],
            requires_group_by=True,
            answer_kind="grouped_table",
            expected_row_count="one_per_group",
        ),
        constraints=["percentage_denominator_matches_filtered_category"],
    )
    state = _repair_state(
        "percentual de internacoes respiratorias por trimestre",
        plan,
        chart_plan={
            "requested": True,
            "required_columns": ["trimestre", "percentual"],
            "x_dimension": "trimestre",
            "y_column": "percentual",
        },
    )

    updated = repair_sql_node(state)
    repair_meta = updated["response_metadata"]["semantic_repair"]

    assert updated["current_error"] is None
    assert "GROUP BY EXTRACT(QUARTER" in updated["generated_sql"]
    assert repair_meta["accepted_repair_candidate"]["strategy"] == (
        "filtered_category_period_percentage_macro"
    )
    assert repair_meta["rejected_repair_candidates"] == []


def test_diagnosis_lookup_repair_is_rejected_for_time_series_chart_columns(monkeypatch):
    _patch_llm(monkeypatch)
    plan = SemanticPlan(
        intent="trend",
        base_grain="internacao",
        metrics=[SemanticMetric(name="total_mortes", expression_type="count")],
        filters=[
            SemanticFilter(field="diagnostico_principal_prefix", values=["J%"], operator="LIKE"),
            SemanticFilter(field="ano", values=["2021", "2022", "2023"], operator="IN"),
            SemanticFilter(field="desfecho", values=["MORTE = true"], operator="semantic"),
        ],
        answer_shape=AnswerShape(
            row_grain="time_series",
            required_dimensions=["ano"],
            requires_group_by=True,
            answer_kind="time_series",
            expected_row_count="one_per_group",
            output_dimensions=["ano"],
        ),
        constraints=["diagnosis_concept_resolution_required"],
    )
    state = _repair_state(
        "me mostre um grafico de mortes por causa respiratorias em 2021, 2022 e 2023",
        plan,
        chart_plan={
            "requested": True,
            "required_columns": ["ano", "total_mortes"],
            "x_dimension": "ano",
            "y_column": "total_mortes",
        },
    )
    state["current_error"] = (
        "SEMANTIC PLAN ERROR: diagnosis description lookup is missing expanded term(s): "
        "respiratorias."
    )

    updated = repair_sql_node(state)
    repair_meta = updated["response_metadata"]["semantic_repair"]

    assert updated["generated_sql"] == "SELECT broken_sql"
    assert "could not preserve the requested answer shape" in updated["current_error"]
    assert repair_meta["accepted_repair_candidate"] is None
    assert repair_meta["rejected_repair_candidates"][0]["strategy"] == (
        "diagnosis_description_lookup_macro"
    )
    assert "CHART PLAN ERROR" in repair_meta["rejected_repair_candidates"][0]["reason"]
