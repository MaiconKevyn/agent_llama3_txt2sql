from src.semantic.contract_validator import validate_sql_contract
from src.semantic.planner import build_semantic_plan
from src.semantic.sql_ast import parse_sql_ast


def test_sql_ast_extracts_tables_aliases_joins_and_windows():
    sql = """
        SELECT estado, procedimento, total
        FROM (
            SELECT mu."SG_UF", p."NOME_PROC" AS procedimento, COUNT(*) AS total,
                   ROW_NUMBER() OVER (PARTITION BY mu."SG_UF" ORDER BY COUNT(*) DESC) AS rn
            FROM internacoes i
            JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
            JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"
            JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
            GROUP BY mu."SG_UF", p."NOME_PROC"
        ) ranked
        WHERE rn <= 3
    """

    summary = parse_sql_ast(sql)

    assert "internacoes" in summary.tables
    assert summary.aliases["i"] == "internacoes"
    assert any(join.table == "procedimentos" for join in summary.joins)
    assert summary.window_functions[0].partition_by == ['mu."sg_uf"']


def test_sql_ast_does_not_treat_extract_from_as_table_alias():
    sql = """
        SELECT mu."SG_UF", EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*)
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE EXTRACT(YEAR FROM i."DT_INTER") = 2021
        GROUP BY mu."SG_UF", ano
    """

    summary = parse_sql_ast(sql)

    assert summary.aliases["i"] == "internacoes"
    assert "internacoes" in summary.tables
    assert "i" not in summary.tables


def test_contract_validator_accepts_equivalent_aliases_for_mortality_rate():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT m."SG_UF", EXTRACT(YEAR FROM x."DT_INTER") AS ano,
               SUM(CASE WHEN x."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa
        FROM internacoes AS x
        JOIN municipios AS m ON x."MUNIC_RES" = m."CO_MUNICIPIO_6D"
        GROUP BY m."SG_UF", ano
    """

    result = validate_sql_contract(plan, sql)

    assert result.passed, result.errors


def test_contract_validator_rejects_outcome_filter_for_mortality_rate():
    plan = build_semantic_plan("Qual a evolução anual da taxa de mortalidade por estado?")
    sql = """
        SELECT m."SG_UF", EXTRACT(YEAR FROM x."DT_INTER") AS ano,
               COUNT(*) * 100.0 / COUNT(*) AS taxa
        FROM internacoes x
        JOIN municipios m ON x."MUNIC_RES" = m."CO_MUNICIPIO_6D"
        WHERE x."MORTE" = true
        GROUP BY m."SG_UF", ano
    """

    result = validate_sql_contract(plan, sql)

    assert not result.passed
    assert "denominator" in result.errors[0]


def test_contract_validator_rejects_join_outside_catalog_path_for_procedimento():
    plan = build_semantic_plan("Quais são os 5 procedimentos mais comuns para cada sexo?")
    sql = """
        SELECT i."SEXO", p."NOME_PROC", COUNT(*) AS total,
               ROW_NUMBER() OVER (PARTITION BY i."SEXO" ORDER BY COUNT(*) DESC) AS rn
        FROM internacoes i
        JOIN procedimentos p ON i."PROC_REA" = p."PROC_REA"
        GROUP BY i."SEXO", p."NOME_PROC"
    """

    result = validate_sql_contract(plan, sql)

    assert not result.passed
    assert "join path" in result.errors[0]


def test_contract_validator_accepts_procedure_catalog_without_internacoes_join():
    plan = build_semantic_plan("Quais são os 5 procedimentos mais realizados?")
    sql = """
        SELECT p."NOME_PROC" AS procedimento, COUNT(*) AS total
        FROM internacao_procedimento ip
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        GROUP BY p."NOME_PROC"
        ORDER BY total DESC
        LIMIT 5
    """

    result = validate_sql_contract(plan, sql)

    assert result.passed, result.errors


def test_contract_validator_rejects_top_n_per_group_without_partition():
    plan = build_semantic_plan("Quais são os 3 hospitais com maior custo médio de UTI por estado?")
    sql = """
        SELECT mu."SG_UF", i."CNES", AVG(i."VAL_UTI") AS custo
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"
        WHERE i."VAL_UTI" > 0
        GROUP BY mu."SG_UF", i."CNES"
        ORDER BY custo DESC
        LIMIT 3
    """

    result = validate_sql_contract(plan, sql)

    assert not result.passed
    assert "top-N per group" in result.errors[0]


def test_contract_validator_accepts_absence_antijoin_without_group_by():
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

    result = validate_sql_contract(plan, sql)

    assert result.passed, result.errors


def test_contract_validator_accepts_hospital_state_join_path_when_hospital_dimension_present():
    plan = build_semantic_plan("Quais hospitais nunca registraram cobrança de UTI por estado?")
    sql = """
        SELECT mu."SG_UF", h."CNES"
        FROM hospital h
        LEFT JOIN internacoes i
          ON h."CNES" = i."CNES"
         AND i."VAL_UTI" > 0
        JOIN municipios mu
          ON h."MUNIC_MOV" = mu."CO_MUNICIPIO_6D"
        WHERE i."CNES" IS NULL
        GROUP BY mu."SG_UF", h."CNES"
    """

    result = validate_sql_contract(plan, sql)

    assert result.passed, result.errors


def test_contract_validator_accepts_socioeconomico_state_join_path():
    plan = build_semantic_plan("Qual o total de medicos registrados nos estados do MA e RS?")
    sql = """
        SELECT mu."SG_UF", SUM(s."QT_MEDICOS") AS total_medicos
        FROM socioeconomico s
        JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"
        WHERE mu."SG_UF" IN ('MA', 'RS')
        GROUP BY mu."SG_UF"
    """

    result = validate_sql_contract(plan, sql)

    assert result.passed, result.errors
