from src.semantic.contracts.candidate_keys import load_candidate_key_registry
from src.semantic.contracts.data_quality import (
    data_quality_caveats_for_sql,
    load_data_quality_registry,
)


def test_candidate_key_registry_loads_single_column_key():
    registry = load_candidate_key_registry()

    key = registry.lookup("internacoes")

    assert key is not None
    assert key.columns == ("N_AIH",)
    assert key.is_confirmed is True
    assert key.is_unique is True
    assert registry.is_candidate_key("internacoes", ["N_AIH"]) is True


def test_candidate_key_registry_loads_composite_key():
    registry = load_candidate_key_registry()

    key = registry.lookup("socioeconomico")

    assert key is not None
    assert key.columns == ("CO_MUNICIPIO_6D", "NU_ANO")
    assert key.is_confirmed is True
    assert registry.is_candidate_key("socioeconomico", ["CO_MUNICIPIO_6D", "NU_ANO"]) is True
    assert registry.is_candidate_key("socioeconomico", ["CO_MUNICIPIO_6D"]) is False


def test_data_quality_registry_loads_blocking_checks():
    registry = load_data_quality_registry()

    check = registry.lookup("DQ010")

    assert check is not None
    assert check.has_findings is True
    assert check.blocks_ground_truth is True
    assert check.severity == "high"
    assert "Municipios orfaos" in check.why_it_matters


def test_data_quality_caveats_match_sql_for_municipio_residencia():
    sql = """
        SELECT m."SG_UF", COUNT(*) AS total
        FROM internacoes i
        JOIN municipios m ON i."MUNIC_RES" = m."CO_MUNICIPIO_6D"
        GROUP BY m."SG_UF"
    """

    caveats = data_quality_caveats_for_sql(sql)
    caveat_text = " ".join(caveats)

    assert "DQ010" in caveat_text
    assert "municipio de residencia sem correspondencia" in caveat_text
    assert "DQ016" in caveat_text
    assert "SG_UF" in caveat_text


def test_data_quality_caveats_do_not_apply_munic_res_check_to_socioeconomic_join():
    sql = """
        SELECT m."SG_UF", AVG(s."VL_LEITOS_SUS_1000") AS valor_indicador
        FROM socioeconomico s
        JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"
        GROUP BY m."SG_UF"
    """

    caveats = data_quality_caveats_for_sql(sql)
    caveat_text = " ".join(caveats)

    assert "DQ010" not in caveat_text
    assert "DQ016" in caveat_text


def test_data_quality_caveats_ignore_checks_without_findings():
    sql = """
        SELECT COUNT(*) AS total
        FROM internacoes
        WHERE VAL_TOT < 0
    """

    caveats = data_quality_caveats_for_sql(sql)

    assert caveats == []
