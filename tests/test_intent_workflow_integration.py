from src.agent.intent_plan import build_intent_plan
from src.agent.state_helpers import create_initial_messages_state
from src.agent.tool_planner import plan_tools

TARGET_QUERY = (
    "gere um grafico mostrando o numero de mortes de crianca por "
    "causas respiratorias nos ultimos 5 anos"
)


def test_state_can_carry_intent_plan_and_tool_plan():
    state = create_initial_messages_state(
        user_query=TARGET_QUERY,
        session_id="intent-state",
    )
    intent_plan = build_intent_plan(state["user_query"])
    tool_plan = plan_tools(intent_plan)

    state["intent_plan"] = intent_plan.model_dump()
    state["tool_plan"] = [tool.model_dump() for tool in tool_plan]

    assert state["intent_plan"]["presentation"] == "chart"
    assert [tool["name"] for tool in state["tool_plan"]] == [
        "inspect_schema",
        "resolve_concepts",
        "resolve_temporal_scope",
        "resolve_join_policy",
        "compile_sql",
        "execute_sql",
        "validate_result_contract",
        "build_chart",
    ]


def test_intent_planning_node_populates_intent_and_tool_plan():
    from src.agent.intent_node import intent_planning_node

    state = create_initial_messages_state(
        user_query=TARGET_QUERY,
        session_id="intent-node",
    )

    new_state = intent_planning_node(state)

    assert new_state["intent_plan"]["presentation"] == "chart"
    assert new_state["intent_plan"]["temporal_scope"]["type"] == "last_n_available_years"
    assert any(tool["name"] == "build_chart" for tool in new_state["tool_plan"])
    assert any(tool["name"] == "resolve_concepts" for tool in new_state["tool_plan"])


def test_langgraph_workflow_routes_database_queries_through_intent_planning():
    from src.agent.workflow import create_langgraph_sql_workflow

    graph = create_langgraph_sql_workflow()

    assert "intent_planning" in graph.nodes
