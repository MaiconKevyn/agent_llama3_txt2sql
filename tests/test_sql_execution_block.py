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


def test_execution_contract_reuses_select_only_policy():
    from src.agent.execution_contracts import validate_sql_execution_contract

    blocked = validate_sql_execution_contract("DELETE FROM t;")
    allowed = validate_sql_execution_contract("SELECT * FROM t;")

    assert blocked.allowed is False
    assert "blocked" in blocked.error_message.lower()
    assert allowed.allowed is True
    assert allowed.error_message == ""


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


def test_build_age_diagnosis_association_sql_from_semantic_plan():
    from src.agent.analytic_sql import build_age_diagnosis_association_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Existe relação entre idade e câncer de próstata?")

    sql = build_age_diagnosis_association_sql(plan)

    assert sql is not None
    assert "diagnosticos_alvo" in sql
    assert "'C61'" in sql
    assert "faixas_etarias" in sql
    assert "homens" in sql
    assert "rate_ratio_maior_igual_50_vs_menor_50" in sql
    assert "top_idades" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_build_age_diagnosis_association_sql_supports_cid_prefix_and_age_quality_warning():
    from src.agent.analytic_sql import build_age_diagnosis_association_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Existe relação entre idade e doenças pulmonares?")

    sql = build_age_diagnosis_association_sql(plan)

    assert sql is not None
    assert 'SELECT c."CID" FROM cid c WHERE c."CID" LIKE \'J%\'' in sql
    assert "'CID J00-J99 - Doencas do aparelho respiratorio' AS resolved_concept" in sql
    assert 'date_diff(\'day\', "NASC", "DT_INTER") >= 365' in sql
    assert "idade_zero_inconsistente_nasc" in sql
    assert "AS warnings" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_build_age_diagnosis_association_sql_supports_generic_diagnosis_description():
    from src.agent.analytic_sql import build_age_diagnosis_association_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Existe relação entre idade e diabetes?")

    sql = build_age_diagnosis_association_sql(plan)

    assert sql is not None
    assert 'SELECT c."CID" FROM cid c WHERE c."CID" LIKE \'E10%\'' in sql
    assert "c.\"CID\" LIKE 'E14%'" in sql
    assert 'JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"' in sql
    assert "faixas_etarias" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


@pytest.mark.parametrize(
    "question",
    [
        "O que os dados mostram sobre idade e doencas respiratorias?",
        "Compare covid segundo idade, com denominador e caveats.",
        "O que os dados mostram sobre idade e diabetes?",
    ],
)
def test_build_age_diagnosis_association_sql_supports_natural_analysis_phrasings(question):
    from src.agent.analytic_sql import build_age_diagnosis_association_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(question)

    sql = build_age_diagnosis_association_sql(plan)

    assert sql is not None
    assert "'age_diagnosis_association' AS analysis_type" in sql
    assert "taxa_por_100k_denominador" in sql
    assert "rate_ratio_maior_igual_50_vs_menor_50" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_analytic_sql_respects_rollout_flag():
    from src.agent.sql_generation import _build_deterministic_analytic_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Existe relação entre idade e doenças pulmonares?")

    assert (
        _build_deterministic_analytic_sql(plan, {"enable_analytic_response_templates": False})
        is None
    )
    assert _build_deterministic_analytic_sql(plan, {"enable_analytic_response_templates": True})


@pytest.mark.parametrize(
    "question",
    [
        "Qual a relação entre raça/cor e mortalidade?",
        "Qual a relação entre instrução e taxa de mortalidade?",
        "Existe diferença de mortalidade entre homens e mulheres?",
    ],
)
def test_build_categorical_outcome_association_sql_packages(question):
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(question)

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert "'categorical_outcome_association' AS analysis_type" in sql
    assert "taxa_mortalidade_percentual" in sql
    assert "group_distribution" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


@pytest.mark.parametrize(
    "question",
    [
        "Existe relação entre morte por covid e raça/cor?",
        "Existe diferença de mortalidade por coronavirus entre raças/cores?",
    ],
)
def test_categorical_outcome_association_preserves_resolved_clinical_concept(question):
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(question)

    diagnosis_filters = [
        semantic_filter
        for semantic_filter in plan.filters
        if semantic_filter.field == "diagnostico_principal_codigo"
    ]
    assert diagnosis_filters
    assert diagnosis_filters[0].values == ["B342", "B972"]
    assert "raca_cor" in plan.answer_shape.required_dimensions
    assert "categorical_outcome_association_required" in plan.constraints

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert "'B342'" in sql
    assert "'B972'" in sql
    assert 'JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"' in sql
    assert 'i."RACA_COR" IN (1, 2, 3, 4, 5)' in sql
    assert 'SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END)' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


@pytest.mark.parametrize(
    ("question", "expected_prefixes", "dimension_sql"),
    [
        (
            "Existe relação entre morte por dengue e raça/cor?",
            ["A90%", "A91%"],
            'JOIN raca_cor rc ON i."RACA_COR" = rc."RACA_COR"',
        ),
        (
            "Existe relação entre mortalidade por pneumonia e sexo?",
            ["J12%", "J13%", "J14%", "J15%", "J16%", "J17%", "J18%"],
            'CASE WHEN i."SEXO" = 1 THEN',
        ),
        (
            "Óbitos por dengue variam por raça/cor?",
            ["A90%", "A91%"],
            'JOIN raca_cor rc ON i."RACA_COR" = rc."RACA_COR"',
        ),
    ],
)
def test_categorical_outcome_association_preserves_versioned_clinical_condition(
    question,
    expected_prefixes,
    dimension_sql,
):
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(question)

    prefix_filters = [
        semantic_filter
        for semantic_filter in plan.filters
        if semantic_filter.field == "diagnostico_principal_prefix"
    ]
    assert prefix_filters
    assert prefix_filters[0].values == expected_prefixes
    assert "categorical_outcome_association_required" in plan.constraints
    assert "diagnosis_concept_resolution_required" in plan.constraints

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert 'SELECT c."CID" FROM cid c WHERE' in sql
    for prefix in expected_prefixes:
        assert f"c.\"CID\" LIKE '{prefix}'" in sql
    assert 'JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"' in sql
    assert dimension_sql in sql
    assert 'SUM(CASE WHEN "MORTE" = true THEN 1 ELSE 0 END)' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_build_geographic_condition_rate_sql_package():
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Compare a taxa de internações por doenças respiratórias por estado."
    )

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert "'geographic_condition_rate' AS analysis_type" in sql
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert "taxa_por_100k_denominador" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


@pytest.mark.parametrize(
    "question",
    [
        "O que os dados mostram sobre UF de residencia e doencas respiratorias?",
        "Compare covid segundo UF de residencia, com denominador e caveats.",
    ],
)
def test_build_geographic_condition_rate_sql_package_supports_natural_phrasings(question):
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(question)

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert "'geographic_condition_rate' AS analysis_type" in sql
    assert "group_distribution" in sql
    assert "taxa_por_100k_denominador" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_build_temporal_condition_trend_sql_package_resolves_covid():
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual a tendência anual de internações por covid?")

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert "'temporal_condition_trend' AS analysis_type" in sql
    assert "'B342'" in sql
    assert "'B972'" in sql
    assert "time_series" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


@pytest.mark.parametrize(
    "question",
    [
        "O que os dados mostram sobre ano e doencas respiratorias?",
        "Compare doencas respiratorias segundo ano, com denominador e caveats.",
    ],
)
def test_build_temporal_condition_trend_sql_package_supports_natural_phrasings(question):
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(question)

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert "'temporal_condition_trend' AS analysis_type" in sql
    assert "time_series" in sql
    assert "delta_percent" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_temporal_condition_trend_package_does_not_capture_monthly_fixed_year_counts():
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Qual foi a evolucao mensal de internacoes por covid em 2021?")

    assert build_analytic_sql_package(plan) is None


def test_deterministic_grouped_sql_uses_standard_mortality_age_bands():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi a mortalidade por faixa etaria em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert "'00-17'" in sql
    assert "'18-39'" in sql
    assert "'40-59'" in sql
    assert "'60-79'" in sql
    assert "'80+'" in sql
    assert "total_obitos" in sql
    assert "taxa_mortalidade_percentual" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_outputs_hospital_mortality_support_counts():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quais hospitais tiveram maior taxa de mortalidade em 2021 considerando pelo menos 1000 internacoes?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'JOIN hospital h ON i."CNES" = h."CNES"' in sql
    assert 'h."NO_HOSPITAL" AS hospital' in sql
    assert "total_internacoes" in sql
    assert "total_obitos" in sql
    assert "taxa_mortalidade_percentual" in sql
    assert "HAVING COUNT(*) >= 1000" in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_limits_top_diagnosis_death_ranking():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quais diagnosticos principais concentraram mais obitos hospitalares em 2021?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."DESCRICAO" AS diagnostico' in sql
    assert "COUNT(*) AS total_obitos" in sql
    assert 'i."MORTE" = true' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert "ORDER BY total_obitos DESC" in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_uses_cid_chapter_lookup_label():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Quais capitulos CID concentraram mais internacoes em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."DS_CAPITULO" AS capitulo_cid' in sql
    assert "SUBSTR" not in sql.upper()
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'ORDER BY "total_internacoes" DESC' in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_counts_resolved_hypertension_prefix():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Quantas internacoes por hipertensao ocorreram em 2021?")

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."CID" LIKE \'I10%\'' in sql
    assert 'c."CID" LIKE \'I15%\'' in sql
    assert 'c."DESCRICAO" ILIKE' not in sql
    assert "ocorreram" not in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_limits_residence_municipality_rankings():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quais municipios de residencia tiveram mais internacoes em MA em 2020?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'mu."NO_MUNICIPIO" AS municipio_residencia' in sql
    assert "mu.\"SG_UF\" = 'MA'" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2020' in sql
    assert 'ORDER BY "total_internacoes" DESC' in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_limits_health_region_rankings():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Quais regioes de saude de MA tiveram mais internacoes em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'mu."NO_REGIAO_SAUDE" AS "regiao_saude"' in sql
    assert 'mu."NO_MUNICIPIO" AS regiao_saude' not in sql
    assert "mu.\"SG_UF\" = 'MA'" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'ORDER BY "total_internacoes" DESC' in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_build_temporal_condition_trend_sql_package_supports_generic_diagnosis_description():
    from src.agent.analytic_sql import build_analytic_sql_package
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual a tendência anual de internações por dengue?")

    sql = build_analytic_sql_package(plan)

    assert sql is not None
    assert "'temporal_condition_trend' AS analysis_type" in sql
    assert 'SELECT c."CID" FROM cid c WHERE c."CID" LIKE \'A90%\'' in sql
    assert "c.\"CID\" LIKE 'A91%'" in sql
    assert 'JOIN diagnosticos_alvo d ON i."DIAG_PRINC" = d."CID"' in sql
    assert "time_series" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


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


def test_build_goalv2_diagnosis_description_lookup_sql_expands_covid():
    from src.agent.execution import _build_diagnosis_description_lookup_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("tem diagnostico de covid?")

    sql = _build_diagnosis_description_lookup_sql(plan)

    assert sql is not None
    assert "WITH diagnosticos_alvo AS" in sql
    assert "FROM cid c" in sql
    assert "c.\"CID\" IN ('B342', 'B972')" in sql
    assert "FROM internacoes i" in sql
    assert 'i."DIAG_PRINC" IN (SELECT "CID" FROM diagnosticos_alvo)' in sql
    assert "GROUP BY" not in sql
    assert 'i."CID_MORTE"' not in sql
    assert "total_internacoes" in sql


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


def test_deterministic_grouped_sql_lists_death_cause_cid_codes_with_default_top_ten():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quais códigos CID aparecem como diagnóstico principal em óbitos registrados?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'c."CID" AS cid' in sql
    assert 'c."DESCRICAO" AS descricao' in sql
    assert 'i."MORTE" = true' in sql
    assert 'GROUP BY c."CID", c."DESCRICAO"' in sql
    assert "ORDER BY total_mortes DESC" in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


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


def test_build_goalv2_highest_cost_per_day_hospital_sql_orders_desc_and_excludes_zero_days():
    from src.agent.execution import _build_cost_per_day_by_hospital_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Quais são os 5 hospitais com maior custo por dia de internação?")

    sql = _build_cost_per_day_by_hospital_sql(plan)

    assert sql is not None
    assert 'SUM(i."VAL_TOT") / NULLIF(SUM(i."DIAS_PERM"), 0)' in sql
    assert 'SUM(i."DIAS_PERM") > 0' in sql
    assert "ORDER BY custo_por_dia DESC" in sql


def test_build_goalv2_population_rate_by_state_sql_preaggregates_denominator():
    from src.agent.execution import _build_population_rate_by_state_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan(
        "Qual foi a taxa de internações por 100 mil habitantes por estado em 2021?"
    )

    sql = _build_population_rate_by_state_sql(plan)

    assert sql is not None
    assert "internacoes_por_estado AS" in sql
    assert "populacao_por_estado AS" in sql
    assert 'SUM(s."QT_POPULACAO") AS populacao' in sql
    assert 's."NU_ANO" = 2021' in sql
    assert "ipe.total_internacoes * 100000.0 / NULLIF(ppe.populacao, 0)" in sql
    assert "JOIN populacao_por_estado" in sql


def test_build_goalv2_time_to_death_sql_uses_duckdb_date_diff():
    from src.agent.execution import _build_time_to_death_sql
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Qual foi o tempo médio entre internação e óbito em 2021?")

    sql = _build_time_to_death_sql(plan)

    assert sql is not None
    assert "date_diff('day'," in sql
    assert 'i."MORTE" = true' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert "DATE_PART" not in sql


def test_post_execution_contract_rejects_successful_sql_missing_requested_dimension():
    from src.agent.execution import _validate_post_execution_contract
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Qual foi a principal causa de morte por capítulos CID em 2021?")
    sql = """
        SELECT COUNT(*) AS total_mortes
        FROM internacoes i
        WHERE i."MORTE" = true
          AND EXTRACT(YEAR FROM i."DT_INTER") = 2021
    """

    passed, message = _validate_post_execution_contract(
        plan,
        sql,
        results=[{"result": (100,)}],
        row_count=1,
    )

    assert passed is False
    assert "requested output dimension" in (message or "").lower()


def test_post_execution_contract_accepts_health_region_output_dimension():
    from src.agent.execution import _validate_post_execution_contract
    from src.semantic.planner import build_semantic_plan

    plan = build_semantic_plan("Quais regioes de saude de MA tiveram mais internacoes em 2021?")
    sql = """
        SELECT mu."NO_REGIAO_SAUDE" AS regiao_saude,
               COUNT(*) AS total_internacoes
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE mu."SG_UF" = 'MA'
        GROUP BY mu."NO_REGIAO_SAUDE"
    """

    passed, message = _validate_post_execution_contract(
        plan,
        sql,
        results=[{"regiao_saude": "São Luís", "total_internacoes": 82991}],
        row_count=10,
    )

    assert passed is True
    assert message is None


def test_deterministic_grouped_sql_ranks_procedures_with_required_aliases():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Quais foram os procedimentos mais frequentes em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"' in sql
    assert 'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"' in sql
    assert 'p."NOME_PROC" AS "procedimento"' in sql
    assert 'COUNT(*) AS "total_procedimentos"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'ORDER BY "total_procedimentos" DESC' in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_ranks_procedures_inside_diagnosis_description_cohort():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quais procedimentos apareceram com mais frequencia em internacoes por diabetes em 2021?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'p."NOME_PROC" AS "procedimento"' in sql
    assert 'COUNT(*) AS "total_procedimentos"' in sql
    assert 'JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"' in sql
    assert 'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"' in sql
    assert "i.\"DIAG_PRINC\" LIKE 'E10%'" in sql
    assert "i.\"DIAG_PRINC\" LIKE 'E14%'" in sql
    assert 'GROUP BY p."NOME_PROC"' in sql
    assert 'ORDER BY "total_procedimentos" DESC' in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_ranks_procedures_inside_diagnosis_prefix_cohort():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quais procedimentos apareceram com mais frequencia em internacoes por neoplasias em 2021?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'p."NOME_PROC" AS "procedimento"' in sql
    assert 'COUNT(*) AS "total_procedimentos"' in sql
    assert "i.\"DIAG_PRINC\" LIKE 'C%'" in sql
    assert 'GROUP BY p."NOME_PROC"' in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_sums_total_value_by_residence_uf_contract_aliases():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi o valor total de internacoes por UF em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'mu."SG_UF" AS "uf_residencia"' in sql
    assert 'ROUND(SUM(i."VAL_TOT"), 2) AS "valor_total"' in sql
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'GROUP BY mu."SG_UF"' in sql
    assert 'ORDER BY "valor_total" DESC' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_sums_uti_value_by_residence_uf_contract_aliases():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi o valor total de UTI por UF em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'mu."SG_UF" AS "uf_residencia"' in sql
    assert 'ROUND(SUM(i."VAL_UTI"), 2) AS "valor_uti_total"' in sql
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."UTI_INT_TO" IS NOT NULL' not in sql
    assert 'i."MARCA_UTI" IS NOT NULL' not in sql
    assert 'i."VAL_UTI" > 0' not in sql
    assert 'GROUP BY mu."SG_UF"' in sql
    assert 'ORDER BY "valor_uti_total" DESC' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_rates_uti_mortality_by_residence_uf_with_usage_markers():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi a mortalidade em internacoes com UTI por UF em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'mu."SG_UF" AS "uf_residencia"' in sql
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos' in sql
    assert "taxa_mortalidade_percentual" in sql
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0' in sql
    assert 'i."VAL_UTI" > 0' not in sql
    assert 'GROUP BY mu."SG_UF"' in sql
    assert "ORDER BY taxa_mortalidade_percentual DESC" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_distributes_uti_admissions_by_marker_label():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Como as internacoes com UTI se distribuem por marca de UTI em 2021?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'COALESCE(m."DESCRICAO", ' in sql
    assert "AS tipo_uti" in sql
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'LEFT JOIN marca_uti m ON i."MARCA_UTI" = m."MARCA_UTI"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0' in sql
    assert 'i."VAL_UTI" > 0' not in sql
    assert "GROUP BY tipo_uti" in sql
    assert "ORDER BY total_internacoes DESC" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_sums_uti_spending_with_value_alias():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.plan_schema import SemanticFilter
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi o gasto total de UTI em 2021?")
    plan.filters.append(SemanticFilter(field="VAL_UTI", values=["0"], operator="not_equal"))

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert 'ROUND(SUM(i."VAL_UTI"), 2) AS valor_uti_total' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."VAL_UTI" > 0' not in sql
    assert "COUNT(*)" not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_distributes_admissions_by_sex_lookup_label():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Como as internacoes se distribuem por sexo em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 's."DESCRICAO" AS sexo' in sql
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'JOIN sexo s ON i."SEXO" = s."SEXO"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."MORTE" = true' not in sql
    assert 'GROUP BY s."DESCRICAO"' in sql
    assert "ORDER BY total_internacoes DESC" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_distributes_deaths_by_race_color_with_unmapped_bucket():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Como os obitos hospitalares se distribuem por raca/cor informada em 2021?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert "COALESCE" in sql
    assert "'sem raca/cor mapeada'" in sql
    assert "AS raca_cor" in sql
    assert "COUNT(*) AS total_obitos" in sql
    assert 'LEFT JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"' in sql
    assert 'i."MORTE" = true' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."RACA_COR" IN (1, 2, 3, 4, 5)' not in sql
    assert "GROUP BY COALESCE" in sql
    assert "ORDER BY total_obitos DESC" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_reports_instruction_mapping_coverage():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Qual e a cobertura de instrucao preenchida nas internacoes de 2020?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'COUNT(ins."INSTRU") AS com_instrucao_mapeada' in sql
    assert "percentual_mapeado" in sql
    assert 'LEFT JOIN instrucao ins ON i."INSTRU" = ins."INSTRU"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2020' in sql
    assert "GROUP BY" not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_average_age_for_diagnosis_cohort_contract_aliases():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Qual foi a idade media dos pacientes internados por pneumonia em 2021?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'ROUND(AVG(i."IDADE"), 2) AS idade_media' in sql
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."CID" LIKE \'J12%\'' in sql
    assert 'c."CID" LIKE \'J18%\'' in sql
    assert 'c."DESCRICAO" ILIKE' not in sql
    assert 'i."IDADE" IS NOT NULL' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'AVG(i."VAL_TOT")' not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_sums_population_by_uf_contract_aliases():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual era a populacao total por UF em 2019?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'm."SG_UF" AS uf' in sql
    assert 'SUM(s."QT_POPULACAO") AS populacao' in sql
    assert 'JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"' in sql
    assert 's."NU_ANO" = 2019' in sql
    assert 'GROUP BY m."SG_UF"' in sql
    assert "ORDER BY populacao DESC" in sql
    assert "populacao_total" not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_socioeconomic_indicator_by_uf_contract_aliases():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Quais UFs tiveram maior leitos SUS por 1000 habitantes em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'm."SG_UF" AS uf' in sql
    assert 'ROUND(AVG(s."VL_LEITOS_SUS_1000"), 2) AS valor_indicador' in sql
    assert 'JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"' in sql
    assert 's."VL_LEITOS_SUS_1000" IS NOT NULL' not in sql
    assert 's."NU_ANO" = 2021' in sql
    assert 'GROUP BY m."SG_UF"' in sql
    assert "ORDER BY valor_indicador DESC NULLS LAST" in sql
    assert "LIMIT" not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_chart_sql_applies_state_filter_to_monthly_series():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.semantic.planner import build_semantic_plan
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    question = "Como evoluiram mensalmente as internacoes em MA em 2020? Gere um grafico de linha."
    plan = build_semantic_plan(question)
    chart_plan = build_chart_plan(question, detect_visualization_intent(question))

    sql = _build_deterministic_chart_sql(plan, chart_plan)

    assert sql is not None
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert "mu.\"SG_UF\" IN ('MA')" in sql
    assert "i.\"MUNIC_RES\" = 'MA'" not in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2020' in sql
    assert "ORDER BY mes ASC" in sql
    valid, message = validate_sql_against_chart_plan(chart_plan, sql)
    assert valid is True, message


def test_deterministic_chart_sql_uses_socioeconomic_indicator_value_for_uf_chart():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.semantic.planner import build_semantic_plan
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    question = "Quais UFs tiveram maior leitos SUS por 1000 habitantes em 2021? Gere um grafico."
    plan = build_semantic_plan(question)
    chart_plan = build_chart_plan(question, detect_visualization_intent(question))

    sql = _build_deterministic_chart_sql(plan, chart_plan)

    assert sql is not None
    assert 'mu."SG_UF" AS estado' in sql
    assert 'ROUND(AVG(s."VL_LEITOS_SUS_1000"), 2) AS leitos_sus_1000' in sql
    assert 's."NU_ANO" = 2021' in sql
    assert "ORDER BY leitos_sus_1000 DESC" in sql
    valid, message = validate_sql_against_chart_plan(chart_plan, sql)
    assert valid is True, message


def test_deterministic_chart_sql_builds_population_rate_chart_shape():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.semantic.planner import build_semantic_plan
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    question = (
        "Qual foi a taxa de internacoes por 100 mil habitantes por UF em 2019? Gere um grafico."
    )
    plan = build_semantic_plan(question)
    chart_plan = build_chart_plan(question, detect_visualization_intent(question))

    sql = _build_deterministic_chart_sql(plan, chart_plan)

    assert sql is not None
    assert "internacoes_por_estado" in sql
    assert "populacao_por_estado" in sql
    assert "AS taxa_por_100k" in sql
    assert "ORDER BY taxa_por_100k DESC" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2019' in sql
    assert 's."NU_ANO" = 2019' in sql
    valid, message = validate_sql_against_chart_plan(chart_plan, sql)
    assert valid is True, message


def test_deterministic_chart_sql_preserves_missing_race_color_scalar_contract():
    from src.agent.sql_generation import _build_deterministic_chart_sql
    from src.semantic.planner import build_semantic_plan
    from src.visualization.chart_plan import build_chart_plan, validate_sql_against_chart_plan
    from src.visualization.intent import detect_visualization_intent

    question = (
        "Qual percentual dos obitos de 2020 esta sem informacao de raca/cor mapeada? "
        "Gere um grafico."
    )
    plan = build_semantic_plan(question)
    chart_plan = build_chart_plan(question, detect_visualization_intent(question))

    sql = _build_deterministic_chart_sql(plan, chart_plan)

    assert sql is not None
    assert "obitos_sem_raca_cor_mapeada" in sql
    assert "percentual_sem_raca_cor" in sql
    assert 'LEFT JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2020' in sql
    assert chart_plan.expected_result_shape == "single_metric"
    valid, message = validate_sql_against_chart_plan(chart_plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_pib_per_capita_municipality_includes_uf():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Quais municipios tiveram maior PIB per capita em 2019?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'm."NO_MUNICIPIO" AS municipio' in sql
    assert 'm."SG_UF" AS uf' in sql
    assert 'ROUND(s."VL_PIB_PERCAPITA", 2) AS pib_per_capita' in sql
    assert 'JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"' in sql
    assert 's."NU_ANO" = 2019' in sql
    assert "ORDER BY pib_per_capita DESC NULLS LAST" in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_population_rate_by_uf_contract_aliases():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Qual foi a taxa de internacoes por 100 mil habitantes por UF em 2021?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert "internacoes_por_uf AS" in sql
    assert "populacao_por_uf AS" in sql
    assert 'mu."SG_UF" AS uf' in sql
    assert 'm."SG_UF" AS uf' in sql
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'SUM(s."QT_POPULACAO") AS populacao' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 's."NU_ANO" = 2021' in sql
    assert "i.total_internacoes * 100000.0 / NULLIF(p.populacao, 0)" in sql
    assert "AS taxa_por_100k" in sql
    assert "JOIN populacao_por_uf p ON i.uf = p.uf" in sql
    assert "ORDER BY taxa_por_100k DESC" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_counts_missing_primary_diagnosis():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quantas internacoes tiveram diagnostico principal ausente ou em branco em 2021?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS internacoes_sem_diag_princ" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert '(i."DIAG_PRINC" IS NULL OR TRIM(i."DIAG_PRINC") = \'\')' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_counts_primary_diagnosis_without_cid_lookup():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quantos diagnosticos principais de 2021 nao existem no catalogo CID?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS diagnosticos_sem_lookup" in sql
    assert 'LEFT JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."DIAG_PRINC" IS NOT NULL' in sql
    assert 'c."CID" IS NULL' in sql
    assert "ROW_NUMBER" not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_counts_missing_residence_municipality_lookup():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quantas internacoes de 2021 tem municipio de residencia sem cadastro territorial?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS municipios_residencia_sem_lookup" in sql
    assert 'LEFT JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."MUNIC_RES" IS NOT NULL' in sql
    assert 'mu."CO_MUNICIPIO_6D" IS NULL' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_reports_missing_race_color_death_rate():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Qual percentual dos obitos de 2021 esta sem informacao de raca/cor mapeada?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS total_obitos" in sql
    assert "AS obitos_sem_raca_cor_mapeada" in sql
    assert "AS percentual_sem_raca_cor" in sql
    assert 'LEFT JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"' in sql
    assert 'i."MORTE" = true' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'r."RACA_COR" IS NULL' in sql
    assert "DIAG_PRINC" not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_counts_discharge_before_admission_dates():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.plan_schema import SemanticFilter
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Existem internacoes com data de saida anterior a data de entrada em 2021?"
    )
    plan = plan.model_copy(
        update={
            "filters": [
                *plan.filters,
                SemanticFilter(field="DT_SAIDA", values=[], operator="<"),
                SemanticFilter(field="DT_INTER", values=[], operator=">"),
            ]
        }
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS altas_antes_da_internacao" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."DT_SAIDA" < i."DT_INTER"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_SAIDA")' not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_limits_average_stay_by_specialty():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi a permanencia media por especialidade em 2021?")

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'e."DESCRICAO" AS especialidade' in sql
    assert 'ROUND(AVG(i."DIAS_PERM"), 2) AS permanencia_media' in sql
    assert 'JOIN especialidade e ON i."ESPEC" = e."ESPEC"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert "ORDER BY permanencia_media DESC NULLS LAST" in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_counts_uti_usage_with_usage_markers():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Quantas internacoes tiveram uso de UTI em 2019?")

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS internacoes_com_uti" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2019' in sql
    assert 'i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0' in sql
    assert 'i."VAL_UTI" > 0' not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_average_cost_for_diagnosis_cohort_contract_aliases():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi o custo medio de internacao por pneumonia em 2021?")

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'ROUND(AVG(i."VAL_TOT"), 2) AS custo_medio' in sql
    assert 'JOIN cid c ON i."DIAG_PRINC" = c."CID"' in sql
    assert 'c."CID" LIKE \'J12%\'' in sql
    assert 'c."CID" LIKE \'J18%\'' in sql
    assert 'c."DESCRICAO" ILIKE' not in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert "GROUP BY" not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_scalar_sql_average_cost_for_resolved_code_concept_uses_codes_only():
    from src.agent.sql_generation import _build_deterministic_scalar_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan("Qual foi o custo medio de internacao por covid em 2021?")

    sql = _build_deterministic_scalar_sql(plan)

    assert sql is not None
    assert "c.\"CID\" IN ('B342', 'B972')" in sql
    assert 'c."DESCRICAO" ILIKE' not in sql
    assert "COUNT(*) AS total_internacoes" in sql
    assert 'ROUND(AVG(i."VAL_TOT"), 2) AS custo_medio' in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_ranks_hospital_cost_per_day_with_support_columns():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Quais hospitais tiveram maior custo por dia de internacao em 2021 com pelo menos 1000 internacoes?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'h."NO_HOSPITAL" AS hospital' in sql
    assert "COUNT(*) AS total_internacoes" in sql
    assert (
        'ROUND(SUM(i."VAL_TOT") / NULLIF(SUM(i."DIAS_PERM"), 0), 2) AS custo_medio_por_dia' in sql
    )
    assert 'JOIN hospital h ON i."CNES" = h."CNES"' in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2021' in sql
    assert 'i."DIAS_PERM" > 0' in sql
    assert 'GROUP BY h."NO_HOSPITAL"' in sql
    assert "HAVING COUNT(*) >= 1000" in sql
    assert "ORDER BY custo_medio_por_dia DESC NULLS LAST" in sql
    assert "LIMIT 10" in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


def test_deterministic_grouped_sql_filters_procedure_births_by_residence_uf():
    from src.agent.sql_generation import _build_deterministic_grouped_sql
    from src.semantic.planner import build_semantic_plan
    from src.semantic.validators import validate_sql_against_semantic_plan

    plan = build_semantic_plan(
        "Qual foi a quantidade de partos cesareos por UF de residencia em 2022?"
    )

    sql = _build_deterministic_grouped_sql(plan)

    assert sql is not None
    assert 'JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"' in sql
    assert 'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"' in sql
    assert 'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"' in sql
    assert 'mu."SG_UF" AS "uf_residencia"' in sql
    assert 'COUNT(*) AS "total_procedimentos_cesarea"' in sql
    assert "p.\"NOME_PROC\" ILIKE '%CESAR%'" in sql
    assert 'EXTRACT(YEAR FROM i."DT_INTER") = 2022' in sql
    assert 'ORDER BY "total_procedimentos_cesarea" DESC' in sql
    assert 'i."DIAG_PRINC"' not in sql
    assert 'i."ESPEC" = 2' not in sql

    valid, message = validate_sql_against_semantic_plan(plan, sql)
    assert valid is True, message


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
