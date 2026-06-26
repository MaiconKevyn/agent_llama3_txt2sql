from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan
from src.utils.temporal import asks_single_total_across_years, extract_explicit_year_list
from src.visualization.chart_plan import build_chart_plan
from src.visualization.chart_plan import validate_sql_against_chart_plan
from src.visualization.intent import detect_visualization_intent


def _chart_plan(query: str):
    return build_chart_plan(query, detect_visualization_intent(query))


def test_extract_explicit_year_list_preserves_requested_years():
    assert extract_explicit_year_list("comparar 2019, 2021 e 2023") == [
        "2019",
        "2021",
        "2023",
    ]


def test_extract_explicit_year_list_ignores_continuous_year_ranges():
    assert extract_explicit_year_list("de 2021 a 2023") == []


def test_detects_single_total_across_explicit_years():
    assert asks_single_total_across_years(
        "me mostre um grafico com o total de mortes somando 2021, 2022 e 2023"
    )
    assert not asks_single_total_across_years(
        "me mostre um grafico mostrando mortes em 2021, 2022 e 2023"
    )


def test_explicit_year_list_chart_uses_annual_time_metric_contract():
    plan = _chart_plan(
        "me mostre um grafico mostrando o numero total de mortes por causas respiratorias "
        "em 2021, 2022 e 2023"
    )

    assert plan.chart_type == "line"
    assert plan.x_dimension == "ano"
    assert plan.expected_result_shape == "time_metric"
    assert plan.required_columns == ["ano", "total_mortes"]


def test_non_contiguous_explicit_year_list_is_not_broadened_to_range():
    semantic_plan = build_semantic_plan(
        "me mostre um grafico de mortes por causas respiratorias em 2019, 2021 e 2023"
    )

    year_filter = next(
        filter_ for filter_ in semantic_plan.filters if filter_.field == "ano"
    )
    assert year_filter.operator == "IN"
    assert year_filter.values == ["2019", "2021", "2023"]


def test_non_chart_year_list_remains_scalar_filter():
    semantic_plan = build_semantic_plan(
        "qual foi o numero total de mortes por causas respiratorias em 2021, 2022 e 2023"
    )

    assert semantic_plan.answer_shape.row_grain == "single_scalar"
    assert "ano" not in semantic_plan.answer_shape.required_dimensions


def test_explicit_scalar_total_chart_remains_single_metric():
    plan = _chart_plan(
        "me mostre um grafico com o total de mortes somando 2021, 2022 e 2023"
    )
    semantic_plan = build_semantic_plan(
        "me mostre um grafico com o total de mortes somando 2021, 2022 e 2023"
    )

    assert plan.chart_type == "kpi"
    assert plan.expected_result_shape == "single_metric"
    assert semantic_plan.answer_shape.row_grain == "single_scalar"
    assert "ano" not in semantic_plan.answer_shape.required_dimensions


def test_explicit_year_list_chart_semantic_plan_allows_group_by_ano():
    semantic_plan = build_semantic_plan(
        "me mostre um grafico mostrando o numero total de mortes por causas respiratorias "
        "em 2021, 2022 e 2023"
    )
    sql = """
        SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*) AS total_mortes
        FROM internacoes i
      JOIN cid c ON i."DIAG_PRINC" = c."CID"
      WHERE i."MORTE" = true
        AND c."CID" LIKE 'J%'
        AND EXTRACT(YEAR FROM i."DT_INTER") IN (2021, 2022, 2023)
        GROUP BY ano
        ORDER BY ano
    """

    assert semantic_plan.answer_shape.required_dimensions == ["ano"]
    assert semantic_plan.answer_shape.requires_group_by is True
    assert validate_sql_against_semantic_plan(semantic_plan, sql) == (True, None)


def test_temporal_analytic_package_satisfies_chart_plan_contract():
    from src.agent.analytic_sql import build_analytic_sql_package

    query = (
        "me mostre um grafico mostrando o numero total de mortes por causa respiratorias "
        "em 2021, 2022 e 2023"
    )
    sql = build_analytic_sql_package(build_semantic_plan(query))

    assert sql is not None
    assert validate_sql_against_chart_plan(_chart_plan(query), sql) == (True, None)


def test_orchestrator_attaches_line_chart_for_original_respiratory_deaths_prompt():
    from src.agent.orchestrator import LangGraphOrchestrator

    class Logger:
        def warning(self, *args, **kwargs):
            pass

    query = (
        "me mostre um grafico mostrando o numero total de mortes por causa respiratorias "
        "em 2021, 2022 e 2023"
    )
    intent = detect_visualization_intent(query)
    chart_plan = build_chart_plan(query, intent)
    semantic_plan = build_semantic_plan(query)
    orchestrator = object.__new__(LangGraphOrchestrator)
    orchestrator.logger = Logger()

    result = {
        "success": True,
        "response": "serie anual",
        "sql_query": "SELECT ano, total_mortes FROM serie ORDER BY ano",
        "results": [
            {"ano": 2021, "total_mortes": 92714},
            {"ano": 2022, "total_mortes": 111033},
            {"ano": 2023, "total_mortes": 102241},
        ],
        "row_count": 3,
        "metadata": {"semantic_plan": semantic_plan.model_dump(mode="json")},
    }

    enriched = orchestrator._attach_visualization_if_requested(
        result=result,
        user_query=query,
        visualization_intent=intent,
        chart_plan=chart_plan,
    )

    assert enriched["metadata"]["chart_plan"]["required_columns"] == ["ano", "total_mortes"]
    assert enriched["chart"]["requested"] is True
    assert enriched["chart"]["spec"]["chart_type"] == "line"
    assert enriched["chart"]["spec"]["x"] == "ano"
    assert enriched["chart"]["spec"]["y"] == "total_mortes"


def test_orchestrator_builds_line_chart_from_temporal_analytic_package():
    from src.agent.orchestrator import LangGraphOrchestrator

    class Logger:
        def warning(self, *args, **kwargs):
            pass

    query = (
        "me mostre um grafico mostrando o numero total de mortes por causa respiratorias "
        "em 2021, 2022 e 2023"
    )
    intent = detect_visualization_intent(query)
    chart_plan = build_chart_plan(query, intent)
    orchestrator = object.__new__(LangGraphOrchestrator)
    orchestrator.logger = Logger()

    result = {
        "success": True,
        "response": "serie anual",
        "sql_query": "SELECT 'temporal_condition_trend' AS analysis_type",
        "results": [
            {
                "analysis_type": "temporal_condition_trend",
                "resolved_concept": "CID J00-J99 - Doencas do aparelho respiratorio",
                "total_internacoes": 305988,
                "denominador": "internacoes por ano no mesmo escopo",
                "time_series": (
                    "2021:92714:11566528:801.57 | "
                    "2022:111033:12363889:898.04 | "
                    "2023:102241:12450724:821.17"
                ),
            }
        ],
        "row_count": 1,
        "metadata": {},
    }

    enriched = orchestrator._attach_visualization_if_requested(
        result=result,
        user_query=query,
        visualization_intent=intent,
        chart_plan=chart_plan,
    )

    chart = enriched["chart"]["spec"]
    assert chart["chart_type"] == "line"
    assert chart["x"] == "ano"
    assert chart["y"] == "total_mortes"
    assert chart["data"] == [
        {"ano": 2021, "total_mortes": 92714},
        {"ano": 2022, "total_mortes": 111033},
        {"ano": 2023, "total_mortes": 102241},
    ]


def test_orchestrator_builds_line_chart_from_temporal_analytic_tuple_result():
    from src.agent.orchestrator import LangGraphOrchestrator

    class Logger:
        def warning(self, *args, **kwargs):
            pass

    query = (
        "me mostre um grafico mostrando o numero total de mortes por causa respiratorias "
        "em 2021, 2022 e 2023"
    )
    intent = detect_visualization_intent(query)
    chart_plan = build_chart_plan(query, intent)
    orchestrator = object.__new__(LangGraphOrchestrator)
    orchestrator.logger = Logger()

    result = {
        "success": True,
        "response": "serie anual",
        "sql_query": "WITH serie AS (...) SELECT 'temporal_condition_trend' AS analysis_type",
        "results": [
            (
                "temporal_condition_trend",
                "CID J00-J99 - Doencas do aparelho respiratorio",
                "ano de internacao",
                305988,
                "internacoes por ano no mesmo escopo",
                "2021:92714:11566528:801.57 | 2022:111033:12363889:898.04 | 2023:102241:12450724:821.17",
                2021,
                92714,
                2023,
                102241,
                9527,
                10.28,
                2022,
                111033,
                None,
            )
        ],
        "row_count": 1,
        "metadata": {},
    }

    enriched = orchestrator._attach_visualization_if_requested(
        result=result,
        user_query=query,
        visualization_intent=intent,
        chart_plan=chart_plan,
    )

    chart = enriched["chart"]["spec"]
    assert chart["chart_type"] == "line"
    assert chart["x"] == "ano"
    assert chart["y"] == "total_mortes"
    assert chart["data"] == [
        {"ano": 2021, "total_mortes": 92714},
        {"ano": 2022, "total_mortes": 111033},
        {"ano": 2023, "total_mortes": 102241},
    ]
