from src.agent.response import (
    _format_analytic_response_from_package,
    _format_analytic_response_if_available,
)


def test_format_analytic_age_diagnosis_response_uses_structured_package():
    response = _format_analytic_response_from_package(
        "Existe relação entre idade e câncer de próstata?",
        {
            "analysis_type": "age_diagnosis_association",
            "resolved_concept": "C61 - Neopl malig da prostata",
            "total_internacoes": 452111,
            "total_mortes": 40905,
            "idade_media": 68.79,
            "idade_mediana": 69,
            "denominador": "internacoes masculinas",
            "faixas_etarias": "00-39:1449:34082920:4.25:0.32 | 40-49:7055:8649994:81.56:1.56 | 50-59:62684:10146102:617.79:13.86 | 60-69:172335:10411501:1655.21:38.12 | 70-79:147528:8003657:1843.28:32.63 | 80+:61060:4677049:1304.55:13.51",
            "top_idades": "68:24458 | 67:24275 | 69:24131",
            "rate_ratio_maior_igual_50_vs_menor_50": 67.02,
            "rate_ratio_maior_igual_60_vs_menor_60": 12.25,
        },
    )

    assert response.startswith("Sim.")
    assert "C61" in response
    assert "60-69" in response
    assert "67,02x" in response
    assert "associação observada" in response


def test_format_analytic_age_diagnosis_response_includes_age_quality_warning():
    response = _format_analytic_response_from_package(
        "Existe relação entre idade e doenças pulmonares?",
        {
            "analysis_type": "age_diagnosis_association",
            "resolved_concept": "CID J00-J99 - Doencas do aparelho respiratorio",
            "total_internacoes": 19690732,
            "total_mortes": 100,
            "idade_media": 22.1,
            "idade_mediana": 10,
            "denominador": "todas as internacoes",
            "faixas_etarias": "00-39:120:1000:12000:60 | 40-49:10:100:10000:5",
            "top_idades": "0:7207910 | 10:345762 | 11:312945",
            "rate_ratio_maior_igual_50_vs_menor_50": 1.5,
            "rate_ratio_maior_igual_60_vs_menor_60": 2.0,
            "warnings": (
                "data_quality: IDADE=0 contem 5164368 registros com NASC/DT_INTER "
                "indicando 1 ano ou mais"
            ),
        },
    )

    assert "Atenção sobre qualidade dos dados" in response
    assert "IDADE=0 contém 5.164.368 registros" in response


def test_format_analytic_age_diagnosis_response_compacts_long_cid_catalog_labels():
    response = _format_analytic_response_from_package(
        "Existe relacao entre idade e pneumonia nas internacoes?",
        {
            "analysis_type": "age_diagnosis_association",
            "resolved_concept": (
                "A403 - Septicemia p/Streptococcus pneumonia | "
                "B953 - S. pneumoniae causa doenc class outr cap | "
                "J110 - Influenza com pneumonia | J120 - Pneumonia viral"
            ),
            "total_internacoes": 100,
            "total_mortes": 10,
            "idade_media": 40,
            "idade_mediana": 40,
            "denominador": "todas as internacoes",
            "faixas_etarias": "00-39:40:1000:4000:40 | 40-49:60:1000:6000:60",
            "top_idades": "40:10",
            "rate_ratio_maior_igual_50_vs_menor_50": 1.2,
            "rate_ratio_maior_igual_60_vs_menor_60": 1.4,
        },
    )

    assert "catálogo CID" in response
    assert "causa " not in response.lower()


def test_format_categorical_outcome_response_uses_group_distribution():
    response = _format_analytic_response_from_package(
        "Existe diferença de mortalidade entre homens e mulheres?",
        {
            "analysis_type": "categorical_outcome_association",
            "factor_name": "sexo",
            "outcome": "mortalidade hospitalar (MORTE=true)",
            "total_internacoes": 1000,
            "total_mortes": 80,
            "denominador": "internacoes agrupadas por sexo",
            "group_distribution": "Masculino:600:60:10 | Feminino:400:20:5",
            "highest_group": "Masculino",
            "highest_rate": 10,
            "lowest_group": "Feminino",
            "lowest_rate": 5,
            "rate_ratio_highest_vs_lowest": 2,
        },
    )

    assert response.startswith("Sim.")
    assert "Masculino" in response
    assert "Taxa de mortalidade" in response
    assert "2x" in response
    assert "não causalidade" in response


def test_format_analytic_response_maps_tuple_style_columns():
    response = _format_analytic_response_if_available(
        "Existe diferença de mortalidade entre homens e mulheres?",
        [
            {
                "col_1": "categorical_outcome_association",
                "col_2": "sexo",
                "col_3": "mortalidade hospitalar (MORTE=true)",
                "col_4": 1000,
                "col_5": 80,
                "col_6": "internacoes agrupadas por sexo",
                "col_7": "Masculino:600:60:10 | Feminino:400:20:5",
                "col_8": "Masculino",
                "col_9": 10,
                "col_10": "Feminino",
                "col_11": 5,
                "col_12": 2,
                "col_13": None,
            }
        ],
    )

    assert response is not None
    assert response.startswith("Sim.")
    assert "Masculino" in response


def test_format_geographic_condition_response_uses_denominator():
    response = _format_analytic_response_from_package(
        "Compare a taxa de internações por doenças respiratórias por estado.",
        {
            "analysis_type": "geographic_condition_rate",
            "resolved_concept": "CID J00-J99 - Doencas do aparelho respiratorio",
            "total_internacoes": 300,
            "denominador": "internacoes mapeadas por UF de residencia",
            "group_distribution": "RS:200:1000:20000:66.67 | SC:100:1000:10000:33.33",
            "highest_group": "RS",
            "highest_rate": 20000,
            "lowest_group": "SC",
            "lowest_rate": 10000,
            "rate_ratio_highest_vs_lowest": 2,
        },
    )

    assert "Escopo usado" in response
    assert "RS" in response
    assert "Taxa por 100 mil" in response
    assert "2x" in response


def test_format_temporal_condition_response_uses_time_series():
    response = _format_analytic_response_from_package(
        "Qual a tendência anual de doenças respiratórias?",
        {
            "analysis_type": "temporal_condition_trend",
            "resolved_concept": "CID J00-J99 - Doencas do aparelho respiratorio",
            "total_internacoes": 300,
            "denominador": "internacoes por ano no mesmo escopo",
            "time_series": "2020:100:1000:10000 | 2021:200:1000:20000",
            "first_period": 2020,
            "first_total": 100,
            "last_period": 2021,
            "last_total": 200,
            "delta_absolute": 100,
            "delta_percent": 100,
            "peak_period": 2021,
            "peak_total": 200,
        },
    )

    assert "tendência temporal" in response
    assert "2020" in response
    assert "variação absoluta" in response
    assert "100%" in response
