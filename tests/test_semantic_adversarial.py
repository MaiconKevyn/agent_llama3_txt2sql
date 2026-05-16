"""Benchmark-independent adversarial checks for semantic robustness."""

from src.semantic.planner import build_semantic_plan
from src.semantic.validators import validate_sql_against_semantic_plan


def test_adversarial_top_n_for_each_group_rejects_global_limit():
    plan = build_semantic_plan("Liste os 2 procedimentos mais frequentes para cada sexo.")
    sql = """
        SELECT i."SEXO", p."NOME_PROC", COUNT(*) AS total
        FROM internacoes i
        JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"
        JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"
        GROUP BY i."SEXO", p."NOME_PROC"
        ORDER BY total DESC
        LIMIT 2
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "top-N per group" in (message or "")


def test_adversarial_rate_rejects_outcome_filter_even_with_valid_grouping():
    plan = build_semantic_plan("Mostre a taxa de mortalidade por ano e por estado.")
    sql = """
        SELECT mu."SG_UF", EXTRACT(YEAR FROM i."DT_INTER") AS ano,
               COUNT(*) * 100.0 / COUNT(*) AS taxa
        FROM internacoes i
        JOIN municipios mu ON i."MUNIC_RES" = mu.CO_MUNICIPIO_6D
        WHERE i."MORTE" = true
        GROUP BY mu."SG_UF", ano
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "denominator" in (message or "")


def test_adversarial_absence_rejects_simple_negative_filter():
    plan = build_semantic_plan("Quais hospitais nunca registraram cobranca de UTI?")
    sql = """
        SELECT "CNES", COUNT(*) AS total
        FROM internacoes
        WHERE "VAL_UTI" = 0
        GROUP BY "CNES"
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert not passed
    assert "absence" in (message or "").lower()


def test_adversarial_unknown_bucket_accepts_case_and_left_join():
    plan = build_semantic_plan("Distribua os registros por categoria incluindo sem informação.")
    sql = """
        SELECT
            CASE WHEN c.nome IS NULL THEN 'Sem informação' ELSE c.nome END AS categoria,
            COUNT(*) AS total
        FROM internacoes i
        LEFT JOIN categoria c ON i."RACA_COR" = c.codigo
        GROUP BY categoria
    """

    passed, message = validate_sql_against_semantic_plan(plan, sql)

    assert passed, message
