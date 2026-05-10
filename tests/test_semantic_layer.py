from src.agent.plan_gate import plan_gate_node
from src.agent.state_helpers import create_initial_messages_state
from src.agent.validation import check_semantic_rules
from src.application.config.simple_config import OrchestratorConfig
from src.application.prompts.table_selection.catalog import resolve_table_selection_strategy
from src.semantic.catalog import (
    catalog_summary,
    load_semantic_catalog,
    render_catalog_context_for_plan,
    render_catalog_prompt_context,
)
from src.semantic.data_profile import (
    ColumnProfileSpec,
    build_column_profile_queries,
    build_default_profile_query_sets,
)
from src.semantic.equivalence import same_semantic_pattern, semantic_sql_signature
from src.semantic.error_taxonomy import (
    SemanticErrorCategory,
    build_semantic_error_record,
    classify_semantic_error,
)
from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan


def test_semantic_plan_detects_generic_top_n_per_group():
    plan = build_semantic_plan("Quais são os 5 hospitais com maior custo médio de UTI por estado?")

    assert plan.intent == "ranking"
    assert plan.answer_shape.top_n == 5
    assert plan.answer_shape.top_n_scope == "per_group"
    assert "top_n_per_group_requires_window_partition" in plan.constraints
    assert "estado_hospital" in plan.answer_shape.required_dimensions
    assert "hospital" in plan.answer_shape.required_dimensions


def test_semantic_plan_treats_city_mention_as_filter_for_top_procedures_in_state():
    plan = build_semantic_plan("Quais são os 10 procedimentos mais comuns nas cidades do RS?")

    assert plan.intent == "ranking"
    assert plan.answer_shape.row_grain == "top_n_global"
    assert plan.answer_shape.top_n == 10
    assert plan.answer_shape.required_dimensions == ["procedimento"]
    assert "geographic_filter_dimension_not_output" in plan.constraints
    assert "join_path_hospital_location_required" in plan.constraints


def test_semantic_validator_rejects_unrequested_city_grouping_for_top_procedures():
    plan = build_semantic_plan("Quais são os 10 procedimentos mais comuns nas cidades do RS?")
    sql = """
        SELECT mu."nome", p."NOME_PROC", COUNT(*) AS total
        FROM internacoes i
        JOIN hospital h ON i."CNES" = h."CNES"
        JOIN municipios mu ON h."MUNIC_MOV" = mu."codigo_6d"
        JOIN atendimentos a ON i."N_AIH" = a."N_AIH"
        JOIN procedimentos p ON a."PROC_REA" = p."PROC_REA"
        WHERE mu."estado" = 'RS'
        GROUP BY mu."nome", p."NOME_PROC"
        ORDER BY total DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "filter/location scope" in (message or "")


def test_semantic_validator_accepts_state_scoped_top_procedures_without_city_grouping():
    plan = build_semantic_plan("Quais são os 10 procedimentos mais comuns nas cidades do RS?")
    sql = """
        SELECT p."NOME_PROC", COUNT(*) AS total
        FROM internacoes i
        JOIN hospital h ON i."CNES" = h."CNES"
        JOIN municipios mu ON h."MUNIC_MOV" = mu."codigo_6d"
        JOIN atendimentos a ON i."N_AIH" = a."N_AIH"
        JOIN procedimentos p ON a."PROC_REA" = p."PROC_REA"
        WHERE mu."estado" = 'RS'
        GROUP BY p."NOME_PROC"
        ORDER BY total DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_treats_respiratory_cid_as_filter_for_quarter_percentage():
    plan = build_semantic_plan(
        "Qual o total e o percentual de internações por doenças respiratórias (CID J%) em cada trimestre do ano no estado do RS?"
    )

    assert "diagnostico" not in plan.answer_shape.required_dimensions
    assert "trimestre" in plan.answer_shape.required_dimensions
    assert "diagnosis_filter_dimension_not_output" in plan.constraints
    assert "percentage_denominator_matches_filtered_category" in plan.constraints


def test_semantic_plan_does_not_treat_utilizados_as_uti_filter():
    plan = build_semantic_plan(
        "Qual a distribuição dos métodos contraceptivos utilizados por pacientes em internações obstétricas, incluindo os casos sem informação?"
    )

    assert not any(filter_.field == "uti" for filter_ in plan.filters)
    assert any(filter_.field == "obstetrico" for filter_ in plan.filters)
    assert "contraceptivo" in plan.answer_shape.required_dimensions
    assert "contraceptive_obstetric_filter_required" in plan.constraints
    assert "include_unknown_bucket_with_left_join_or_coalesce" in plan.null_policy


def test_semantic_validator_rejects_contraceptive_inner_join_unknown_bucket_loss():
    plan = build_semantic_plan(
        "Qual a distribuição dos métodos contraceptivos utilizados por pacientes em internações obstétricas, incluindo os casos sem informação?"
    )
    sql = """
        SELECT c."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN contraceptivos c ON i."CONTRACEP1" = c."CONTRACEPTIVO"
        WHERE i."ESPEC" = 2
        GROUP BY c."DESCRICAO"
        ORDER BY total DESC
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "unknown" in (message or "").lower()


def test_semantic_validator_accepts_contraceptive_left_join_unknown_bucket():
    plan = build_semantic_plan(
        "Qual a distribuição dos métodos contraceptivos utilizados por pacientes em internações obstétricas, incluindo os casos sem informação?"
    )
    sql = """
        SELECT COALESCE(c."DESCRICAO", 'SEM INFORMACAO') AS metodo_contraceptivo,
               COUNT(*) AS total_internacoes
        FROM internacoes i
        LEFT JOIN contraceptivos c ON i."CONTRACEP1" = c."CONTRACEPTIVO"
        WHERE i."ESPEC" = 2
        GROUP BY COALESCE(c."DESCRICAO", 'SEM INFORMACAO')
        ORDER BY total_internacoes DESC
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_goalv2_contraceptive_distribution_does_not_require_arbitrary_limit():
    plan = build_semantic_plan(
        "Qual a distribuição dos métodos contraceptivos utilizados por pacientes em internações obstétricas, incluindo os casos sem informação?"
    )
    sql = """
        SELECT COALESCE(c."DESCRICAO", 'SEM INFORMACAO') AS metodo_contraceptivo,
               COUNT(*) AS total_internacoes
        FROM internacoes i
        LEFT JOIN contraceptivos c ON i."CONTRACEP1" = c."CONTRACEPTIVO"
        WHERE i."ESPEC" = 2
        GROUP BY COALESCE(c."DESCRICAO", 'SEM INFORMACAO')
        ORDER BY total_internacoes DESC
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None
    assert plan.answer_shape.top_n is None


def test_semantic_plan_requires_sex_labels_for_grouped_sex_metric():
    plan = build_semantic_plan(
        "Qual o custo médio de UTI por especialidade médica e sexo do paciente, considerando apenas internações com custo de UTI registrado?"
    )

    assert "sexo" in plan.answer_shape.required_dimensions
    assert "sex_label_output_required" in plan.constraints
    assert any(filter_.field == "uti" for filter_ in plan.filters)


def test_semantic_validator_rejects_raw_numeric_sex_output():
    plan = build_semantic_plan(
        "Qual o custo médio de UTI por especialidade médica e sexo do paciente, considerando apenas internações com custo de UTI registrado?"
    )
    sql = """
        SELECT e."DESCRICAO" AS especialidade,
               i."SEXO",
               ROUND(AVG(i."VAL_UTI"), 2) AS custo_medio_uti
        FROM internacoes i
        JOIN especialidade e ON i."ESPEC" = e."ESPEC"
        WHERE i."VAL_UTI" > 0
        GROUP BY e."DESCRICAO", i."SEXO"
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "human-readable labels" in (message or "")


def test_semantic_validator_accepts_case_sex_labels_for_uti_cost():
    plan = build_semantic_plan(
        "Qual o custo médio de UTI por especialidade médica e sexo do paciente, considerando apenas internações com custo de UTI registrado?"
    )
    sql = """
        SELECT e."DESCRICAO" AS especialidade,
               CASE WHEN i."SEXO" = 1 THEN 'Masculino' WHEN i."SEXO" = 3 THEN 'Feminino' END AS sexo,
               ROUND(AVG(i."VAL_UTI"), 2) AS custo_medio_uti
        FROM internacoes i
        JOIN especialidade e ON i."ESPEC" = e."ESPEC"
        WHERE i."VAL_UTI" > 0 AND i."SEXO" IN (1, 3)
        GROUP BY e."DESCRICAO", i."SEXO"
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_detects_death_cause_cid_antijoin():
    plan = build_semantic_plan(
        "Quais códigos CID aparecem como causa de morte em óbitos registrados mas nunca foram registrados como diagnóstico principal de internação?"
    )

    assert "diagnostico" in plan.answer_shape.required_dimensions
    assert "absence_condition_requires_antijoin_or_aggregate_zero" in plan.constraints
    assert "death_cause_cid_requires_cid_morte_antijoin" in plan.constraints


def test_semantic_plan_does_not_treat_temporal_grouping_as_death_cause_description():
    plan = build_semantic_plan("Gere um grafico temporal com o numero de mortes por ano")

    assert "death_cause_description_requires_cid_morte" not in plan.constraints
    assert not any(filter_.field == "cid_morte_descricao" for filter_ in plan.filters)
    assert any(filter_.field == "desfecho" and filter_.values == ["MORTE = true"] for filter_ in plan.filters)
    assert "ano" in plan.answer_shape.required_dimensions


def test_semantic_validator_rejects_temporal_count_rank_deduplication():
    plan = build_semantic_plan("Gere um grafico temporal com o numero de mortes por ano")
    sql = """
        SELECT ano, COUNT(*) AS total
        FROM (
            SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano,
                   ROW_NUMBER() OVER (
                       PARTITION BY EXTRACT(YEAR FROM i."DT_INTER")
                       ORDER BY i."DT_INTER"
                   ) AS rn
            FROM internacoes i
            WHERE i."MORTE" = true
        ) sub
        WHERE rn = 1
        GROUP BY ano
        ORDER BY ano
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "complete temporal aggregation" in (message or "")


def test_semantic_plan_detects_recent_years_as_available_data_window():
    plan = build_semantic_plan(
        "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    )

    assert plan.intent == "trend"
    assert plan.answer_shape.row_grain == "time_series"
    assert "ano" in plan.answer_shape.required_dimensions
    assert any(metric.name == "total_mortes" for metric in plan.metrics)
    assert any(
        filter_.field == "recent_years_available" and filter_.values == ["5"]
        for filter_ in plan.filters
    )
    assert "relative_recent_years_use_available_data_max_year" in plan.constraints


def test_semantic_validator_rejects_current_date_for_recent_available_years():
    plan = build_semantic_plan(
        "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    )
    sql = """
        SELECT EXTRACT(YEAR FROM "DT_INTER") AS ano,
               SUM(CASE WHEN "SEXO" = 1 THEN 1 ELSE 0 END) AS total_mortes_homens,
               SUM(CASE WHEN "SEXO" = 3 THEN 1 ELSE 0 END) AS total_mortes_mulheres
        FROM internacoes
        WHERE "MORTE" = true
          AND "SEXO" IN (1, 3)
          AND "DT_INTER" >= CURRENT_DATE - INTERVAL '5 years'
        GROUP BY ano
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "latest year available" in (message or "")


def test_semantic_validator_accepts_sex_comparison_pivot_columns():
    plan = build_semantic_plan(
        "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    )
    sql = """
        WITH max_ano AS (
            SELECT MAX(EXTRACT(YEAR FROM "DT_INTER")) AS ano_max
            FROM internacoes
            WHERE "DT_INTER" IS NOT NULL
        )
        SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               SUM(CASE WHEN i."SEXO" = 1 THEN 1 ELSE 0 END) AS total_mortes_homens,
               SUM(CASE WHEN i."SEXO" = 3 THEN 1 ELSE 0 END) AS total_mortes_mulheres
        FROM internacoes i
        CROSS JOIN max_ano m
        WHERE i."MORTE" = true
          AND i."SEXO" IN (1, 3)
          AND i."DT_INTER" IS NOT NULL
          AND EXTRACT(YEAR FROM i."DT_INTER") BETWEEN m.ano_max - 4 AND m.ano_max
        GROUP BY EXTRACT(YEAR FROM i."DT_INTER")
        ORDER BY ano
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_detects_static_death_distribution_by_sex_with_typo():
    plan = build_semantic_plan(
        "gere um grafico de pizza mostrando as mortes entre homens em ulheres"
    )

    assert plan.intent == "distribution"
    assert plan.answer_shape.row_grain == "one_row_per_group"
    assert plan.answer_shape.required_dimensions == ["sexo"]
    assert any(
        filter_.field == "sexo" and filter_.operator == "IN" and filter_.values == ["1", "3"]
        for filter_ in plan.filters
    )
    assert any(filter_.field == "desfecho" and filter_.values == ["MORTE = true"] for filter_ in plan.filters)


def test_semantic_plan_detects_moving_average_contract_without_state_false_positive():
    plan = build_semantic_plan(
        "Qual a média móvel de 3 anos de internações no estado do RS por ano (2008-2023)?"
    )

    assert plan.intent == "trend"
    assert plan.answer_shape.row_grain == "time_series"
    assert "ano" in plan.answer_shape.required_dimensions
    assert any(filter_.field == "estado" and filter_.values == ["RS"] for filter_ in plan.filters)
    assert "moving_average_requires_preaggregated_time_series" in plan.constraints


def test_semantic_validator_rejects_moving_average_over_raw_average():
    plan = build_semantic_plan(
        "Qual a média móvel de 3 anos de internações no estado do RS por ano (2008-2023)?"
    )
    sql = """
        SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               AVG(i."VAL_TOT") OVER (
                   ORDER BY EXTRACT(YEAR FROM i."DT_INTER") ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
               ) AS media_movel
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        WHERE mu."estado" = 'RS'
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "GROUP BY" in (message or "") or "annual admission counts" in (message or "")


def test_semantic_validator_accepts_moving_average_over_annual_counts():
    plan = build_semantic_plan(
        "Qual a média móvel de 3 anos de internações no estado do RS por ano (2008-2023)?"
    )
    sql = """
        WITH anuais AS (
            SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*) AS total_internacoes
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
            WHERE mu."estado" = 'RS'
              AND EXTRACT(YEAR FROM i."DT_INTER") BETWEEN 2008 AND 2023
            GROUP BY EXTRACT(YEAR FROM i."DT_INTER")
        )
        SELECT ano,
               total_internacoes,
               ROUND(AVG(total_internacoes) OVER (
                   ORDER BY ano ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
               ), 0) AS media_movel_3anos
        FROM anuais
        ORDER BY ano
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_detects_quartile_distribution_without_se_state_filter():
    plan = build_semantic_plan(
        "Como se distribuem os hospitais em quartis de volume de internações? Mostre o número de hospitais e o intervalo de internações por quartil."
    )

    assert not any(filter_.field == "estado" for filter_ in plan.filters)
    assert "quartil" in plan.answer_shape.required_dimensions
    assert "quartile_distribution_requires_ntile_interval" in plan.constraints


def test_semantic_plan_detects_idhm_and_hospital_mortality_mixed_sources():
    plan = build_semantic_plan(
        "Compare o IDHM médio dos municípios do RS com taxa de mortalidade hospitalar acima e abaixo da média estadual (mínimo de 500 internações)."
    )

    metric_names = {metric.name for metric in plan.metrics}
    assert {"idhm", "taxa_mortalidade"} <= metric_names
    assert any(filter_.field == "metrica" and "idhm" in filter_.values for filter_ in plan.filters)
    assert "socioeconomico_metric_filter_required" in plan.constraints
    assert "rate_denominator_must_preserve_full_scope" in plan.constraints
    assert "idhm_mortality_cohort_requires_state_rate_split" in plan.constraints


def test_semantic_plan_detects_socioeconomico_multi_metric_pivot():
    plan = build_semantic_plan(
        "Quais são os 10 municípios do Maranhão com Bolsa Família acima da média estadual e mortalidade infantil abaixo da média estadual?"
    )

    metric_names = {metric.name for metric in plan.metrics}
    assert {"bolsa_familia_total", "mortalidade_infantil_1ano"} <= metric_names
    metrica_filter = next(filter_ for filter_ in plan.filters if filter_.field == "metrica")
    assert set(metrica_filter.values) == {"bolsa_familia_total", "mortalidade_infantil_1ano"}
    assert "socioeconomico_multi_metric_requires_conditional_pivot" in plan.constraints


def test_semantic_validator_rejects_idhm_mortality_cohort_using_municipality_rate_average():
    plan = build_semantic_plan(
        "Compare o IDHM médio dos municípios do RS com taxa de mortalidade hospitalar acima e abaixo da média estadual (mínimo de 500 internações)."
    )
    sql = """
        WITH taxa_mortalidade AS (
            SELECT mu.nome,
                   SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
            WHERE mu.estado = 'RS'
            GROUP BY mu.nome
            HAVING COUNT(*) > 500
        ),
        idhm_municipios AS (
            SELECT s."codigo_6d", AVG(s."valor") AS idhm
            FROM socioeconomico s
            JOIN municipios mu ON s."codigo_6d" = mu."codigo_6d"
            WHERE s.metrica = 'idhm' AND mu.estado = 'RS'
            GROUP BY s."codigo_6d"
        )
        SELECT CASE WHEN tm.taxa > (SELECT AVG(taxa) FROM taxa_mortalidade)
                    THEN 'Acima da média' ELSE 'Abaixo da média' END AS grupo,
               AVG(i.idhm) AS idhm_medio
        FROM taxa_mortalidade tm
        JOIN idhm_municipios i ON tm.nome = (
            SELECT mu.nome FROM municipios mu WHERE mu.codigo_6d = i.codigo_6d
        )
        GROUP BY grupo
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "state-level mortality rate" in (message or "")


def test_semantic_validator_accepts_idhm_mortality_cohort_macro_shape():
    plan = build_semantic_plan(
        "Compare o IDHM médio dos municípios do RS com taxa de mortalidade hospitalar acima e abaixo da média estadual (mínimo de 500 internações)."
    )
    sql = """
        WITH media_estado AS (
            SELECT SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_media
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
            WHERE mu."estado" = 'RS'
        ),
        mortalidade_mun AS (
            SELECT mu."codigo_6d", mu."nome",
                   SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_mortalidade
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
            WHERE mu."estado" = 'RS'
            GROUP BY mu."codigo_6d", mu."nome"
            HAVING COUNT(*) > 500
        )
        SELECT CASE WHEN mm.taxa_mortalidade > me.taxa_media
                    THEN 'Acima da media' ELSE 'Abaixo da media' END AS grupo,
               COUNT(*) AS qtd_municipios,
               ROUND(AVG(s."valor"), 4) AS idhm_medio
        FROM mortalidade_mun mm
        CROSS JOIN media_estado me
        JOIN socioeconomico s ON mm."codigo_6d" = s."codigo_6d"
        WHERE s."metrica" = 'idhm'
        GROUP BY CASE WHEN mm.taxa_mortalidade > me.taxa_media
                      THEN 'Acima da media' ELSE 'Abaixo da media' END
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_validator_rejects_multi_metric_socioeconomico_without_pivot():
    plan = build_semantic_plan(
        "Quais são os 10 municípios do Maranhão com Bolsa Família acima da média estadual e mortalidade infantil abaixo da média estadual?"
    )
    sql = """
        SELECT mu."nome", SUM(s."valor") AS valor
        FROM socioeconomico s
        JOIN municipios mu ON s."codigo_6d" = mu."codigo_6d"
        WHERE mu."estado" = 'MA'
          AND s."metrica" IN ('bolsa_familia_total', 'mortalidade_infantil_1ano')
        GROUP BY mu."nome"
        ORDER BY valor DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "conditional pivot" in (message or "")


def test_semantic_validator_accepts_multi_metric_socioeconomico_pivot():
    plan = build_semantic_plan(
        "Quais são os 10 municípios do Maranhão com Bolsa Família acima da média estadual e mortalidade infantil abaixo da média estadual?"
    )
    sql = """
        WITH media_estado AS (
            SELECT AVG(CASE WHEN s."metrica" = 'bolsa_familia_total' THEN s."valor" END) AS avg_bf,
                   AVG(CASE WHEN s."metrica" = 'mortalidade_infantil_1ano' THEN s."valor" END) AS avg_mi
            FROM socioeconomico s
            JOIN municipios mu ON s."codigo_6d" = mu."codigo_6d"
            WHERE mu."estado" = 'MA'
        ),
        por_municipio AS (
            SELECT mu."nome",
                   MAX(CASE WHEN s."metrica" = 'bolsa_familia_total' THEN s."valor" END) AS bolsa_familia,
                   MAX(CASE WHEN s."metrica" = 'mortalidade_infantil_1ano' THEN s."valor" END) AS mortalidade_infantil
            FROM socioeconomico s
            JOIN municipios mu ON s."codigo_6d" = mu."codigo_6d"
            WHERE mu."estado" = 'MA'
            GROUP BY mu."nome"
        )
        SELECT pm."nome", pm.bolsa_familia, pm.mortalidade_infantil
        FROM por_municipio pm CROSS JOIN media_estado me
        WHERE pm.bolsa_familia > me.avg_bf
          AND pm.mortalidade_infantil < me.avg_mi
        ORDER BY pm.bolsa_familia DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_validator_rejects_quartile_without_interval_columns():
    plan = build_semantic_plan(
        "Como se distribuem os hospitais em quartis de volume de internações? Mostre o número de hospitais e o intervalo de internações por quartil."
    )
    sql = """
        WITH volumes AS (
            SELECT "CNES", COUNT(*) AS total_internacoes
            FROM internacoes
            GROUP BY "CNES"
        )
        SELECT NTILE(4) OVER (ORDER BY total_internacoes) AS quartil, COUNT(*)
        FROM volumes
        GROUP BY quartil
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "MIN(total)" in (message or "")


def test_semantic_validator_accepts_quartile_distribution_with_interval():
    plan = build_semantic_plan(
        "Como se distribuem os hospitais em quartis de volume de internações? Mostre o número de hospitais e o intervalo de internações por quartil."
    )
    sql = """
        WITH volume_por_hospital AS (
            SELECT "CNES", COUNT(*) AS total_internacoes
            FROM internacoes
            GROUP BY "CNES"
        ),
        quartis AS (
            SELECT "CNES",
                   total_internacoes,
                   NTILE(4) OVER (ORDER BY total_internacoes) AS ntile_grupo
            FROM volume_por_hospital
        )
        SELECT ntile_grupo,
               COUNT(*) AS total_hospitais,
               MIN(total_internacoes) AS min_internacoes,
               MAX(total_internacoes) AS max_internacoes
        FROM quartis
        GROUP BY ntile_grupo
        ORDER BY ntile_grupo
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_validator_rejects_death_cause_antijoin_on_diag_princ_only():
    plan = build_semantic_plan(
        "Quais códigos CID aparecem como causa de morte em óbitos registrados mas nunca foram registrados como diagnóstico principal de internação?"
    )
    sql = """
        SELECT c."CID", c."CD_DESCRICAO"
        FROM cid c
        WHERE NOT EXISTS (
            SELECT 1 FROM internacoes d WHERE d."DIAG_PRINC" = c."CID"
        )
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "death filter" in (message or "") or "CID_MORTE" in (message or "")


def test_semantic_validator_accepts_death_cause_cid_antijoin():
    plan = build_semantic_plan(
        "Quais códigos CID aparecem como causa de morte em óbitos registrados mas nunca foram registrados como diagnóstico principal de internação?"
    )
    sql = """
        SELECT c."CID", c."CD_DESCRICAO", COUNT(*) AS total_como_morte
        FROM internacoes i
        JOIN cid c ON i."CID_MORTE" = c."CID"
        WHERE i."MORTE" = true
          AND i."CID_MORTE" IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM internacoes d WHERE d."DIAG_PRINC" = c."CID"
          )
        GROUP BY c."CID", c."CD_DESCRICAO"
        ORDER BY total_como_morte DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_validator_rejects_unbounded_death_cause_antijoin_list():
    plan = build_semantic_plan(
        "Quais códigos CID aparecem como causa de morte em óbitos registrados mas nunca foram registrados como diagnóstico principal de internação?"
    )
    sql = """
        SELECT c."CID", c."CD_DESCRICAO"
        FROM cid c
        WHERE EXISTS (
            SELECT 1 FROM internacoes i WHERE i."CID_MORTE" = c."CID" AND i."MORTE" = true
        )
          AND NOT EXISTS (
              SELECT 1 FROM internacoes d WHERE d."DIAG_PRINC" = c."CID"
          )
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "support counts per CID" in (message or "")


def test_semantic_validator_rejects_diagnosis_grouping_for_category_percentage():
    plan = build_semantic_plan(
        "Qual o total e o percentual de internações por doenças respiratórias (CID J%) em cada trimestre do ano no estado do RS?"
    )
    sql = """
        WITH total_internacoes AS (
            SELECT COUNT(*) AS total
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
            WHERE mu."estado" = 'RS'
        ),
        respiratorias AS (
            SELECT EXTRACT(QUARTER FROM i."DT_INTER") AS trimestre,
                   i."DIAG_PRINC",
                   COUNT(*) AS total_resp
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
            WHERE mu."estado" = 'RS' AND i."DIAG_PRINC" LIKE 'J%'
            GROUP BY trimestre, i."DIAG_PRINC"
        )
        SELECT r.trimestre, r.total_resp, r.total_resp * 100.0 / t.total
        FROM respiratorias r, total_internacoes t
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "diagnosis/category mention is a filter" in (message or "")


def test_semantic_validator_accepts_filtered_category_quarter_percentage():
    plan = build_semantic_plan(
        "Qual o total e o percentual de internações por doenças respiratórias (CID J%) em cada trimestre do ano no estado do RS?"
    )
    sql = """
        SELECT EXTRACT(QUARTER FROM i."DT_INTER") AS trimestre,
               COUNT(*) AS total_respiratorio,
               COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS pct_anual
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        WHERE i."DIAG_PRINC" LIKE 'J%' AND mu."estado" = 'RS'
        GROUP BY trimestre
        ORDER BY trimestre
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_detects_two_period_growth_comparison():
    plan = build_semantic_plan(
        "Quais são os 10 diagnósticos com maior crescimento absoluto de internações "
        "entre os períodos 2008-2012 e 2019-2023?"
    )

    assert plan.intent == "trend"
    assert plan.answer_shape.top_n == 10
    assert "diagnostico" in plan.answer_shape.required_dimensions
    assert any(filter_.field == "period_1" and filter_.values == ["2008", "2012"] for filter_ in plan.filters)
    assert any(filter_.field == "period_2" and filter_.values == ["2019", "2023"] for filter_ in plan.filters)
    assert "temporal_comparison_requires_matched_period_entities" in plan.constraints
    assert "temporal_growth_uses_after_minus_before" in plan.constraints


def test_semantic_validator_rejects_temporal_full_outer_join_for_growth():
    plan = build_semantic_plan(
        "Quais são os 10 diagnósticos com maior crescimento absoluto de internações "
        "entre os períodos 2008-2012 e 2019-2023?"
    )
    sql = """
        WITH p1 AS (
            SELECT "DIAG_PRINC", COUNT(*) AS total_2008_2012
            FROM internacoes
            WHERE EXTRACT(YEAR FROM "DT_INTER") BETWEEN 2008 AND 2012
            GROUP BY "DIAG_PRINC"
        ),
        p2 AS (
            SELECT "DIAG_PRINC", COUNT(*) AS total_2019_2023
            FROM internacoes
            WHERE EXTRACT(YEAR FROM "DT_INTER") BETWEEN 2019 AND 2023
            GROUP BY "DIAG_PRINC"
        )
        SELECT COALESCE(p1."DIAG_PRINC", p2."DIAG_PRINC") AS diagnostico,
               COALESCE(p2.total_2019_2023, 0) - COALESCE(p1.total_2008_2012, 0) AS crescimento
        FROM p1 FULL OUTER JOIN p2 ON p1."DIAG_PRINC" = p2."DIAG_PRINC"
        ORDER BY crescimento DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "matched entities" in (message or "")


def test_semantic_validator_rejects_temporal_delta_without_period_counts():
    plan = build_semantic_plan(
        "Quais são os 10 diagnósticos com maior crescimento absoluto de internações "
        "entre os períodos 2008-2012 e 2019-2023?"
    )
    sql = """
        WITH p1 AS (
            SELECT "DIAG_PRINC", COUNT(*) AS total
            FROM internacoes
            WHERE EXTRACT(YEAR FROM "DT_INTER") BETWEEN 2008 AND 2012
            GROUP BY "DIAG_PRINC"
        ),
        p2 AS (
            SELECT "DIAG_PRINC", COUNT(*) AS total
            FROM internacoes
            WHERE EXTRACT(YEAR FROM "DT_INTER") BETWEEN 2019 AND 2023
            GROUP BY "DIAG_PRINC"
        )
        SELECT p1."DIAG_PRINC", p2.total - p1.total AS crescimento
        FROM p1 JOIN p2 ON p1."DIAG_PRINC" = p2."DIAG_PRINC"
        ORDER BY crescimento DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "both period counts" in (message or "")


def test_semantic_validator_accepts_temporal_growth_with_period_counts():
    plan = build_semantic_plan(
        "Quais são os 10 diagnósticos com maior crescimento absoluto de internações "
        "entre os períodos 2008-2012 e 2019-2023?"
    )
    sql = """
        WITH p1 AS (
            SELECT "DIAG_PRINC" AS cid, COUNT(*) AS total_internacoes
            FROM internacoes
            WHERE EXTRACT(YEAR FROM "DT_INTER") BETWEEN 2008 AND 2012
            GROUP BY "DIAG_PRINC"
        ),
        p2 AS (
            SELECT "DIAG_PRINC" AS cid, COUNT(*) AS total_internacoes
            FROM internacoes
            WHERE EXTRACT(YEAR FROM "DT_INTER") BETWEEN 2019 AND 2023
            GROUP BY "DIAG_PRINC"
        )
        SELECT p1.cid,
               p1.total_internacoes AS periodo_2008_2012,
               p2.total_internacoes AS periodo_2019_2023,
               p2.total_internacoes - p1.total_internacoes AS crescimento_absoluto
        FROM p1 JOIN p2 ON p1.cid = p2.cid
        ORDER BY crescimento_absoluto DESC
        LIMIT 10
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_detects_decline_as_positive_drop():
    plan = build_semantic_plan(
        "Quais são os 10 diagnósticos com maior queda absoluta de internações "
        "entre os períodos 2008-2012 e 2019-2023?"
    )

    assert "temporal_decline_uses_before_minus_after" in plan.constraints


def test_semantic_plan_keeps_ranked_year_for_top_year_per_state():
    plan = build_semantic_plan("Em qual ano ocorreu o maior número de mortes em cada estado (MA e RS)?")

    assert plan.answer_shape.row_grain == "top_n_per_group"
    assert plan.answer_shape.top_n == 1
    assert plan.answer_shape.top_n_scope == "per_group"
    assert plan.answer_shape.required_dimensions == ["estado", "ano"]
    assert plan.answer_shape.partition_dimensions == ["estado"]
    assert plan.answer_shape.ranked_dimensions == ["ano"]
    assert "top_n_per_group_requires_window_partition" in plan.constraints


def test_semantic_validator_accepts_ranked_year_per_state_subquery():
    plan = build_semantic_plan("Em qual ano ocorreu o maior número de mortes em cada estado (MA e RS)?")
    sql = """
        SELECT estado, ano, total_mortes
        FROM (
            SELECT mu.estado,
                   EXTRACT(YEAR FROM i."DT_INTER") AS ano,
                   COUNT(*) AS total_mortes,
                   ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY COUNT(*) DESC) AS rn
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
            WHERE i."MORTE" = true
              AND mu.estado IN ('MA', 'RS')
              AND i."DT_INTER" IS NOT NULL
            GROUP BY mu.estado, ano
        ) sub
        WHERE rn = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_keeps_ranked_month_per_year():
    plan = build_semantic_plan("Em qual mês de cada ano (2008-2023) ocorreu o maior número de internações em UTI?")

    assert plan.answer_shape.row_grain == "top_n_per_group"
    assert plan.answer_shape.top_n == 1
    assert plan.answer_shape.partition_dimensions == ["ano"]
    assert plan.answer_shape.ranked_dimensions == ["mes"]
    assert plan.answer_shape.top_n_scope == "per_group"
    assert plan.answer_shape.required_dimensions == ["ano", "mes"]
    assert any(filter_.field == "uti" for filter_ in plan.filters)
    assert any(
        filter_.field == "ano_intervalo" and filter_.values == ["2008", "2023"]
        for filter_ in plan.filters
    )


def test_semantic_validator_accepts_exclusive_end_date_for_year_range():
    plan = build_semantic_plan("Em qual mês de cada ano (2008-2023) ocorreu o maior número de internações em UTI?")
    sql = """
        SELECT ano, mes, total
        FROM (
            SELECT EXTRACT(YEAR FROM "DT_INTER") AS ano,
                   EXTRACT(MONTH FROM "DT_INTER") AS mes,
                   COUNT(*) AS total,
                   ROW_NUMBER() OVER (
                       PARTITION BY EXTRACT(YEAR FROM "DT_INTER")
                       ORDER BY COUNT(*) DESC
                   ) AS rn
            FROM internacoes
            WHERE "VAL_UTI" > 0
              AND "DT_INTER" >= '2008-01-01'
              AND "DT_INTER" < '2024-01-01'
            GROUP BY ano, mes
        ) sub
        WHERE rn = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_uses_explicit_minimum_group_count():
    plan = build_semantic_plan(
        "Quais os 3 hospitais com maior valor médio de serviço hospitalar (VAL_SH) por estado (MA e RS), considerando hospitais com mais de 500 internações?"
    )

    assert plan.answer_shape.top_n_scope == "per_group"
    assert "estado_hospital" in plan.answer_shape.required_dimensions
    assert "hospital" in plan.answer_shape.required_dimensions
    assert plan.answer_shape.partition_dimensions == ["estado_hospital"]
    assert plan.answer_shape.ranked_dimensions == ["hospital"]
    assert {metric.name for metric in plan.metrics} == {"media_val_sh"}
    assert any(
        filter_.field == "minimum_group_count" and filter_.values == ["500"]
        for filter_ in plan.filters
    )


def test_goalv2_validator_rejects_residence_state_for_hospital_state_ranking():
    plan = build_semantic_plan(
        "Quais os 3 hospitais com maior valor médio de serviço hospitalar (VAL_SH) por estado (MA e RS), considerando hospitais com mais de 500 internações?"
    )
    sql = """
        SELECT estado, "CNES", total_internacoes, avg_val_sh, rk
        FROM (
            SELECT mu.estado, i."CNES", COUNT(*) AS total_internacoes,
                   ROUND(AVG(i."VAL_SH"), 2) AS avg_val_sh,
                   RANK() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_SH") DESC) AS rk
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
            WHERE mu.estado IN ('MA', 'RS') AND i."VAL_SH" IS NOT NULL
            GROUP BY mu.estado, i."CNES"
            HAVING COUNT(*) > 500
        ) sub
        WHERE rk <= 3
        ORDER BY estado, rk
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "hospital location" in (message or "") or "MUNIC_MOV" in (message or "")


def test_semantic_validator_rejects_uti_rate_where_filter_denominator_leakage():
    plan = build_semantic_plan(
        "Quais municípios com mais de 1000 internações têm taxa de internação em UTI mais de duas vezes acima da média nacional?"
    )
    sql = """
        WITH media_nacional AS (
            SELECT AVG(CASE WHEN "VAL_UTI" > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_uti
            FROM internacoes
        )
        SELECT mu.nome, COUNT(*) AS total, COUNT(*) * 100.0 / COUNT(*) AS taxa_uti
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        CROSS JOIN media_nacional mn
        WHERE i."VAL_UTI" > 0
        GROUP BY mu.nome, mn.taxa_uti
        HAVING COUNT(*) > 1000 AND COUNT(*) * 100.0 / COUNT(*) > 2 * mn.taxa_uti
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "double-divides AVG(CASE" in (message or "")


def test_semantic_validator_accepts_uti_rate_reference_comparison():
    plan = build_semantic_plan(
        "Quais municípios com mais de 1000 internações têm taxa de internação em UTI mais de duas vezes acima da média nacional?"
    )
    sql = """
        WITH media_nacional AS (
            SELECT SUM(CASE WHEN "VAL_UTI" > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_uti
            FROM internacoes
        )
        SELECT mu.nome,
               COUNT(*) AS total_internacoes,
               SUM(CASE WHEN i."VAL_UTI" > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_uti
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        CROSS JOIN media_nacional mn
        GROUP BY mu.nome, mn.taxa_uti
        HAVING COUNT(*) > 1000
           AND SUM(CASE WHEN i."VAL_UTI" > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) > 2 * mn.taxa_uti
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_tracks_revenue_ranking_metric_and_scope():
    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )

    assert plan.answer_shape.top_n_scope == "per_group"
    assert plan.answer_shape.partition_dimensions == ["especialidade"]
    assert plan.answer_shape.ranked_dimensions == ["hospital"]
    assert {metric.name for metric in plan.metrics} == {"receita_total"}


def test_semantic_validator_rejects_missing_explicit_minimum_group_count():
    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )
    sql = """
        SELECT especialidade, "CNES", receita_total
        FROM (
            SELECT e."DESCRICAO" AS especialidade, i."CNES",
                   SUM(i."VAL_TOT") AS receita_total,
                   ROW_NUMBER() OVER (PARTITION BY e."DESCRICAO" ORDER BY SUM(i."VAL_TOT") DESC) AS rn
            FROM internacoes i
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            GROUP BY e."DESCRICAO", i."CNES"
        ) sub
        WHERE rn = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "minimum group support" in (message or "")


def test_semantic_validator_rejects_partition_by_ranked_entity_for_top_n_per_group():
    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )
    sql = """
        SELECT "CNES", especialidade, receita_total
        FROM (
            SELECT i."CNES", e."DESCRICAO" AS especialidade,
                   SUM(i."VAL_TOT") AS receita_total,
                   ROW_NUMBER() OVER (
                       PARTITION BY i."CNES", e."DESCRICAO"
                       ORDER BY SUM(i."VAL_TOT") DESC
                   ) AS rn
            FROM internacoes i
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            GROUP BY i."CNES", e."DESCRICAO"
            HAVING COUNT(*) > 500
        ) sub
        WHERE rn = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "ranked entity" in (message or "")


def test_semantic_validator_rejects_count_ranking_when_revenue_requested():
    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )
    sql = """
        SELECT especialidade, "CNES", total_internacoes
        FROM (
            SELECT e."DESCRICAO" AS especialidade, i."CNES",
                   COUNT(*) AS total_internacoes,
                   ROW_NUMBER() OVER (
                       PARTITION BY e."DESCRICAO"
                       ORDER BY COUNT(*) DESC
                   ) AS rn
            FROM internacoes i
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            GROUP BY e."DESCRICAO", i."CNES"
            HAVING COUNT(*) > 500
        ) sub
        WHERE rn = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "receita total" in (message or "")


def test_semantic_validator_rejects_rank_for_top1_per_group():
    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )
    sql = """
        SELECT especialidade, "CNES", receita_total
        FROM (
            SELECT e."DESCRICAO" AS especialidade, i."CNES",
                   SUM(i."VAL_TOT") AS receita_total,
                   RANK() OVER (
                       PARTITION BY e."DESCRICAO"
                       ORDER BY SUM(i."VAL_TOT") DESC
                   ) AS rk
            FROM internacoes i
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            GROUP BY e."DESCRICAO", i."CNES"
            HAVING COUNT(*) > 500
        ) sub
        WHERE rk = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "top-1 per group should use ROW_NUMBER" in (message or "")


def test_semantic_validator_rejects_ranked_entity_before_group_in_top_n_output():
    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )
    sql = """
        WITH ranked AS (
            SELECT i."CNES", e."DESCRICAO" AS especialidade,
                   SUM(i."VAL_TOT") AS receita_total,
                   ROW_NUMBER() OVER (
                       PARTITION BY e."DESCRICAO"
                       ORDER BY SUM(i."VAL_TOT") DESC
                   ) AS rn
            FROM internacoes i
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            GROUP BY i."CNES", e."DESCRICAO"
            HAVING COUNT(*) > 500
        )
        SELECT "CNES", especialidade, receita_total
        FROM ranked
        WHERE rn = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "group/partition dimension before the ranked entity" in (message or "")


def test_semantic_validator_accepts_explicit_minimum_group_count():
    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )
    sql = """
        SELECT especialidade, "CNES", receita_total
        FROM (
            SELECT e."DESCRICAO" AS especialidade, i."CNES",
                   SUM(i."VAL_TOT") AS receita_total,
                   ROW_NUMBER() OVER (PARTITION BY e."DESCRICAO" ORDER BY SUM(i."VAL_TOT") DESC) AS rn
            FROM internacoes i
            JOIN especialidade e ON i."ESPEC" = e."ESPEC"
            GROUP BY e."DESCRICAO", i."CNES"
            HAVING COUNT(*) > 500
        ) sub
        WHERE rn = 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_keeps_count_entity_mentions_scalar_without_grouping():
    plan = build_semantic_plan("Quantos códigos CID-10 estão disponíveis?")

    assert plan.intent == "count"
    assert plan.answer_shape.row_grain == "single_scalar"
    assert not plan.answer_shape.required_dimensions
    assert not plan.answer_shape.requires_group_by


def test_semantic_plan_treats_age_extrema_as_scalar_aggregate_not_top_n():
    plan = build_semantic_plan("Qual a menor idade registrada nas internações?")

    assert plan.intent == "lookup"
    assert [metric.name for metric in plan.metrics] == ["idade_minima"]
    assert plan.metrics[0].expression_type == "min"
    assert plan.answer_shape.row_grain == "single_scalar"
    assert plan.answer_shape.top_n_scope == "none"
    assert plan.answer_shape.top_n is None


def test_semantic_plan_canonicalizes_under_one_year_age_filter():
    plan = build_semantic_plan(
        "Quantas internações foram registradas para pacientes com menos de 1 ano de idade?"
    )

    assert plan.intent == "count"
    assert plan.answer_shape.row_grain == "single_scalar"
    assert [(f.field, f.operator, f.values) for f in plan.filters] == [
        ("idade", "=", ["0"])
    ]


def test_semantic_plan_detects_age_above_filter_without_patient_prefix():
    plan = build_semantic_plan("Quantas internações com idade acima de 60 anos?")

    assert plan.intent == "count"
    assert plan.answer_shape.row_grain == "single_scalar"
    assert [(f.field, f.operator, f.values) for f in plan.filters] == [
        ("idade", ">", ["60"])
    ]


def test_semantic_plan_detects_cid_catalog_cardinality():
    plan = build_semantic_plan("Quantos códigos CID-10 distintos existem?")

    assert plan.intent == "count"
    assert plan.base_grain == "cid_catalog"
    assert [metric.name for metric in plan.metrics] == ["cid_catalog_count"]
    assert plan.answer_shape.row_grain == "single_scalar"
    assert "catalog_cardinality_must_use_reference_table" in plan.constraints


def test_semantic_validator_requires_cid_reference_for_catalog_cardinality():
    plan = build_semantic_plan("Quantos códigos CID-10 distintos existem?")

    valid, message = validate_sql_against_semantic_plan(
        plan,
        'SELECT COUNT(DISTINCT "DIAG_PRINC") FROM internacoes;',
    )

    assert valid is False
    assert message is not None
    assert "cid reference table" in message.lower() or "catálogo" in message.lower()


def test_semantic_validator_accepts_cid_reference_catalog_count():
    plan = build_semantic_plan("Quantos códigos CID-10 distintos existem?")

    valid, message = validate_sql_against_semantic_plan(
        plan,
        'SELECT COUNT(DISTINCT "CID") FROM cid;',
    )

    assert valid is True
    assert message is None


def test_semantic_plan_detects_vincprev_catalog_cardinality():
    plan = build_semantic_plan("Quantos tipos de vínculo previdenciário existem?")

    assert plan.intent == "count"
    assert plan.base_grain == "vincprev_catalog"
    assert [metric.name for metric in plan.metrics] == ["vincprev_catalog_count"]
    assert plan.answer_shape.row_grain == "single_scalar"
    assert "catalog_cardinality_must_use_reference_table" in plan.constraints


def test_semantic_validator_requires_vincprev_reference_for_catalog_cardinality():
    plan = build_semantic_plan("Quantos tipos de vínculo previdenciário existem?")

    valid, message = validate_sql_against_semantic_plan(
        plan,
        'SELECT COUNT(DISTINCT "VINCPREV") FROM internacoes WHERE "VINCPREV" IS NOT NULL;',
    )

    assert valid is False
    assert message is not None
    assert "reference table" in message.lower()


def test_semantic_validator_accepts_vincprev_reference_catalog_count():
    plan = build_semantic_plan("Quantos tipos de vínculo previdenciário existem?")

    valid, message = validate_sql_against_semantic_plan(plan, "SELECT COUNT(*) FROM vincprev;")

    assert valid is True
    assert message is None


def test_semantic_plan_detects_state_coverage_cardinality():
    plan = build_semantic_plan("Quantos estados distintos estão cobertos pelo banco de dados?")

    assert plan.intent == "count"
    assert plan.base_grain == "municipio_catalog"
    assert [metric.name for metric in plan.metrics] == ["estado_coverage_count"]
    assert plan.answer_shape.row_grain == "single_scalar"
    assert "catalog_cardinality_must_use_reference_table" in plan.constraints


def test_semantic_validator_requires_municipios_for_state_coverage():
    plan = build_semantic_plan("Quantos estados distintos estão cobertos pelo banco de dados?")

    valid, message = validate_sql_against_semantic_plan(
        plan,
        'SELECT COUNT(DISTINCT mu."estado") FROM municipios mu JOIN internacoes i ON mu."codigo_6d" = i."MUNIC_RES";',
    )

    assert valid is False
    assert message is not None
    assert "reference" in message.lower()


def test_semantic_validator_accepts_municipios_for_state_coverage():
    plan = build_semantic_plan("Quantos estados distintos estão cobertos pelo banco de dados?")

    valid, message = validate_sql_against_semantic_plan(
        plan,
        'SELECT COUNT(DISTINCT "estado") FROM municipios;',
    )

    assert valid is True
    assert message is None


def test_semantic_plan_preserves_multi_state_comparison_dimension():
    plan = build_semantic_plan(
        "Qual o total de internações para o estado do Maranhão e para o estado do Rio Grande do Sul?"
    )

    assert plan.intent == "count"
    assert plan.answer_shape.row_grain == "one_row_per_group"
    assert "estado" in plan.answer_shape.required_dimensions
    assert any(
        semantic_filter.field == "estado" and set(semantic_filter.values) == {"MA", "RS"}
        for semantic_filter in plan.filters
    )


def test_semantic_plan_preserves_plural_multi_state_comparison_dimension():
    plan = build_semantic_plan("Qual o total de esgotamento sanitário nos estados do MA e RS?")

    assert plan.answer_shape.row_grain == "one_row_per_group"
    assert "estado" in plan.answer_shape.required_dimensions


def test_semantic_plan_does_not_treat_recebem_as_hospital_location():
    plan = build_semantic_plan(
        "Qual o total de benefício Bolsa Família que o estado do MA e RS recebem?"
    )

    assert "join_path_hospital_location_required" not in plan.constraints
    assert "estado" in plan.answer_shape.required_dimensions


def test_semantic_plan_allows_explicit_combined_multi_state_total():
    plan = build_semantic_plan("Qual o total combinado de internações nos estados MA e RS?")

    assert plan.intent == "count"
    assert plan.answer_shape.row_grain == "single_scalar"
    assert "estado" not in plan.answer_shape.required_dimensions


def test_semantic_plan_treats_principal_secondary_diagnosis_question_as_scalar_count():
    plan = build_semantic_plan(
        "Quantas internações tiveram tanto diagnóstico principal quanto secundário?"
    )

    assert plan.intent == "count"
    assert plan.answer_shape.row_grain == "single_scalar"
    assert plan.answer_shape.required_dimensions == []
    assert plan.answer_shape.top_n is None
    assert any(filter_.field == "diagnostico_principal_required" for filter_ in plan.filters)
    assert any(filter_.field == "diagnostico_secundario_required" for filter_ in plan.filters)


def test_semantic_plan_treats_respiratory_disease_as_filter_not_breakdown():
    plan = build_semantic_plan(
        "Quantas internações por doença respiratória ocorrem no inverno (junho a agosto)?"
    )

    assert plan.intent == "count"
    assert plan.answer_shape.row_grain == "single_scalar"
    assert "diagnostico" not in plan.answer_shape.required_dimensions
    assert any(
        filter_.field == "diagnostico_principal_prefix" and filter_.values == ["J%"]
        for filter_ in plan.filters
    )
    assert any(
        filter_.field == "mes_internacao" and filter_.values == ["6", "7", "8"]
        for filter_ in plan.filters
    )


def test_semantic_validator_rejects_grouped_sql_for_scalar_count():
    plan = build_semantic_plan(
        "Quantas internações por doença respiratória ocorrem no inverno (junho a agosto)?"
    )
    sql = """
        SELECT c."CD_DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE c."CID" LIKE 'J%' AND EXTRACT(MONTH FROM i."DT_INTER") IN (6, 7, 8)
        GROUP BY c."CD_DESCRICAO"
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is False
    assert "single scalar" in (message or "").lower()


def test_semantic_validator_accepts_scalar_respiratory_winter_count():
    plan = build_semantic_plan(
        "Quantas internações por doença respiratória ocorrem no inverno (junho a agosto)?"
    )
    sql = """
        SELECT COUNT(*) AS total
        FROM internacoes i
        WHERE i."DIAG_PRINC" LIKE 'J%'
          AND EXTRACT(MONTH FROM i."DT_INTER") IN (6, 7, 8)
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_distinguishes_exact_age_from_age_band():
    exact_age_plan = build_semantic_plan("Qual a distribuição por idade nas internações?")
    age_band_plan = build_semantic_plan("Qual a distribuição por faixa etária nas internações?")

    assert exact_age_plan.answer_shape.required_dimensions == ["idade"]
    assert age_band_plan.answer_shape.required_dimensions == ["faixa_etaria"]


def test_semantic_plan_treats_patient_categorical_attribute_as_distribution():
    plan = build_semantic_plan("Qual o nível de instrução dos pacientes internados?")

    assert plan.intent == "distribution"
    assert plan.answer_shape.row_grain == "one_row_per_group"
    assert plan.answer_shape.required_dimensions == ["instrucao"]
    assert "domain_instrucao_valid_required" in plan.constraints
    assert any(filter_.field == "instrucao_valid" for filter_ in plan.filters)


def test_semantic_plan_supports_population_value_metric():
    plan = build_semantic_plan(
        "Quantos habitantes tem o município que tem a maior população segundo dados do IBGE?"
    )

    assert plan.intent == "ranking"
    assert plan.base_grain == "municipio_ano_metrica"
    assert [metric.name for metric in plan.metrics] == ["populacao_total"]
    assert plan.metrics[0].expression_type == "value"
    assert plan.answer_shape.row_grain == "top_n_global"
    assert plan.answer_shape.top_n == 1
    assert plan.answer_shape.requires_group_by is False
    assert any(
        filter_.field == "metrica" and filter_.values == ["populacao_total"]
        for filter_ in plan.filters
    )


def test_semantic_validator_accepts_population_value_ranking_without_group_by():
    plan = build_semantic_plan(
        "Quantos habitantes tem o município que tem a maior população segundo dados do IBGE?"
    )
    sql = """
        SELECT mu."nome", s."valor" AS total_habitantes
        FROM socioeconomico s
        JOIN municipios mu ON s."codigo_6d" = mu."codigo_6d"
        WHERE s."metrica" = 'populacao_total'
        ORDER BY s."valor" DESC
        LIMIT 1
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_validator_rejects_scalar_count_for_patient_categorical_attribute():
    plan = build_semantic_plan("Qual o nível de instrução dos pacientes internados?")

    valid, message = validate_sql_against_semantic_plan(
        plan,
        'SELECT COUNT(*) AS total FROM internacoes WHERE "INSTRU" IS NOT NULL AND "INSTRU" != 0;',
    )

    assert valid is False
    assert message is not None
    assert "GROUP BY" in message


def test_semantic_validator_accepts_instruction_distribution():
    plan = build_semantic_plan("Qual o nível de instrução dos pacientes internados?")
    sql = """
        SELECT ins."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN instrucao ins ON i."INSTRU" = ins."INSTRU"
        WHERE i."INSTRU" IS NOT NULL AND i."INSTRU" != 0
        GROUP BY ins."INSTRU", ins."DESCRICAO"
    """

    valid, message = validate_sql_against_semantic_plan(plan, sql)

    assert valid is True
    assert message is None


def test_semantic_plan_treats_state_name_as_filter_not_output_dimension():
    plan = build_semantic_plan("Qual a taxa de mortalidade no estado do Rio Grande do Sul em 2021?")

    assert plan.answer_shape.row_grain == "single_scalar"
    assert not plan.answer_shape.required_dimensions
    assert any(filter_.field == "estado" and filter_.values == ["RS"] for filter_ in plan.filters)
    assert any(filter_.field == "ano" and filter_.values == ["2021"] for filter_ in plan.filters)


def test_semantic_plan_treats_gender_in_scalar_average_as_filter():
    plan = build_semantic_plan("Qual é o valor médio de UTI para homens?")

    assert plan.answer_shape.row_grain == "single_scalar"
    assert not plan.answer_shape.required_dimensions
    assert any(filter_.field == "sexo" and filter_.values == ["1"] for filter_ in plan.filters)


def test_plan_gate_persists_semantic_telemetry_metadata():
    state = create_initial_messages_state(
        user_query="Quais são os 3 hospitais com maior custo médio de UTI por estado?",
        session_id="semantic-telemetry-test",
    )

    new_state = plan_gate_node(state)
    metadata = new_state["response_metadata"]

    assert "semantic_plan" in metadata
    assert "semantic_constraints" in metadata
    assert "top_n_per_group_requires_window_partition" in metadata["semantic_constraints"]


def test_semantic_catalog_loads_versioned_metrics_dimensions_and_rules():
    catalog = load_semantic_catalog()
    summary = catalog_summary()

    assert catalog.version >= 1
    assert "taxa_mortalidade" in catalog.metrics
    assert catalog.metrics["taxa_mortalidade"].denominator == "COUNT(*)"
    assert "hospital" in catalog.dimensions
    assert catalog.dimensions["hospital"].output_policy == "preserve_cnes_identifier"
    assert "top_n_per_group" in catalog.macros
    assert summary["rule_count"] >= 4


def test_semantic_catalog_prompt_context_is_selective_and_reusable():
    context = render_catalog_prompt_context(
        metric_names=["taxa_mortalidade"],
        dimension_names=["hospital"],
        rule_names=["rate_denominator_must_preserve_full_scope"],
    )

    assert "taxa_mortalidade" in context
    assert "denominator=COUNT(*)" in context
    assert "source=internacoes.CNES" in context
    assert "rate_denominator_must_preserve_full_scope" in context
    assert "total_obitos" not in context


def test_semantic_catalog_context_can_be_rendered_from_plan():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    context = render_catalog_context_for_plan(plan)

    assert "taxa_mortalidade" in context
    assert "estado_residencia" in context
    assert "ano_internacao" in context
    assert "rate_denominator_must_preserve_full_scope" in context


def test_semantic_catalog_context_includes_cid_catalog_count_rule():
    plan = build_semantic_plan("Quantos códigos CID-10 distintos existem?")
    context = render_catalog_context_for_plan(plan)

    assert "cid_catalog_count" in context
    assert "catalog_cardinality_must_use_reference_table" in context


def test_data_profile_query_builder_creates_summary_and_top_values_sql():
    query_set = build_column_profile_queries(
        ColumnProfileSpec(table="internacoes", column="MORTE", kind="categorical", top_k=5)
    )

    assert 'COUNT(DISTINCT "MORTE") AS distinct_count' in query_set.summary_sql
    assert 'SUM(CASE WHEN "MORTE" IS NULL THEN 1 ELSE 0 END)' in query_set.summary_sql
    assert query_set.top_values_sql is not None
    assert 'GROUP BY "MORTE"' in query_set.top_values_sql
    assert "LIMIT 5" in query_set.top_values_sql


def test_semantic_error_taxonomy_classifies_validator_messages():
    assert (
        classify_semantic_error("SQL has no PARTITION BY for top-N per group")
        == SemanticErrorCategory.TOP_N_SCOPE
    )
    assert (
        classify_semantic_error(
            "Mortality-rate SQL filters MORTE=true in WHERE, damaging denominator"
        )
        == SemanticErrorCategory.RATE_DENOMINATOR
    )
    record = build_semantic_error_record("SQL does not use NOT EXISTS for absence")
    assert record.category == SemanticErrorCategory.ABSENCE_CONDITION
    assert record.severity == "error"


def test_semantic_sql_signature_captures_structural_features():
    sql = """
        SELECT mu.estado, COUNT(*),
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE mu.estado IN ('SP', 'RJ')
        GROUP BY mu.estado
    """

    signature = semantic_sql_signature(sql)

    assert signature.tables == {"internacoes", "municipios"}
    assert signature.has_conditional_mortality_numerator
    assert "estado" in signature.group_by


def test_semantic_sql_equivalence_ignores_alias_and_formatting_differences():
    left = """
        SELECT mu.estado, COUNT(*)
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE mu.estado IN ('SP', 'RJ')
        GROUP BY mu.estado
    """
    right = """
        SELECT m.estado, COUNT(*)
        FROM internacoes AS x
        JOIN municipios AS m ON x."MUNIC_RES" = m.codigo_6d
        WHERE m.estado IN ('SP', 'RJ')
        GROUP BY m.estado
    """

    assert same_semantic_pattern(left, right)


def test_data_profile_query_builder_adds_ranges_for_numeric_columns():
    query_set = build_column_profile_queries(
        ColumnProfileSpec(table="internacoes", column="VAL_UTI", kind="numeric")
    )

    assert 'MIN("VAL_UTI") AS min_value' in query_set.summary_sql
    assert 'MAX("VAL_UTI") AS max_value' in query_set.summary_sql
    assert query_set.top_values_sql is None


def test_default_profile_specs_cover_core_semantic_columns():
    query_sets = build_default_profile_query_sets()
    pairs = {(query_set.table, query_set.column) for query_set in query_sets}

    assert ("internacoes", "MORTE") in pairs
    assert ("internacoes", "VAL_UTI") in pairs
    assert ("internacoes", "DT_INTER") in pairs
    assert ("municipios", "estado") in pairs


def test_semantic_plan_detects_para_cada_as_top_n_per_group():
    plan = build_semantic_plan("Quais são os 5 procedimentos mais comuns para cada sexo?")

    assert plan.intent == "ranking"
    assert plan.answer_shape.top_n_scope == "per_group"
    assert "top_n_per_group_requires_window_partition" in plan.constraints
    assert "sexo" in plan.answer_shape.required_dimensions


def test_semantic_plan_detects_rate_without_outcome_filter():
    plan = build_semantic_plan("Qual a taxa de mortalidade por município?")

    assert plan.intent == "rate"
    assert any(metric.name == "taxa_mortalidade" for metric in plan.metrics)
    assert "rate_denominator_must_preserve_full_scope" in plan.constraints
    assert not any(f.field == "desfecho" for f in plan.filters)
    assert "faixa_etaria" not in plan.answer_shape.required_dimensions


def test_semantic_plan_does_not_confuse_mortalidade_with_idade_dimension():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")

    assert "estado" in plan.answer_shape.required_dimensions
    assert "ano" in plan.answer_shape.required_dimensions
    assert "faixa_etaria" not in plan.answer_shape.required_dimensions


def test_semantic_validator_rejects_global_limit_for_per_group_top_n():
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
    sql = """
        SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE i."VAL_UTI" > 0
        GROUP BY mu.estado, i."CNES"
        ORDER BY custo DESC
        LIMIT 3
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "ROW_NUMBER" in (message or "")


def test_semantic_validator_accepts_per_group_window_pattern():
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
    sql = """
        SELECT estado, "CNES", custo
        FROM (
            SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo,
                   ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_UTI") DESC) AS rn
            FROM internacoes i
            JOIN hospital h ON i."CNES" = h."CNES"
            JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
            WHERE i."VAL_UTI" > 0
            GROUP BY mu.estado, i."CNES"
            HAVING COUNT(*) > 100
        ) sub
        WHERE rn <= 3
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_plan_detects_hospital_location_join_path_for_care_municipality():
    plan = build_semantic_plan("Quais são os 10 municípios que atendem mais pacientes?")

    assert plan.intent == "ranking"
    assert plan.answer_shape.top_n == 10
    assert "municipio_hospital" in plan.answer_shape.required_dimensions
    assert "join_path_hospital_location_required" in plan.constraints
    assert any(metric.name == "total" for metric in plan.metrics)


def test_semantic_validator_rejects_residence_join_for_care_municipality():
    plan = build_semantic_plan("Quais são os 10 municípios que atendem mais pacientes?")
    sql = """
        SELECT mu.nome, COUNT(i."N_AIH") AS total
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        GROUP BY mu.nome
        ORDER BY total DESC
        LIMIT 10
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "hospital location" in (message or "") or "MUNIC_RES" in (message or "")


def test_semantic_validator_accepts_hospital_location_join_for_care_municipality():
    plan = build_semantic_plan("Quais são os 10 municípios que atendem mais pacientes?")
    sql = """
        SELECT mu.nome, COUNT(i."N_AIH") AS total
        FROM internacoes i
        JOIN hospital h ON i."CNES" = h."CNES"
        JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
        GROUP BY mu.nome
        ORDER BY total DESC
        LIMIT 10
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_plan_requires_support_for_high_cardinality_average_top_n():
    plan = build_semantic_plan(
        "Quais são os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?"
    )

    assert plan.answer_shape.top_n_scope == "per_group"
    assert "estado_hospital" in plan.answer_shape.required_dimensions
    assert "hospital" in plan.answer_shape.required_dimensions
    assert "top_n_average_high_cardinality_requires_minimum_group_size" in plan.constraints
    assert any(filter_.field == "minimum_group_count" for filter_ in plan.filters)


def test_semantic_validator_rejects_hospital_average_top_n_without_support():
    plan = build_semantic_plan(
        "Quais são os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?"
    )
    sql = """
        SELECT estado, "CNES", custo
        FROM (
            SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo,
                   ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_UTI") DESC) AS rn
            FROM internacoes i
            JOIN hospital h ON i."CNES" = h."CNES"
            JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
            WHERE i."VAL_UTI" > 0 AND mu.estado IN ('MA', 'RS')
            GROUP BY mu.estado, i."CNES"
        ) ranked
        WHERE rn <= 3
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "HAVING COUNT" in (message or "")


def test_semantic_validator_accepts_hospital_average_top_n_with_support():
    plan = build_semantic_plan(
        "Quais são os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?"
    )
    sql = """
        SELECT estado, "CNES", custo
        FROM (
            SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo,
                   ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_UTI") DESC) AS rn
            FROM internacoes i
            JOIN hospital h ON i."CNES" = h."CNES"
            JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
            WHERE i."VAL_UTI" > 0 AND mu.estado IN ('MA', 'RS')
            GROUP BY mu.estado, i."CNES"
            HAVING COUNT(*) > 100
        ) ranked
        WHERE rn <= 3
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_accepts_per_group_rank_alias_not_named_rn():
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
    sql = """
        SELECT estado, "CNES", custo
        FROM (
            SELECT mu.estado, i."CNES", AVG(i."VAL_UTI") AS custo,
                   RANK() OVER (PARTITION BY mu.estado ORDER BY AVG(i."VAL_UTI") DESC) AS ranking
            FROM internacoes i
            JOIN hospital h ON i."CNES" = h."CNES"
            JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
            WHERE i."VAL_UTI" > 0
            GROUP BY mu.estado, i."CNES"
            HAVING COUNT(*) > 100
        ) ranked
        WHERE ranking <= 3
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_rejects_mortality_rate_with_filtered_denominator():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               COUNT(*) AS total,
               ROUND(COUNT(*) * 100.0 / COUNT(*), 2) AS taxa_mortalidade
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE i."MORTE" = true
        GROUP BY mu.estado, ano
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "denominator" in (message or "")


def test_semantic_validator_does_not_treat_conditional_numerator_as_filtered_denominator():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS mortes,
               COUNT(*) AS total,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        WHERE mu.estado IN ('SP', 'RJ')
        GROUP BY mu.estado, ano
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_rejects_unrequested_nonzero_filter_in_time_series():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        WITH taxa_mortalidade AS (
            SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
                   SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
            GROUP BY mu.estado, ano
        )
        SELECT estado, ano, taxa
        FROM taxa_mortalidade tm
        WHERE tm.taxa > 0
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "non-zero" in (message or "")


def test_semantic_validator_rejects_rank_filter_in_time_series_without_top_n_intent():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado (MA e RS)?")
    sql = """
        WITH taxa_mortalidade AS (
            SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
                   COUNT(*) AS total_internacoes,
                   SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_mortes,
                   ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS taxa
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
            WHERE mu.estado IN ('MA', 'RS')
            GROUP BY mu.estado, ano
        ),
        por_estado AS (
            SELECT estado, ano, total_internacoes, total_mortes, taxa,
                   ROW_NUMBER() OVER (PARTITION BY estado ORDER BY ano) AS rn
            FROM taxa_mortalidade
        )
        SELECT estado, ano, total_internacoes, total_mortes, taxa
        FROM por_estado
        WHERE rn = 1
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "return every requested period" in (message or "")


def test_semantic_validator_rejects_group_by_missing_required_dimension():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT mu.estado, EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        GROUP BY ano
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "estado" in (message or "")


def test_semantic_validator_rejects_missing_required_state_filter():
    plan = build_semantic_plan("Quantas mortes foram registradas no estado do RS?")
    sql = """
        SELECT mu.estado, COUNT(*) AS total_mortes
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        WHERE i."MORTE" = true
        GROUP BY mu.estado
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "estado filter" in (message or "")


def test_semantic_rules_reject_internacoes_self_join_row_explosion():
    sql = """
        SELECT mu.estado, ano,
               ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS taxa_mortalidade
        FROM (
            SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, i."MUNIC_RES", i."MORTE"
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
            WHERE mu.estado IN ('MA', 'RS')
        ) sub
        JOIN internacoes i ON sub."MUNIC_RES" = i."MUNIC_RES"
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        GROUP BY mu.estado, ano
        ORDER BY mu.estado, ano
    """

    passed, message = check_semantic_rules(
        "Qual a evolução anual da taxa de mortalidade por estado (MA e RS)?",
        sql,
    )

    assert not passed
    assert "row explosion" in (message or "")


def test_semantic_rules_allow_population_value_question_without_count():
    sql = """
        SELECT mu."nome", s."valor" AS total_habitantes
        FROM socioeconomico s
        JOIN municipios mu ON s."codigo_6d" = mu."codigo_6d"
        WHERE s."metrica" = 'populacao_total'
        ORDER BY s."valor" DESC
        LIMIT 1
    """

    passed, message = check_semantic_rules(
        "Quantos habitantes tem o município que tem a maior população segundo dados do IBGE?",
        sql,
    )

    assert passed
    assert message is None


def test_semantic_rules_allow_count_metric_inside_top_year_question():
    sql = """
        SELECT estado, ano, total_mortes
        FROM (
            SELECT mu.estado,
                   EXTRACT(YEAR FROM i."DT_INTER") AS ano,
                   COUNT(*) AS total_mortes,
                   ROW_NUMBER() OVER (PARTITION BY mu.estado ORDER BY COUNT(*) DESC) AS rn
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
            WHERE i."MORTE" = true
              AND mu.estado IN ('MA', 'RS')
            GROUP BY mu.estado, ano
        ) sub
        WHERE rn = 1
    """

    passed, message = check_semantic_rules(
        "Em qual ano ocorreu o maior número de mortes em cada estado (MA e RS)?",
        sql,
    )

    assert passed
    assert message is None


def test_semantic_validator_requires_unknown_bucket_policy():
    plan = build_semantic_plan(
        "Qual a distribuição por categoria incluindo os casos sem informação?"
    )
    sql = """
        SELECT c."DESCRICAO", COUNT(*)
        FROM internacoes i
        JOIN categoria c ON i."CAT" = c."CAT"
        GROUP BY c."DESCRICAO"
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "COALESCE" in (message or "")


def test_semantic_validator_accepts_case_unknown_bucket_policy():
    plan = build_semantic_plan(
        "Qual a distribuição por categoria incluindo os casos sem informação?"
    )
    sql = """
        SELECT
            CASE WHEN c."DESCRICAO" IS NULL THEN 'Sem informação' ELSE c."DESCRICAO" END AS categoria,
            COUNT(*)
        FROM internacoes i
        LEFT JOIN categoria c ON i."CAT" = c."CAT"
        GROUP BY categoria
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_accepts_aggregate_zero_absence_condition():
    plan = build_semantic_plan(
        "Quais hospitais com mais de 1000 internações nunca tiveram internação em UTI?"
    )
    sql = """
        SELECT "CNES", COUNT(*) AS total
        FROM internacoes
        GROUP BY "CNES"
        HAVING COUNT(*) > 1000
           AND SUM(CASE WHEN "VAL_UTI" > 0 THEN 1 ELSE 0 END) = 0
        ORDER BY total DESC
        LIMIT 10
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_accepts_count_case_zero_absence_condition_by_dimension():
    plan = build_semantic_plan("Quais hospitais nunca registraram cobrança de UTI por estado?")
    sql = """
        SELECT mu.estado, h."CNES"
        FROM hospital h
        JOIN internacoes i ON h."CNES" = i."CNES"
        JOIN municipios mu ON h."MUNIC_MOV" = mu.codigo_6d
        GROUP BY mu.estado, h."CNES"
        HAVING COUNT(CASE WHEN i."VAL_UTI" > 0 THEN 1 END) = 0
        ORDER BY mu.estado, h."CNES"
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_validator_accepts_absence_not_exists_without_group_by():
    plan = build_semantic_plan("Quais hospitais nunca registraram cobrança de UTI?")
    sql = """
        SELECT h."CNES"
        FROM hospital h
        WHERE NOT EXISTS (
            SELECT 1
            FROM internacoes i
            WHERE i."CNES" = h."CNES"
              AND i."VAL_UTI" > 0
        )
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_plan_requires_valid_instrucao_domain_filter():
    plan = build_semantic_plan(
        "Qual é a taxa de mortalidade por nível de instrução no estado do RS, "
        "considerando apenas grupos com mais de 1000 internações?"
    )

    assert "instrucao" in plan.answer_shape.required_dimensions
    assert "domain_instrucao_valid_required" in plan.constraints
    assert any(filter_.field == "instrucao_valid" for filter_ in plan.filters)


def test_semantic_validator_rejects_instrucao_group_without_valid_code_filter():
    plan = build_semantic_plan(
        "Qual é a taxa de mortalidade por nível de instrução no estado do RS, "
        "considerando apenas grupos com mais de 1000 internações?"
    )
    sql = """
        SELECT inst."DESCRICAO",
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        JOIN instrucao inst ON i."INSTRU" = inst."INSTRU"
        WHERE mu.estado = 'RS'
        GROUP BY inst."DESCRICAO"
        HAVING COUNT(*) > 1000
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "INSTRU=0" in (message or "") or "NULL INSTRU" in (message or "")


def test_semantic_validator_accepts_instrucao_group_with_valid_code_filter():
    plan = build_semantic_plan(
        "Qual é a taxa de mortalidade por nível de instrução no estado do RS, "
        "considerando apenas grupos com mais de 1000 internações?"
    )
    sql = """
        SELECT inst."DESCRICAO",
               SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.codigo_6d
        JOIN instrucao inst ON i."INSTRU" = inst."INSTRU"
        WHERE mu.estado = 'RS' AND i."INSTRU" IS NOT NULL AND i."INSTRU" != 0
        GROUP BY inst."DESCRICAO"
        HAVING COUNT(*) > 1000
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_plan_resolves_infant_mortality_to_socioeconomico_metric():
    plan = build_semantic_plan("Qual a taxa de mortalidade infantil média no Brasil?")

    assert plan.base_grain == "municipio_ano_metrica"
    assert any(metric.name == "mortalidade_infantil_1ano" for metric in plan.metrics)
    assert "socioeconomico_metric_filter_required" in plan.constraints
    assert any(
        filter_.field == "metrica" and filter_.values == ["mortalidade_infantil_1ano"]
        for filter_ in plan.filters
    )


def test_semantic_validator_rejects_wrong_socioeconomico_metric_for_infant_mortality():
    plan = build_semantic_plan("Qual a taxa de mortalidade infantil média no Brasil?")
    sql = """
        SELECT AVG(s."valor") AS media
        FROM socioeconomico s
        WHERE s."metrica" = 'bolsa_familia_total'
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "mortalidade_infantil_1ano" in (message or "")


def test_semantic_validator_accepts_infant_mortality_metric_filter():
    plan = build_semantic_plan("Qual a taxa de mortalidade infantil média no Brasil?")
    sql = """
        SELECT AVG(s."valor") AS media
        FROM socioeconomico s
        WHERE s."metrica" = 'mortalidade_infantil_1ano'
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message


def test_semantic_plan_resolves_socioeconomico_sum_metric():
    plan = build_semantic_plan("Qual o total de esgotamento sanitário nos estados do MA e RS?")

    assert plan.base_grain == "municipio_ano_metrica"
    assert [metric.name for metric in plan.metrics] == ["esgotamento_sanitario_domicilio"]
    assert plan.metrics[0].expression_type == "sum"
    assert "estado" in plan.answer_shape.required_dimensions
    assert any(
        filter_.field == "metrica"
        and filter_.values == ["esgotamento_sanitario_domicilio"]
        for filter_ in plan.filters
    )


def test_semantic_validator_rejects_count_for_socioeconomico_total_metric():
    plan = build_semantic_plan("Qual o total de esgotamento sanitário nos estados do MA e RS?")
    sql = """
        SELECT mu."estado", COUNT(*) AS total_esgotamento_sanitario
        FROM socioeconomico s
        JOIN municipios mu ON s."codigo_6d" = mu."codigo_6d"
        WHERE s."metrica" = 'esgotamento_sanitario_domicilio'
          AND mu."estado" IN ('MA', 'RS')
        GROUP BY mu."estado"
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "SUM(valor)" in (message or "")


def test_orchestrator_config_defaults_do_not_mask_table_selection_preset_without_langchain():
    cfg = OrchestratorConfig()
    strategy = resolve_table_selection_strategy(
        preset_name=cfg.table_selection_preset,
        mode=cfg.table_selection_mode,
        description_variant=cfg.table_selection_description_variant,
        prompt_variant=cfg.table_selection_prompt_variant,
    )

    assert strategy["preset_name"] == "llm_best"
    assert strategy["mode"] == "llm_only"
    assert strategy["description_variant"] == "role_guardrails"
    assert strategy["prompt_variant"] == "decision_checklist"


def test_goalv2_plan_detects_written_top_n_obstetric_municipality():
    plan = build_semantic_plan("Quais os cinco municípios com mais internações obstétricas registradas?")

    assert plan.intent == "ranking"
    assert plan.answer_shape.top_n == 5
    assert plan.answer_shape.top_n_scope == "global"
    assert plan.answer_shape.required_dimensions == ["municipio"]
    assert any(filter_.field == "obstetrico" for filter_ in plan.filters)


def test_semantic_plan_preserves_ranked_entity_dimension_without_explicit_top_n():
    plan = build_semantic_plan("Gere um grafico de barras com os municipios que tiveram mais mortes.")

    assert plan.intent in {"distribution", "unknown"}
    assert plan.answer_shape.row_grain == "one_row_per_group"
    assert plan.answer_shape.requires_group_by is True
    assert plan.answer_shape.required_dimensions == ["municipio"]
    assert any(metric.name == "total_mortes" for metric in plan.metrics)


def test_semantic_plan_adds_year_dimension_for_over_years_trend():
    plan = build_semantic_plan("Gere um grafico de linhas das internacoes por estado ao longo dos anos.")

    assert plan.intent == "trend"
    assert plan.answer_shape.row_grain == "time_series"
    assert "estado" in plan.answer_shape.required_dimensions
    assert "ano" in plan.answer_shape.required_dimensions
    assert plan.answer_shape.requires_group_by is True


def test_semantic_plan_adds_month_dimension_for_monthly_chart():
    plan = build_semantic_plan("Visualize em grafico as internacoes mensais.")

    assert plan.intent == "trend"
    assert plan.answer_shape.row_grain == "time_series"
    assert plan.answer_shape.required_dimensions == ["mes"]
    assert plan.answer_shape.requires_group_by is True


def test_goalv2_validator_rejects_scalar_for_top_n_municipality():
    plan = build_semantic_plan("Quais os cinco municípios com mais internações obstétricas registradas?")
    sql = 'SELECT COUNT(*) AS total_internacoes FROM internacoes i WHERE i."ESPEC" = 2'

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "GROUP BY" in (message or "") or "top-N" in (message or "")


def test_goalv2_plan_uses_death_cause_description_for_disease_death_question():
    plan = build_semantic_plan("Quantas internações por meningite ocasionaram em morte?")

    assert "death_cause_description_requires_cid_morte" in plan.constraints
    assert any(filter_.field == "cid_morte_descricao" for filter_ in plan.filters)
    assert any(filter_.field == "desfecho" for filter_ in plan.filters)


def test_goalv2_validator_rejects_primary_diagnosis_for_death_cause_description():
    plan = build_semantic_plan("Quantas internações por meningite ocasionaram em morte?")
    sql = """
        SELECT COUNT(*)
        FROM internacoes i
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE i."MORTE" = true
          AND c."CD_DESCRICAO" ILIKE '%meningite%'
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "CID_MORTE" in (message or "")


def test_goalv2_plan_treats_more_than_sixty_years_as_age_filter_not_support():
    plan = build_semantic_plan(
        "Quais são os 3 diagnósticos principais mais comuns entre pacientes com mais de 60 anos "
        "no estado de MA e no estado do RS?"
    )

    assert plan.answer_shape.top_n_scope == "per_group"
    assert plan.answer_shape.partition_dimensions == ["estado"]
    assert plan.answer_shape.ranked_dimensions == ["diagnostico"]
    assert any(filter_.field == "idade" and filter_.values == ["60"] for filter_ in plan.filters)
    assert not any(filter_.field == "minimum_group_count" for filter_ in plan.filters)


def test_goalv2_validator_rejects_unbounded_grouped_top_n_per_state():
    plan = build_semantic_plan(
        "Quais são os 3 diagnósticos principais mais comuns entre pacientes com mais de 60 anos "
        "no estado de MA e no estado do RS?"
    )
    sql = """
        SELECT mu.estado, c."CD_DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        JOIN cid c ON i."DIAG_PRINC" = c."CID"
        WHERE i."IDADE" > 60 AND mu.estado IN ('MA', 'RS')
        GROUP BY mu.estado, c."CD_DESCRICAO"
        ORDER BY total DESC
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "ROW_NUMBER" in (message or "") or "PARTITION BY" in (message or "")


def test_goalv2_plan_detects_uti_weekday_percentage_distribution():
    plan = build_semantic_plan("Qual a distribuição e percentual de internações em UTI por dia da semana?")

    assert plan.intent == "distribution"
    assert plan.answer_shape.required_dimensions == ["dia_semana"]
    assert "filtered_cohort_percentage_distribution" in plan.constraints
    assert "rate_denominator_must_preserve_full_scope" not in plan.constraints


def test_goalv2_validator_rejects_scalar_uti_percentage_for_weekday_distribution():
    plan = build_semantic_plan("Qual a distribuição e percentual de internações em UTI por dia da semana?")
    sql = """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN "VAL_UTI" > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS percentual
        FROM internacoes
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "dia_semana" in (message or "") or "GROUP BY" in (message or "")


def test_goalv2_plan_detects_side_by_side_state_pivot_for_average_stay():
    plan = build_semantic_plan(
        "Qual a média de dias de internação por especialidade médica, comparando lado a lado os estados MA e RS?"
    )

    assert "side_by_side_state_pivot_required" in plan.constraints
    assert any(metric.name == "media_dias_permanencia" for metric in plan.metrics)
    assert plan.answer_shape.required_dimensions == ["especialidade"]


def test_goalv2_validator_rejects_long_format_for_side_by_side_state_average():
    plan = build_semantic_plan(
        "Qual a média de dias de internação por especialidade médica, comparando lado a lado os estados MA e RS?"
    )
    sql = """
        SELECT e."DESCRICAO", mu.estado, AVG(i."DIAS_PERM") AS media_dias
        FROM internacoes i
        JOIN especialidade e ON i."ESPEC" = e."ESPEC"
        JOIN municipios mu ON i."MUNIC_RES" = mu."codigo_6d"
        WHERE mu.estado IN ('MA', 'RS')
        GROUP BY e."DESCRICAO", mu.estado
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "Side-by-side" in (message or "")
