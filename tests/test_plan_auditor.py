from src.agent.plan_auditor import audit_pre_sql_plan, audit_result_contract
from src.semantic.planner import build_semantic_plan
from src.visualization.chart_plan import build_chart_plan
from src.visualization.intent import detect_visualization_intent

TARGET_QUERY = (
    "gere um grafico mostrando o numero de mortes de crianca por causas "
    "respiratorias nos ultimos 5 anos"
)


def test_pre_sql_auditor_accepts_resolved_target_plan():
    semantic_plan = build_semantic_plan(TARGET_QUERY)
    chart_plan = build_chart_plan(TARGET_QUERY, detect_visualization_intent(TARGET_QUERY))

    audit = audit_pre_sql_plan(
        user_query=TARGET_QUERY,
        semantic_plan=semantic_plan.model_dump(),
        chart_plan=chart_plan.model_dump(),
    )

    assert audit["passed"] is True
    assert audit["errors"] == []
    assert "child_age_policy" in audit["resolved_concepts"]
    assert "respiratory_cid" in audit["resolved_concepts"]


def test_pre_sql_auditor_blocks_unresolved_child_respiratory_plan():
    semantic_plan = build_semantic_plan(TARGET_QUERY).model_dump()
    semantic_plan["filters"] = [
        item
        for item in semantic_plan["filters"]
        if item["field"] not in {"idade", "diagnostico_principal_prefix"}
    ]
    chart_plan = build_chart_plan(TARGET_QUERY, detect_visualization_intent(TARGET_QUERY))

    audit = audit_pre_sql_plan(
        user_query=TARGET_QUERY,
        semantic_plan=semantic_plan,
        chart_plan=chart_plan.model_dump(),
    )

    assert audit["passed"] is False
    assert {error["code"] for error in audit["errors"]} == {
        "missing_child_age_policy",
        "missing_respiratory_cid_resolution",
    }


def test_result_auditor_validates_chart_columns_and_rows():
    audit = audit_result_contract(
        chart_plan={"requested": True, "required_columns": ["ano", "total_mortes"]},
        rows=[{"ano": 2019, "total_mortes": 3633}],
    )

    assert audit["passed"] is True
