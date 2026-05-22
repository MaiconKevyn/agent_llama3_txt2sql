from src.agent.intent_plan import build_intent_plan
from src.agent.tool_planner import plan_tools


def test_tool_planner_selects_chart_database_tools_for_target_query():
    intent = build_intent_plan(
        "gere um grafico mostrando o numero de mortes de crianca por causas respiratorias nos ultimos 5 anos"
    )

    tools = plan_tools(intent)
    tool_names = [tool.name for tool in tools]

    assert tool_names == [
        "inspect_schema",
        "resolve_concepts",
        "resolve_temporal_scope",
        "resolve_join_policy",
        "compile_sql",
        "execute_sql",
        "validate_result_contract",
        "build_chart",
    ]


def test_tool_planner_refuses_out_of_scope_without_sql_execution():
    intent = build_intent_plan("qual antibiotico foi usado depois da alta?")

    tools = plan_tools(intent)
    tool_names = [tool.name for tool in tools]

    assert tool_names == ["clarify_or_refuse"]
