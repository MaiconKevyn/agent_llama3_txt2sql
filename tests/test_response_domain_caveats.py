from src.agent.response import (
    build_data_quality_caveats,
    build_domain_caveats,
    build_join_policy_caveats,
)


def test_domain_caveats_explain_child_and_respiratory_defaults():
    semantic_plan = {
        "filters": [
            {"field": "idade", "values": ["18"], "operator": "<"},
            {"field": "diagnostico_principal_prefix", "values": ["J%"], "operator": "LIKE"},
            {"field": "desfecho", "values": ["MORTE = true"], "operator": "semantic"},
        ]
    }

    caveats = build_domain_caveats(
        user_query="mortes de crianca por causas respiratorias",
        semantic_plan=semantic_plan,
    )

    assert "idade menor que 18 anos" in " ".join(caveats)
    assert "CID J00-J99" in " ".join(caveats)
    assert "MORTE=true" in " ".join(caveats)


def test_join_policy_caveats_explain_mapped_scope_and_low_coverage():
    sql = """
        SELECT m."NO_MUNICIPIO", r."DESCRICAO", COUNT(*) AS total
        FROM internacoes i
        JOIN municipios m ON i."MUNIC_RES" = m."CO_MUNICIPIO_6D"
        JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"
        GROUP BY m."NO_MUNICIPIO", r."DESCRICAO"
    """

    caveats = build_join_policy_caveats(sql)
    caveat_text = " ".join(caveats)

    assert "cobertura imperfeita" in caveat_text
    assert "baixa cobertura" in caveat_text
    assert "internacoes.raca_cor" in caveat_text


def test_data_quality_caveats_explain_generated_contract_findings():
    sql = """
        SELECT m."SG_UF", COUNT(*) AS total
        FROM internacoes i
        JOIN municipios m ON i."MUNIC_RES" = m."CO_MUNICIPIO_6D"
        GROUP BY m."SG_UF"
    """

    caveats = build_data_quality_caveats(sql)
    caveat_text = " ".join(caveats)

    assert "DQ010" in caveat_text
    assert "DQ016" in caveat_text
