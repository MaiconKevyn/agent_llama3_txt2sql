import pytest

pytest.importorskip("langgraph")

from src.agent.state_helpers import create_initial_messages_state
from src.agent.state_models import ExecutionPhase


def test_execute_sql_node_blocks_non_select(monkeypatch):
    """execute_sql_node deve bloquear DDL/DML antes de tocar em ferramentas."""
    # Import tardio para permitir monkeypatch de get_llm_manager dentro de nodes
    import src.agent.nodes as nodes

    # Monkeypatch get_llm_manager para não inicializar nada pesado
    class DummyLLMManager:
        pass

    monkeypatch.setattr(nodes, "get_llm_manager", lambda: DummyLLMManager())

    # Criar estado inicial e injetar SQL inválido
    state = create_initial_messages_state(user_query="teste", session_id="s1")
    state["validated_sql"] = "DROP TABLE t;"
    state["current_phase"] = ExecutionPhase.SQL_EXECUTION
    new_state = nodes.execute_sql_node(state)

    # Deve registrar erro e não executar
    assert new_state["current_error"]
    assert any(
        "blocked" in (err.get("message", "").lower()) for err in new_state["errors"]
    ) or "blocked" in (new_state.get("current_error", "").lower())


def test_llm_manager_execute_sql_query_blocks_non_select():
    """OpenAILLMManager.execute_sql_query deve bloquear DDL/DML (sem DB real)."""
    from src.agent.llm_manager import OpenAILLMManager

    # Criar instância sem __init__ para evitar inicialização pesada
    inst = OpenAILLMManager.__new__(OpenAILLMManager)
    # Simular que há um database inicializado (qualquer objeto não-None serve para passar pela checagem)
    inst._sql_database = object()

    result = OpenAILLMManager.execute_sql_query(inst, "UPDATE t SET a=1;")
    assert result["success"] is False
    assert "blocked" in result.get("error", "").lower()


def test_parse_tool_result_rows_expands_stringified_tuple_list():
    from src.agent.execution import _parse_tool_result_rows

    rows = _parse_tool_result_rows("[(2772299, 109261), (2457121, 89982)]")

    assert len(rows) == 2
    assert rows[0]["result"] == (2772299, 109261)


def test_parse_tool_result_rows_keeps_multiline_fallback():
    from src.agent.execution import _parse_tool_result_rows

    rows = _parse_tool_result_rows("first row\nsecond row")

    assert rows == [{"result": "first row"}, {"result": "second row"}]


def test_remove_unrequested_nonzero_metric_filter_preserves_order_by():
    from src.agent.execution import _remove_unrequested_nonzero_metric_filter

    sql = (
        'SELECT tm."SG_UF", tm.ano, tm.taxa '
        "FROM taxa_mortalidade tm "
        "WHERE tm.taxa > 0 "
        'ORDER BY tm."SG_UF", tm.ano;'
    )

    repaired = _remove_unrequested_nonzero_metric_filter(sql)

    assert "taxa > 0" not in repaired
    assert 'ORDER BY tm."SG_UF", tm.ano' in repaired


def test_reorder_top_n_per_group_select_places_group_before_entity():
    from src.agent.execution import _reorder_top_n_per_group_select
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, considerando apenas hospitais com mais de 500 internações na especialidade?"
    )
    sql = (
        'WITH ranked AS (SELECT i."CNES", e."DESCRICAO" AS especialidade, '
        'SUM(i."VAL_TOT") AS receita_total, '
        'ROW_NUMBER() OVER (PARTITION BY e."DESCRICAO" ORDER BY SUM(i."VAL_TOT") DESC) AS rn '
        'FROM internacoes i JOIN especialidade e ON i."ESPEC" = e."ESPEC" '
        'GROUP BY i."CNES", e."DESCRICAO" HAVING COUNT(*) > 500) '
        'SELECT "CNES", especialidade, receita_total FROM ranked WHERE rn = 1;'
    )

    repaired = _reorder_top_n_per_group_select(sql, plan)

    assert 'SELECT especialidade, "CNES", receita_total FROM ranked' in repaired


def test_replace_top1_rank_with_row_number():
    from src.agent.execution import _replace_top1_rank_with_row_number

    sql = 'SELECT RANK() OVER (PARTITION BY e."DESCRICAO" ORDER BY SUM(i."VAL_TOT") DESC) AS rk'

    repaired = _replace_top1_rank_with_row_number(sql)

    assert "ROW_NUMBER() OVER" in repaired
    assert "RANK() OVER" not in repaired


def test_build_filtered_category_period_percentage_sql_from_semantic_plan():
    from src.agent.execution import _build_filtered_category_period_percentage_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual o total e o percentual de internações por doenças respiratórias (CID J%) em cada trimestre do ano no estado do RS?"
    )

    sql = _build_filtered_category_period_percentage_sql(plan)

    assert sql is not None
    assert "i.\"DIAG_PRINC\" LIKE 'J%'" in sql
    assert "mu.\"SG_UF\" = 'RS'" in sql
    assert "SUM(COUNT(*)) OVER ()" in sql
    assert "GROUP BY EXTRACT(QUARTER" in sql


def test_build_temporal_period_comparison_sql_from_semantic_plan():
    from src.agent.execution import _build_temporal_period_comparison_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais são os 10 diagnósticos com maior queda absoluta de internações "
        "entre os períodos 2008-2012 e 2019-2023?"
    )

    sql = _build_temporal_period_comparison_sql(plan)

    assert sql is not None
    assert "WITH periodo_1 AS" in sql
    assert "BETWEEN 2008 AND 2012" in sql
    assert "BETWEEN 2019 AND 2023" in sql
    assert "JOIN periodo_2" in sql
    assert "FULL OUTER JOIN" not in sql
    assert "queda_absoluta" in sql
    assert "p1.total_internacoes - p2.total_internacoes" in sql
    assert "LIMIT 10" in sql


def test_build_death_cause_cid_antijoin_sql_not_used_for_general_death_cause_plan():
    from src.agent.execution import _build_death_cause_cid_antijoin_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais códigos CID aparecem como causa de morte em óbitos registrados mas nunca foram registrados como diagnóstico principal de internação?"
    )

    sql = _build_death_cause_cid_antijoin_sql(plan)

    assert sql is None


def test_build_moving_average_sql_from_semantic_plan():
    from src.agent.execution import _build_moving_average_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual a média móvel de 3 anos de internações no estado do RS por ano (2008-2023)?"
    )

    sql = _build_moving_average_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS total_internacoes" in sql
    assert "mu.\"SG_UF\" = 'RS'" in sql
    assert "BETWEEN 2008 AND 2023" in sql
    assert "AVG(total_internacoes) OVER" in sql
    assert "ROWS BETWEEN 2 PRECEDING AND CURRENT ROW" in sql


def test_build_quartile_distribution_sql_from_semantic_plan():
    from src.agent.execution import _build_quartile_distribution_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Como se distribuem os hospitais em quartis de volume de internações? Mostre o número de hospitais e o intervalo de internações por quartil."
    )

    sql = _build_quartile_distribution_sql(plan)

    assert sql is not None
    assert "NTILE(4) OVER" in sql
    assert 'SELECT "CNES", COUNT(*) AS total_internacoes' in sql
    assert "COUNT(*) AS total_hospitais" in sql
    assert "MIN(total_internacoes)" in sql
    assert "MAX(total_internacoes)" in sql


def test_build_idhm_mortality_cohort_sql_from_semantic_plan():
    from src.agent.execution import _build_idhm_mortality_cohort_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Compare o IDHM médio dos municípios do RS com taxa de mortalidade hospitalar acima e abaixo da média estadual (mínimo de 500 internações)."
    )

    sql = _build_idhm_mortality_cohort_sql(plan)

    assert sql is None
    assert any("unsupported_metric:idhm" in item for item in plan.ambiguities)


def test_build_socioeconomic_multi_metric_sql_from_semantic_plan():
    from src.agent.execution import _build_socioeconomic_multi_metric_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais são os 10 municípios do Maranhão com Bolsa Família acima da média estadual e mortalidade infantil abaixo da média estadual?"
    )

    sql = _build_socioeconomic_multi_metric_sql(plan)

    assert sql is None
    assert any("unsupported_metric:bolsa_familia" in item for item in plan.ambiguities)


def test_build_mortality_rate_time_series_sql_from_semantic_plan():
    from src.agent.execution import _build_mortality_rate_time_series_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado (MA e RS)?")

    sql = _build_mortality_rate_time_series_sql(plan)

    assert sql is not None
    assert "mu.\"SG_UF\" IN ('MA', 'RS')" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") AS ano' in sql
    assert 'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END)' in sql
    assert 'GROUP BY mu."SG_UF", ano' in sql
    assert 'ORDER BY mu."SG_UF", ano' in sql


def test_build_recent_years_mortality_by_sex_sql_from_semantic_plan():
    from src.agent.execution import _build_recent_years_mortality_by_sex_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "gere um grafico comparando morte de homens e mulheres nos ultimos 5 anos"
    )

    sql = _build_recent_years_mortality_by_sex_sql(plan)

    assert sql is not None
    assert 'MAX(EXTRACT(YEAR FROM "DT_INTER")) AS ano_max' in sql
    assert "m.ano_max - 4" in sql
    assert 'i."MORTE" = true' in sql
    assert 'i."SEXO" IN (1, 3)' in sql
    assert "CASE WHEN i.\"SEXO\" = 1 THEN 'homens'" in sql
    assert "COUNT(*) AS total_mortes" in sql
    assert 'GROUP BY EXTRACT(YEAR FROM i."DT_INTER"), i."SEXO"' in sql


def test_build_goalv2_death_cause_description_count_sql():
    from src.agent.execution import _build_death_cause_description_count_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Quantas internações por meningite ocasionaram em morte?")

    sql = _build_death_cause_description_count_sql(plan)

    assert sql is not None
    assert 'i."DIAG_PRINC" = c."CID"' in sql
    assert 'i."MORTE" = true' in sql
    assert "c.\"DESCRICAO\" ILIKE '%meningite%'" in sql
    assert 'i."CID_MORTE"' not in sql


def test_build_death_cause_top_n_sql_uses_diag_princ_with_death_filter():
    from src.agent.execution import _build_death_cause_top_n_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("qual foi o principal motivo de morte em 2021?")

    sql = _build_death_cause_top_n_sql(plan)

    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'i."MORTE" = true' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."DIAG_PRINC" IS NOT NULL' in sql
    assert 'i."CID_MORTE"' not in sql
    assert "ORDER BY total_mortes DESC" in sql
    assert "LIMIT 1" in sql


def test_death_cause_top_n_sql_has_no_fallback_observation_column():
    from src.agent.execution import _build_death_cause_top_n_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("qual foi a principal causa de morte em 2021?")

    sql = _build_death_cause_top_n_sql(plan)

    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'i."MORTE" = true' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert "fallback_observacao" not in sql
    assert "CID_MORTE" not in sql
    assert "ORDER BY total_mortes DESC" in sql
    assert "LIMIT 1" in sql


def test_build_goalv2_top_n_obstetric_municipality_sql():
    from src.agent.execution import _build_top_n_count_by_dimension_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais os cinco municípios com mais internações obstétricas registradas?"
    )

    sql = _build_top_n_count_by_dimension_sql(plan)

    assert sql is not None
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'i."ESPEC" = 2' in sql
    assert "ORDER BY total_internacoes DESC" in sql
    assert "LIMIT 5" in sql


def test_build_goalv2_lookup_distribution_sql_for_race_color():
    from src.agent.execution import _build_lookup_distribution_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Qual a distribuição de internações por raça/cor?")

    sql = _build_lookup_distribution_sql(plan)

    assert sql is not None
    assert 'JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"' in sql
    assert 'r."DESCRICAO" AS raca_cor' in sql
    assert 'GROUP BY r."DESCRICAO"' in sql


def test_build_goalv2_filtered_cohort_weekday_percentage_sql():
    from src.agent.execution import _build_filtered_cohort_weekday_percentage_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual a distribuição e percentual de internações em UTI por dia da semana?"
    )

    sql = _build_filtered_cohort_weekday_percentage_sql(plan)

    assert sql is not None
    assert 'JOIN tempo t ON i."DT_INTER" = t."data"' in sql
    assert 'WHERE i."VAL_UTI" > 0' in sql
    assert "SUM(COUNT(*)) OVER ()" in sql
    assert 'GROUP BY t."dia_semana"' in sql


def test_build_goalv2_top_hospital_revenue_by_specialty_sql():
    from src.agent.execution import _build_top_hospital_revenue_by_specialty_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual o hospital com maior receita total por especialidade médica, "
        "considerando apenas hospitais com mais de 500 internações na especialidade?"
    )

    sql = _build_top_hospital_revenue_by_specialty_sql(plan)

    assert sql is not None
    assert 'e."DESCRICAO" AS especialidade' in sql
    assert 'i."CNES" AS hospital' in sql
    assert 'SUM(i."VAL_TOT") AS receita_total' in sql
    assert 'ROW_NUMBER() OVER (PARTITION BY e."DESCRICAO"' in sql
    assert "HAVING COUNT(*) > 500" in sql
    assert "SELECT especialidade, hospital, receita_total" in sql


def test_build_goalv2_side_by_side_state_average_sql():
    from src.agent.execution import _build_side_by_side_state_average_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual a média de dias de internação por especialidade médica, comparando lado a lado os estados MA e RS?"
    )

    sql = _build_side_by_side_state_average_sql(plan)

    assert sql is not None
    assert 'AVG(CASE WHEN mu."SG_UF" = \'MA\' THEN i."DIAS_PERM" END)' in sql
    assert 'AVG(CASE WHEN mu."SG_UF" = \'RS\' THEN i."DIAS_PERM" END)' in sql
    assert 'GROUP BY e."DESCRICAO"' in sql
    assert 'GROUP BY e."DESCRICAO", mu' not in sql
    assert "total_internacoes" not in sql
    assert " > 0" in sql


def test_build_goalv2_annual_growth_rate_sql_preserves_filters():
    from src.agent.execution import _build_annual_growth_rate_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual o crescimento percentual anual de internações no estado do RS entre 2008 e 2023, "
        "retornando apenas anos com ano anterior disponível?"
    )

    sql = _build_annual_growth_rate_sql(plan)

    assert sql is not None
    assert "mu.\"SG_UF\" = 'RS'" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN 2008 AND 2023' in sql
    assert "LAG(total_internacoes) OVER (ORDER BY ano)" in sql
    assert "WHERE total_anterior IS NOT NULL" in sql


def test_build_goalv2_cost_per_day_hospital_sql():
    from src.agent.execution import _build_cost_per_day_by_hospital_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais são os 5 hospitais mais eficientes em custo por dia de internação "
        "(com mais de 1000 internações)?"
    )

    sql = _build_cost_per_day_by_hospital_sql(plan)

    assert sql is not None
    assert 'SUM(i."VAL_TOT") / NULLIF(SUM(i."DIAS_PERM"), 0)' in sql
    assert "HAVING COUNT(*) > 1000" in sql
    assert "LIMIT 5" in sql


def test_build_goalv2_reference_uti_rate_sql():
    from src.agent.execution import _build_reference_uti_rate_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais são os 10 municípios com mais de 1000 internações que têm taxa de internação em UTI "
        "mais de duas vezes acima da média nacional?"
    )

    sql = _build_reference_uti_rate_sql(plan)

    assert sql is not None
    assert "WITH media_nacional AS" in sql
    assert 'SUM(CASE WHEN "VAL_UTI" > 0 THEN 1 ELSE 0 END)' in sql
    assert 'mu."SG_UF" AS estado' in sql
    assert "AS taxa_uti_local" in sql
    assert "AS taxa_uti_nacional" in sql
    assert "2 * mn.taxa_uti_nacional" in sql
    assert "ORDER BY taxa_uti_local DESC" in sql
    assert "LIMIT 10" in sql


def test_build_goalv2_cumulative_coverage_sql():
    from src.agent.execution import _build_cumulative_coverage_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais procedimentos, ordenados por volume decrescente, cobrem até 80% "
        "do total de atendimentos realizados?"
    )

    sql = _build_cumulative_coverage_sql(plan)

    assert sql is not None
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql
    assert "WHERE pct_acumulado <= 80" in sql


def test_build_goalv2_dual_top_n_intersection_sql():
    from src.agent.execution import _build_dual_top_n_municipality_intersection_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Quais municípios com mais de 500 internações aparecem simultaneamente no top-20 "
        "de volume e no top-20 de taxa de mortalidade nos estados MA e RS?"
    )

    sql = _build_dual_top_n_municipality_intersection_sql(plan)

    assert sql is not None
    assert "WITH top_volume AS" in sql
    assert "top_mortalidade" in sql
    assert "IN (SELECT municipio FROM top_mortalidade)" in sql
