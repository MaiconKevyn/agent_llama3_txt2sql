from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
from src.visualization.intent import detect_visualization_intent


def test_build_chart_plan_for_recent_years_death_by_sex():
    query = "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.requested is True
    assert plan.chart_type == "line"
    assert plan.metric == "total_mortes"
    assert plan.x_dimension == "ano"
    assert plan.series_dimension == "sexo"
    assert plan.y_column == "total_mortes"
    assert plan.expected_result_shape == "time_series_metric"
    assert plan.time_window.type == "last_n_available_years"
    assert plan.time_window.n == 5
    assert plan.required_columns == ["ano", "sexo", "total_mortes"]


def test_build_chart_plan_for_pie_death_causes():
    query = "pie grafico mostrando as 3 principais causas de mortes"
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.requested is True
    assert plan.chart_type == "pie"
    assert plan.metric == "total_mortes"
    assert plan.x_dimension == "causa_morte"
    assert plan.y_column == "total_mortes"
    assert plan.expected_result_shape == "category_metric"
    assert plan.required_columns == ["causa_morte", "total_mortes"]
    assert "Nao preenchido" in plan.sql_shape_guidance


def test_build_chart_plan_for_pie_deaths_by_sex_with_typo():
    query = "gere um grafico de pizza mostrando as mortes entre homens em ulheres"
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.requested is True
    assert plan.chart_type == "pie"
    assert plan.metric == "total_mortes"
    assert plan.x_dimension == "sexo"
    assert plan.series_dimension is None
    assert plan.y_column == "total_mortes"
    assert plan.expected_result_shape == "category_metric"
    assert plan.required_columns == ["sexo", "total_mortes"]
    assert any(filter_.field == "SEXO" and filter_.values == [1, 3] for filter_ in plan.filters)


def test_build_chart_plan_for_state_series_over_years():
    query = "Gere um grafico de linhas das internacoes por estado ao longo dos anos."
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.requested is True
    assert plan.chart_type == "line"
    assert plan.x_dimension == "ano"
    assert plan.series_dimension == "estado"
    assert plan.y_column == "total_internacoes"
    assert plan.expected_result_shape == "time_series_metric"
    assert plan.required_columns == ["ano", "estado", "total_internacoes"]


def test_build_chart_plan_for_monthly_plural_uses_month_axis():
    query = "Visualize em grafico as internacoes mensais."
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.x_dimension == "mes"
    assert plan.y_column == "total_internacoes"
    assert plan.required_columns == ["mes", "total_internacoes"]


def test_build_chart_plan_prioritizes_value_metric_over_admission_word():
    query = "Gere um KPI com o valor total das internacoes."
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.chart_type == "kpi"
    assert plan.metric == "receita_total"
    assert plan.y_column == "receita_total"
    assert plan.required_columns == ["receita_total"]


def test_build_chart_plan_for_scatter_uses_two_numeric_axes():
    query = "Gere um grafico de dispersao entre receita total e taxa de mortalidade por estado."
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.chart_type == "scatter"
    assert plan.x_dimension == "receita_total"
    assert plan.y_column == "taxa_mortalidade"
    assert plan.required_columns == ["receita_total", "taxa_mortalidade"]


def test_build_chart_plan_supports_english_deaths_metric():
    query = "Column chart with deaths by state."
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert plan.x_dimension == "estado"
    assert plan.y_column == "total_mortes"


def test_chart_plan_validation_rejects_current_date_window():
    query = "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        SELECT EXTRACT(YEAR FROM "DT_INTER") AS ano,
               CASE WHEN "SEXO" = 1 THEN 'homens' ELSE 'mulheres' END AS sexo,
               COUNT(*) AS total_mortes
        FROM internacoes
        WHERE "DT_INTER" >= CURRENT_DATE - INTERVAL '5 years'
        GROUP BY ano, sexo
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is False
    assert "CURRENT_DATE" in (message or "")


def test_chart_plan_validation_rejects_date_to_numeric_year_window():
    query = "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        SELECT EXTRACT(YEAR FROM "DT_INTER") AS ano,
               CASE WHEN "SEXO" = 1 THEN 'homens' ELSE 'mulheres' END AS sexo,
               COUNT(*) AS total_mortes
        FROM internacoes
        WHERE "DT_INTER" >= (SELECT MAX(EXTRACT(YEAR FROM "DT_INTER")) - 5 FROM internacoes)
        GROUP BY ano, sexo
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is False
    assert "dates directly to a numeric year" in (message or "")


def test_chart_plan_validation_rejects_interval_from_numeric_year():
    query = "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        SELECT EXTRACT(YEAR FROM "DT_INTER") AS ano,
               CASE WHEN "SEXO" = 1 THEN 'homens' ELSE 'mulheres' END AS sexo,
               COUNT(*) AS total_mortes
        FROM internacoes
        WHERE "DT_INTER" >= (
            SELECT MAX(EXTRACT(YEAR FROM "DT_INTER")) FROM internacoes
        ) - INTERVAL '5 years'
        GROUP BY ano, sexo
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is False
    assert "subtract an INTERVAL" in (message or "")


def test_chart_plan_validation_rejects_pie_sex_without_labels():
    query = "gere um grafico de pizza mostrando as mortes entre homens em mulheres"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        SELECT "SEXO", COUNT(*) AS total_mortes
        FROM internacoes
        WHERE "MORTE" = true AND "SEXO" IN (1, 3)
        GROUP BY "SEXO";
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is False
    assert "human-readable labels" in (message or "")


def test_chart_plan_validation_accepts_pie_sex_with_masculino_feminino_labels():
    query = "gere um grafico de pizza mostrando as mortes entre homens em mulheres"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        SELECT CASE WHEN "SEXO"=1 THEN 'Masculino' WHEN "SEXO"=3 THEN 'Feminino' END AS "SEXO",
               COUNT(*) AS total_mortes
        FROM internacoes
        WHERE "MORTE" = true AND "SEXO" IN (1, 3)
        GROUP BY "SEXO";
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is True
    assert message is None


def test_chart_plan_validation_accepts_pie_sex_with_homens_mulheres_labels():
    query = "gere um grafico de pizza mostrando as mortes entre homens em mulheres"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        SELECT CASE WHEN "SEXO"=1 THEN 'homens' WHEN "SEXO"=3 THEN 'mulheres' END AS "SEXO",
               COUNT(*) AS total_mortes
        FROM internacoes
        WHERE "MORTE" = true AND "SEXO" IN (1, 3)
        GROUP BY "SEXO";
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is True
    assert message is None


def test_chart_plan_shape_guidance_for_pie_sex_includes_label_hint():
    query = "gere um grafico de pizza mostrando as mortes entre homens em mulheres"
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert "Masculino" in plan.sql_shape_guidance
    assert "Feminino" in plan.sql_shape_guidance
    assert "CASE WHEN" in plan.sql_shape_guidance


def test_chart_plan_shape_guidance_for_recent_years_includes_window_anchor():
    query = "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    plan = build_chart_plan(query, detect_visualization_intent(query))

    assert "MAX(EXTRACT(YEAR FROM DT_INTER))" in plan.sql_shape_guidance
    assert "MAX_YEAR - 4" in plan.sql_shape_guidance
    assert "Masculino" in plan.sql_shape_guidance


def test_chart_plan_validation_accepts_tidy_recent_years_sql():
    query = "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        WITH max_ano AS (
            SELECT MAX(EXTRACT(YEAR FROM "DT_INTER")) AS ano_max
            FROM internacoes
        )
        SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               CASE WHEN i."SEXO" = 1 THEN 'homens' ELSE 'mulheres' END AS sexo,
               COUNT(*) AS total_mortes
        FROM internacoes i
        CROSS JOIN max_ano m
        WHERE EXTRACT(YEAR FROM i."DT_INTER") BETWEEN m.ano_max - 4 AND m.ano_max
        GROUP BY ano, sexo
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is True
    assert message is None


def test_chart_plan_validation_accepts_extract_year_scalar_subquery_window():
    query = "gere um grafico da evolucao de mortes totais nos ultimos 5 anos"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = """
        SELECT EXTRACT(YEAR FROM "DT_INTER") AS ano,
               COUNT(*) AS total_mortes
        FROM internacoes
        WHERE "MORTE" = true
          AND EXTRACT(YEAR FROM "DT_INTER") >= (
              SELECT MAX(EXTRACT(YEAR FROM "DT_INTER")) - 4 FROM internacoes
          )
        GROUP BY ano
        ORDER BY ano;
    """

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is True
    assert message is None


def test_chart_plan_validation_rejects_clinical_categories_without_unfilled_exclusion():
    query = "gere um gráfico de pizza com as 6 principais causas de morte"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = (
        'SELECT c."DESCRICAO" AS causa_morte, COUNT(*) AS total_mortes '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        'WHERE i."MORTE" = true '
        'GROUP BY c."DESCRICAO" ORDER BY total_mortes DESC LIMIT 6'
    )

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is False
    assert "Nao preenchido" in message


def test_chart_plan_validation_accepts_clinical_categories_with_unfilled_exclusion():
    query = "gere um gráfico de pizza com as 6 principais causas de morte"
    plan = build_chart_plan(query, detect_visualization_intent(query))
    sql = (
        'SELECT c."DESCRICAO" AS causa_morte, COUNT(*) AS total_mortes '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        'WHERE i."MORTE" = true '
        "AND c.\"DESCRICAO\" <> 'Nao preenchido' "
        'AND c."DESCRICAO" IS NOT NULL '
        'GROUP BY c."DESCRICAO" ORDER BY total_mortes DESC LIMIT 6'
    )

    passed, message = validate_sql_against_chart_plan(plan, sql)

    assert passed is True
    assert message is None
