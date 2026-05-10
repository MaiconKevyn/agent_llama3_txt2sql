from src.visualization.chart_plan import build_chart_plan
from src.visualization.intent import detect_visualization_intent
from src.visualization.planner import plan_chart
from src.visualization.schema import ChartPlanningInput


def test_plans_bar_for_categorical_metric_result():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere um grafico",
            columns=["municipio", "total_internacoes"],
            column_types={"municipio": "string", "total_internacoes": "number"},
            rows=[
                {"municipio": "Porto Alegre", "total_internacoes": 10},
                {"municipio": "Caxias do Sul", "total_internacoes": 8},
            ],
            row_count=2,
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "bar"
    assert spec.x == "municipio"
    assert spec.y == "total_internacoes"


def test_plans_line_for_temporal_metric_result():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere um grafico de linhas",
            columns=["ano", "total_internacoes"],
            column_types={"ano": "temporal", "total_internacoes": "number"},
            rows=[
                {"ano": 2020, "total_internacoes": 10},
                {"ano": 2021, "total_internacoes": 12},
            ],
            row_count=2,
            chart_hint="line",
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "line"
    assert spec.x == "ano"
    assert spec.y == "total_internacoes"


def test_plans_multi_series_line_for_temporal_wide_metrics():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere grafico comparando mortes de homens e mulheres nos ultimos 5 anos",
            columns=["ano", "total_mortes_homens", "total_mortes_mulheres"],
            column_types={
                "ano": "temporal",
                "total_mortes_homens": "number",
                "total_mortes_mulheres": "number",
            },
            rows=[
                {"ano": 2021, "total_mortes_homens": 22595, "total_mortes_mulheres": 19659},
                {"ano": 2022, "total_mortes_homens": 30663, "total_mortes_mulheres": 28564},
            ],
            row_count=2,
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "line"
    assert spec.x == "ano"
    assert spec.y == "valor"
    assert spec.series == "serie"
    assert spec.data[0] == {"ano": 2021, "serie": "total mortes homens", "valor": 22595}
    assert spec.data[1] == {"ano": 2021, "serie": "total mortes mulheres", "valor": 19659}


def test_multi_series_line_ignores_numeric_domain_code_columns():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere grafico comparando mortes de homens e mulheres nos ultimos 5 anos",
            columns=["ano", "SEXO", "total_mortes_homens", "total_mortes_mulheres"],
            column_types={
                "ano": "temporal",
                "SEXO": "number",
                "total_mortes_homens": "number",
                "total_mortes_mulheres": "number",
            },
            rows=[
                {
                    "ano": 2021,
                    "SEXO": 1,
                    "total_mortes_homens": 22595,
                    "total_mortes_mulheres": 0,
                },
                {
                    "ano": 2021,
                    "SEXO": 3,
                    "total_mortes_homens": 0,
                    "total_mortes_mulheres": 19659,
                },
            ],
            row_count=2,
        )
    )

    assert {row["serie"] for row in spec.data} == {
        "total mortes homens",
        "total mortes mulheres",
    }


def test_plans_kpi_for_scalar_numeric_result():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere um grafico",
            columns=["total_internacoes"],
            column_types={"total_internacoes": "number"},
            rows=[{"total_internacoes": 10}],
            row_count=1,
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "kpi"
    assert spec.y == "total_internacoes"


def test_plans_bar_for_single_row_multi_metric_comparison():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere um grafico com mortes de homens vs mulheres",
            columns=["mortes_homens", "mortes_mulheres"],
            column_types={"mortes_homens": "number", "mortes_mulheres": "number"},
            rows=[{"mortes_homens": 763021, "mortes_mulheres": 404208}],
            row_count=1,
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "bar"
    assert spec.x == "metrica"
    assert spec.y == "valor"
    assert spec.data == [
        {"metrica": "mortes homens", "valor": 763021},
        {"metrica": "mortes mulheres", "valor": 404208},
    ]


def test_single_row_multi_metric_comparison_omits_total_when_breakdown_exists():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere um grafico com mortes de homens vs mulheres",
            columns=["total_mortes", "masculino", "feminino"],
            column_types={"total_mortes": "number", "masculino": "number", "feminino": "number"},
            rows=[{"total_mortes": 763021, "masculino": 404208, "feminino": 358813}],
            row_count=1,
        )
    )

    assert spec.chart_type == "bar"
    assert spec.data == [
        {"metrica": "masculino", "valor": 404208},
        {"metrica": "feminino", "valor": 358813},
    ]


def test_chart_plan_path_handles_uppercase_column_names():
    query = "gere um grafico de pizza mostrando as mortes entre homens em mulheres"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    spec = plan_chart(
        ChartPlanningInput(
            user_query=query,
            columns=["SEXO", "TOTAL_MORTES"],
            column_types={"SEXO": "string", "TOTAL_MORTES": "number"},
            rows=[
                {"SEXO": "Masculino", "TOTAL_MORTES": 404208},
                {"SEXO": "Feminino", "TOTAL_MORTES": 358813},
            ],
            row_count=2,
            chart_hint="pie",
            chart_plan=plan,
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "pie"
    assert spec.x == "SEXO"
    assert spec.y == "TOTAL_MORTES"


def test_scatter_chart_plan_uses_numeric_axes_not_group_dimension():
    query = "Gere um scatter plot comparando idade media e total de mortes por municipio."
    plan = build_chart_plan(query, detect_visualization_intent(query))
    spec = plan_chart(
        ChartPlanningInput(
            user_query=query,
            columns=["municipio", "idade_media", "total_mortes"],
            column_types={
                "municipio": "string",
                "idade_media": "number",
                "total_mortes": "number",
            },
            rows=[
                {"municipio": "Porto Alegre", "idade_media": 68.2, "total_mortes": 52000},
                {"municipio": "Canoas", "idade_media": 66.1, "total_mortes": 18000},
            ],
            row_count=2,
            chart_hint="scatter",
            chart_plan=plan,
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "scatter"
    assert spec.x == "idade_media"
    assert spec.y == "total_mortes"


def test_chart_plan_pie_folds_excess_categories_into_outros():
    query = "Crie um grafico de pizza com internacoes por especialidade."
    plan = build_chart_plan(query, detect_visualization_intent(query))
    rows = [
        {"especialidade": f"Especialidade {index}", "total_internacoes": 100 - index}
        for index in range(10)
    ]
    spec = plan_chart(
        ChartPlanningInput(
            user_query=query,
            columns=["especialidade", "total_internacoes"],
            column_types={"especialidade": "string", "total_internacoes": "number"},
            rows=rows,
            row_count=len(rows),
            chart_hint="pie",
            chart_plan=plan,
        )
    )

    assert spec.chartable is True
    assert spec.chart_type == "pie"
    assert len(spec.data) == 8
    assert spec.data[-1]["especialidade"] == "Outros"


def test_format_domain_label_normalizes_to_canonical_sex_form():
    from src.visualization.planner import _format_domain_label

    assert _format_domain_label("sexo", 1) == "Masculino"
    assert _format_domain_label("sexo", "3") == "Feminino"
    assert _format_domain_label("SEXO", "homens") == "Masculino"
    assert _format_domain_label("sexo", "feminino") == "Feminino"


def test_returns_table_for_unsupported_shape():
    spec = plan_chart(
        ChartPlanningInput(
            user_query="gere um grafico",
            columns=["municipio"],
            column_types={"municipio": "string"},
            rows=[{"municipio": "Porto Alegre"}],
            row_count=1,
        )
    )

    assert spec.chartable is False
    assert spec.chart_type == "table"
