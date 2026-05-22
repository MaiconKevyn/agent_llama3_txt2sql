from src.agent.sql_generation import generate_sql_node
from src.agent.state_helpers import create_initial_messages_state
from src.semantic.planner import build_semantic_plan
from src.visualization.chart_plan import build_chart_plan
from src.visualization.intent import detect_visualization_intent

TARGET_QUERY = (
    "gere um grafico mostrando o numero de mortes de crianca por "
    "causas respiratorias nos ultimos 5 anos"
)


def test_sql_generation_records_plan_audit_for_chart_request():
    semantic_plan = build_semantic_plan(TARGET_QUERY)
    chart_plan = build_chart_plan(TARGET_QUERY, detect_visualization_intent(TARGET_QUERY))
    state = create_initial_messages_state(user_query=TARGET_QUERY, session_id="audit-sql")
    state["semantic_plan"] = semantic_plan.model_dump()
    state["chart_plan"] = chart_plan.model_dump()
    state["schema_context"] = "TABLE internacoes; TABLE cid;"
    state["selected_tables"] = ["internacoes", "cid"]

    new_state = generate_sql_node(state)

    assert new_state["plan_audit"]["passed"] is True
    assert new_state["structured_error"] is None


def test_chart_request_never_accepts_analytic_package_when_chart_shape_required(monkeypatch):
    import src.agent.sql_generation as sql_generation

    query = "gere um grafico da evolucao de uma metrica ainda nao suportada por ano"
    semantic_plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query))
    state = create_initial_messages_state(user_query=query, session_id="chart-fallback")
    state["semantic_plan"] = semantic_plan.model_dump()
    state["chart_plan"] = chart_plan.model_dump()
    state["schema_context"] = "TABLE internacoes;"
    state["selected_tables"] = ["internacoes"]

    monkeypatch.setattr(sql_generation, "_build_deterministic_chart_sql", lambda *_: None)
    monkeypatch.setattr(
        sql_generation,
        "_build_deterministic_analytic_sql",
        lambda *_: "SELECT 'temporal_condition_trend' AS analysis_type;",
    )

    new_state = generate_sql_node(state)

    assert new_state.get("structured_error") is not None
    assert new_state["structured_error"]["code"] == "chart_sql_compiler_required"
    assert "analysis_type" not in (new_state.get("generated_sql") or "")
