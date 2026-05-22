from src.agent.sql_generation import _build_deterministic_chart_sql, generate_sql_node
from src.agent.state_helpers import create_initial_messages_state
from src.semantic.planner import build_semantic_plan
from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
from src.visualization.intent import detect_visualization_intent

TARGET_QUERY = (
    "gere um grafico mostrando o numero de mortes de crianca por causas "
    "respiratorias nos ultimos 5 anos"
)


def test_semantic_plan_resolves_target_query_without_literal_diagnosis_fragment():
    plan = build_semantic_plan(TARGET_QUERY)

    assert any(
        filter_.field == "idade" and filter_.operator == "<" and filter_.values == ["18"]
        for filter_ in plan.filters
    )
    assert any(
        filter_.field == "diagnostico_principal_prefix" and filter_.values == ["J%"]
        for filter_ in plan.filters
    )
    assert not any(
        filter_.field == "diagnostico_principal_descricao"
        and "crianca por causas respiratorias" in " ".join(filter_.values)
        for filter_ in plan.filters
    )


def test_chart_sql_for_target_query_satisfies_chart_contract():
    semantic_plan = build_semantic_plan(TARGET_QUERY)
    chart_plan = build_chart_plan(TARGET_QUERY, detect_visualization_intent(TARGET_QUERY))

    sql = _build_deterministic_chart_sql(semantic_plan, chart_plan)

    assert sql is not None
    assert 'EXTRACT(YEAR FROM i."DT_INTER") AS ano' in sql
    assert "COUNT(*) AS total_mortes" in sql
    assert 'i."MORTE" = true' in sql
    assert 'i."IDADE" < 18' in sql
    assert 'i."DIAG_PRINC" LIKE \'J%\'' in sql
    assert 'MAX(EXTRACT(YEAR FROM "DT_INTER")) FROM internacoes' in sql
    passed, message = validate_sql_against_chart_plan(chart_plan, sql)
    assert passed is True, message


def test_generate_sql_node_prioritizes_chart_sql_for_chart_requests():
    semantic_plan = build_semantic_plan(TARGET_QUERY)
    chart_plan = build_chart_plan(TARGET_QUERY, detect_visualization_intent(TARGET_QUERY))
    state = create_initial_messages_state(user_query=TARGET_QUERY, session_id="chart-priority")
    state["semantic_plan"] = semantic_plan.model_dump()
    state["chart_plan"] = chart_plan.model_dump()
    state["schema_context"] = "TABLE internacoes; TABLE cid;"
    state["selected_tables"] = ["internacoes", "cid"]

    new_state = generate_sql_node(state)

    assert "deterministic_chart" in new_state["messages"][-1].content
    assert 'EXTRACT(YEAR FROM i."DT_INTER") AS ano' in new_state["generated_sql"]
    assert "analysis_type" not in new_state["generated_sql"]
