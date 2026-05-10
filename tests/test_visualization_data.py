from src.visualization.data import build_chart_planning_input, normalize_result_rows


def test_normalize_result_rows_uses_sql_aliases_for_tuple_results():
    rows, columns = normalize_result_rows(
        [{"result": ("Porto Alegre", 10)}],
        'SELECT mu."nome" AS municipio, COUNT(*) AS total_internacoes FROM internacoes i',
    )

    assert columns == ["municipio", "total_internacoes"]
    assert rows == [{"municipio": "Porto Alegre", "total_internacoes": 10}]


def test_build_chart_planning_input_infers_column_types():
    planning_input = build_chart_planning_input(
        user_query="gere grafico",
        sql_query='SELECT ano, COUNT(*) AS total FROM internacoes GROUP BY ano',
        results=[{"result": (2022, 10)}],
        row_count=1,
        chart_hint="line",
    )

    assert planning_input.columns == ["ano", "total"]
    assert planning_input.column_types["ano"] == "temporal"
    assert planning_input.column_types["total"] == "number"


def test_normalize_result_rows_extracts_outer_aliases_from_cte_query():
    rows, columns = normalize_result_rows(
        [{"result": (2021, 22595, 19659)}],
        """
        WITH mortes AS (
            SELECT EXTRACT(YEAR FROM "DT_INTER") AS ano, "SEXO", COUNT(*) AS total_mortes
            FROM internacoes
            GROUP BY ano, "SEXO"
        )
        SELECT ano,
               SUM(CASE WHEN "SEXO" = 1 THEN total_mortes ELSE 0 END) AS total_mortes_homens,
               SUM(CASE WHEN "SEXO" = 3 THEN total_mortes ELSE 0 END) AS total_mortes_mulheres
        FROM mortes
        GROUP BY ano
        """,
    )

    assert columns == ["ano", "total_mortes_homens", "total_mortes_mulheres"]
    assert rows == [
        {
            "ano": 2021,
            "total_mortes_homens": 22595,
            "total_mortes_mulheres": 19659,
        }
    ]
