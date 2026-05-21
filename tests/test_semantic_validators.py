from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan


def test_semantic_validator_accepts_global_window_rank_limit_for_top_n():
    plan = build_semantic_plan(
        "Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico."
    )
    sql = """
        WITH municipio_taxa AS (
            SELECT mu."NO_MUNICIPIO" AS municipio,
                   COUNT(*) AS total_internacoes,
                   SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_mortes,
                   SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_mortalidade
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
            GROUP BY mu."NO_MUNICIPIO"
        ),
        ranked AS (
            SELECT municipio,
                   total_internacoes,
                   total_mortes,
                   taxa_mortalidade,
                   ROW_NUMBER() OVER (ORDER BY taxa_mortalidade DESC) AS rn
            FROM municipio_taxa
        )
        SELECT municipio, total_internacoes, total_mortes, taxa_mortalidade
        FROM ranked
        WHERE rn <= 10;
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_validator_rejects_global_top_n_without_limit():
    plan = build_semantic_plan(
        "Quais sao os municipios com maior taxa de mortalidade? Mostre em grafico."
    )
    sql = """
        SELECT mu."NO_MUNICIPIO" AS municipio,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_mortalidade
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        GROUP BY mu."NO_MUNICIPIO"
        ORDER BY taxa_mortalidade DESC;
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "top_n=10" in (message or "")


def test_socioeconomic_multi_metric_macro_uses_wide_columns_and_municipios_join():
    from src.agent.execution import _build_socioeconomic_multi_metric_sql

    plan = build_semantic_plan("Compare PIB per capita e mortalidade infantil em scatter.")

    sql = _build_socioeconomic_multi_metric_sql(plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")

    assert plan.intent == "association"
    assert plan.answer_shape.required_dimensions == ["municipio"]
    assert sql is not None
    assert 's."VL_PIB_PERCAPITA"' in sql
    assert 's."VL_MORT_INFANTIL"' in sql
    assert "JOIN municipios" in sql
    assert valid is True
    assert message is None


def test_semantic_validator_accepts_socioeconomic_year_dimension_and_latest_year_anchor():
    plan = build_semantic_plan("Populacao por estado no ultimo ano disponivel em grafico.")
    sql = """
        SELECT mu."SG_UF" AS estado, SUM(s."QT_POPULACAO") AS populacao
        FROM socioeconomico s
        JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"
        WHERE s."QT_POPULACAO" IS NOT NULL
          AND s."NU_ANO" >= (SELECT MAX("NU_ANO") FROM socioeconomico)
        GROUP BY mu."SG_UF"
        ORDER BY populacao DESC;
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_validator_accepts_cid_chapter_dimension_from_lookup_label():
    plan = build_semantic_plan("Mostre internacoes por categoria CID em barras.")
    sql = """
        SELECT c."DS_CAPITULO" AS cid_capitulo, COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE c."DS_CAPITULO" IS NOT NULL
        GROUP BY c."DS_CAPITULO"
        ORDER BY total_internacoes DESC
        LIMIT 10;
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_diagnosis_grouping_query_does_not_become_named_diagnosis_filter():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = (
        "Mostre taxa de mortalidade por diagnostico principal com minimo de 1000 "
        "internacoes em grafico de barras."
    )
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert not any(
        semantic_filter.field == "diagnostico_principal_descricao"
        for semantic_filter in plan.filters
    )
    assert sql is not None
    assert 'c."DESCRICAO" AS diagnostico' in sql
    assert "Nao preenchido" in sql
    assert "HAVING COUNT(*) > 1000" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_mortality_rate_ranking_honors_pelo_menos_support_threshold():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = (
        "Compare os municipios com maior taxa de mortalidade, considerando pelo menos "
        "1000 internacoes, em grafico de barras."
    )
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert any(
        semantic_filter.field == "minimum_group_count"
        and semantic_filter.values == ["1000"]
        for semantic_filter in plan.filters
    )
    assert sql is not None
    assert "HAVING COUNT(*) > 1000" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_kpi_permanence_average_generates_single_metric_chart_sql():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "KPI com permanencia media geral."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert [metric.name for metric in plan.metrics] == ["media_dias_permanencia"]
    assert chart_plan.chart_type == "kpi"
    assert sql == (
        'SELECT ROUND(AVG(i."DIAS_PERM"), 2) AS media_dias_permanencia '
        'FROM internacoes i WHERE i."DIAS_PERM" IS NOT NULL;'
    )
    assert "total_internacoes" not in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_deterministic_chart_macro_uses_population_denominator_for_per_1000_indicators():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Leitos SUS por 1000 habitantes por municipio em barras."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert sql is not None
    assert 'SUM(s."QT_LEITOS_SUS")' in sql
    assert 'SUM(s."QT_POPULACAO")' in sql
    assert "1000.0" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_deterministic_chart_macro_outputs_both_metrics_for_socioeconomic_scatter():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Scatter entre medicos por 1000 habitantes e mortalidade infantil."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert chart_plan.x_dimension == "medicos_1000"
    assert chart_plan.y_column == "mortalidade_infantil"
    assert sql is not None
    assert "medicos_1000" in sql
    assert "mortalidade_infantil" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_deterministic_chart_macro_outputs_mixed_mortality_and_socioeconomic_state_scatter():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Compare taxa de mortalidade hospitalar e leitos SUS por UF em scatter."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert chart_plan.x_dimension == "taxa_mortalidade"
    assert chart_plan.y_column == "leitos_sus"
    assert sql is not None
    assert "taxa_mortalidade" in sql
    assert "leitos_sus" in sql
    assert 'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END)' in sql
    assert 's."QT_LEITOS_SUS"' in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_deterministic_chart_macro_outputs_two_internacoes_metrics_for_scatter():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Scatter entre permanencia media e custo medio por municipio."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert chart_plan.x_dimension == "media_dias_permanencia"
    assert chart_plan.y_column == "custo_medio"
    assert sql is not None
    assert 'AVG(i."DIAS_PERM")' in sql
    assert 'AVG(i."VAL_TOT")' in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_auto_chart_city_and_deaths_keeps_municipality_dimension():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Grafico de cidade e mortes."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert plan.answer_shape.required_dimensions == ["municipio"]
    assert sql is not None
    assert 'mu."NO_MUNICIPIO" AS municipio' in sql
    assert 'i."MORTE" = true' in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_ambiguous_mortality_chart_defaults_to_temporal_rate():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Quero um grafico com mortalidade."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert plan.answer_shape.required_dimensions == ["ano"]
    assert chart_plan.chart_type == "line"
    assert chart_plan.y_column == "taxa_mortalidade"
    assert sql is not None
    assert 'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END)' in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_profile_cost_chart_defaults_to_sex_profile_with_labels():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Mostre custos por perfil em grafico."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert plan.answer_shape.required_dimensions == ["sexo"]
    assert chart_plan.x_dimension == "sexo"
    assert sql is not None
    assert "Masculino" in sql
    assert "Feminino" in sql
    assert 'SUM(i."VAL_TOT")' in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_deterministic_chart_macro_limits_global_top_n_state_rankings():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Quais estados tiveram maior taxa de mortalidade? Gere um grafico."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert plan.answer_shape.top_n_scope == "global"
    assert plan.answer_shape.top_n == 10
    assert sql is not None
    assert 'mu."SG_UF" AS estado' in sql
    assert "LIMIT 10" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_deterministic_chart_macro_outputs_procedure_dimension_without_repair():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Quais procedimentos tiveram maior taxa de mortalidade? Gere um grafico."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert plan.answer_shape.required_dimensions == ["procedimento"]
    assert sql is not None
    assert 'JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"' in sql
    assert 'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"' in sql
    assert 'p."NOME_PROC" AS procedimento' in sql
    assert "LIMIT 10" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_procedure_time_series_uses_procedure_series_and_bounded_cte():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Procedimentos mais frequentes por ano em linha."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert chart_plan.x_dimension == "ano"
    assert chart_plan.series_dimension == "procedimento"
    assert sql is not None
    assert "WITH top_procedimentos AS" in sql
    assert 'JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"' in sql
    assert 'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"' in sql
    assert "LIMIT 10" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_procedure_chart_applies_obstetric_filter_generically():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Grafico de procedimentos mais comuns em obstetricia."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert any(semantic_filter.field == "obstetrico" for semantic_filter in plan.filters)
    assert sql is not None
    assert 'i."ESPEC" = 2' in sql
    assert 'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"' in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_bottom_mortality_rate_rankings_order_ascending():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Gere um grafico dos estados com menor taxa de mortalidade hospitalar."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert "lowest_rank_requested" in plan.constraints
    assert sql is not None
    assert "ORDER BY taxa_mortalidade ASC" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_deterministic_chart_macro_outputs_demographic_labels_without_repair():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    for query, expected in [
        ("Mostre taxa de mortalidade por raca/cor em barras.", 'r."DESCRICAO" AS raca_cor'),
        ("Grafico de mortes por faixa etaria.", "AS faixa_etaria"),
    ]:
        plan = build_semantic_plan(query)
        chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

        sql = _build_deterministic_chart_sql(plan, chart_plan)
        valid, message = validate_sql_against_semantic_plan(plan, sql or "")
        chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

        assert sql is not None
        assert expected in sql
        assert valid is True
        assert message is None
        assert chart_valid is True
        assert chart_message is None


def test_deterministic_chart_macro_preserves_permanence_alias_over_generic_average():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Evolucao da permanencia media por ano em grafico de linha."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert chart_plan.y_column == "media_dias_permanencia"
    assert sql is not None
    assert 'AVG(i."DIAS_PERM")' in sql
    assert "AS media_dias_permanencia" in sql
    assert "AS custo_medio" not in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_vague_difference_chart_by_sex_defaults_to_count_without_repair():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Mostre graficamente as principais diferencas por sexo."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert chart_plan.y_column == "total_internacoes"
    assert sql is not None
    assert "Masculino" in sql
    assert "Feminino" in sql
    assert "COUNT(*) AS total_internacoes" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None


def test_death_cause_chart_outputs_visual_alias_and_excludes_unfilled_without_repair():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    query = "Pizza das 5 principais causas de morte."
    plan = build_semantic_plan(query)
    chart_plan = build_chart_plan(query, detect_visualization_intent(query), semantic_plan=plan)

    sql = _build_deterministic_chart_sql(plan, chart_plan)
    valid, message = validate_sql_against_semantic_plan(plan, sql or "")
    chart_valid, chart_message = validate_sql_against_chart_plan(chart_plan, sql or "")

    assert chart_plan.x_dimension == "causa_morte"
    assert sql is not None
    assert 'c."DESCRICAO" AS causa_morte' in sql
    assert 'i."MORTE" = true' in sql
    assert "Nao preenchido" in sql
    assert "LIMIT 5" in sql
    assert valid is True
    assert message is None
    assert chart_valid is True
    assert chart_message is None
