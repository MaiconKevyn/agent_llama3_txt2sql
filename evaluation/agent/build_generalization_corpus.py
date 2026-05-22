"""Build the canonical generalization exhaustion corpus."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

OUTPUT_PATH = Path(__file__).with_name("generalization_questions.jsonl")

YEARS = [2018, 2019, 2020, 2021, 2022, 2023]
UFS = ["MA", "RS", "SP", "RJ", "BA", "MG", "PR", "PE"]

CONDITIONS = {
    "doencas respiratorias": {
        "sql": 'c."CID" LIKE \'J%\'',
        "family": "condicao_respiratoria",
    },
    "covid": {
        "sql": '(c."CID" IN (\'B342\', \'B972\') OR c."DESCRICAO" ILIKE \'%coronavirus%\')',
        "family": "condicao_covid",
    },
    "diabetes": {
        "sql": 'c."DESCRICAO" ILIKE \'%diabetes%\'',
        "family": "condicao_diabetes",
    },
    "dengue": {
        "sql": 'c."DESCRICAO" ILIKE \'%dengue%\'',
        "family": "condicao_dengue",
    },
    "pneumonia": {
        "sql": 'c."DESCRICAO" ILIKE \'%pneumonia%\'',
        "family": "condicao_pneumonia",
    },
    "neoplasias": {
        "sql": 'c."CID" LIKE \'C%\'',
        "family": "condicao_neoplasias",
    },
    "doencas cardiovasculares": {
        "sql": 'c."CID" LIKE \'I%\'',
        "family": "condicao_cardiovascular",
    },
    "hipertensao": {
        "sql": 'c."DESCRICAO" ILIKE \'%hipertens%\'',
        "family": "condicao_hipertensao",
    },
}


class CorpusBuilder:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    def add(
        self,
        *,
        persona: str,
        category: str,
        difficulty: str,
        question: str,
        expected_behavior: str,
        expected_tables: list[str],
        reference_sql: str | None,
        judge: dict[str, Any],
        schema_basis: list[str],
        anti_overfit_family: str,
    ) -> None:
        item_id = f"GEN{len(self._items) + 1:03d}"
        self._items.append(
            {
                "id": item_id,
                "persona": persona,
                "category": category,
                "difficulty": difficulty,
                "question": question,
                "expected_behavior": expected_behavior,
                "expected_tables": expected_tables,
                "reference_sql": reference_sql,
                "judge": judge,
                "schema_basis": schema_basis,
                "anti_overfit_family": anti_overfit_family,
            }
        )

    @property
    def items(self) -> list[dict[str, Any]]:
        return self._items


def result_judge(columns: list[str], *, tolerance: float = 0.0) -> dict[str, Any]:
    return {"type": "result_equivalence", "required_columns": columns, "tolerance": tolerance}


def unsupported_judge(tokens: list[str]) -> dict[str, Any]:
    return {
        "type": "unsupported_schema",
        "must_mention": tokens,
        "must_not_claim_numeric_answer": True,
    }


def analytic_judge() -> dict[str, Any]:
    return {
        "type": "analytic_response",
        "required": [
            "concept_resolution",
            "denominator_present",
            "group_distribution_present",
            "comparative_metric_present",
            "no_causal_overclaim",
            "no_sample_only",
        ],
    }


def build_corpus() -> list[dict[str, Any]]:
    builder = CorpusBuilder()
    add_volume_temporal(builder)
    add_mortalidade(builder)
    add_diagnosticos(builder)
    add_geografia(builder)
    add_procedimentos(builder)
    add_custos_permanencia(builder)
    add_uti(builder)
    add_perfil_demografico(builder)
    add_socioeconomico(builder)
    add_qualidade_dados(builder)
    add_fora_do_schema(builder)
    add_perguntas_analiticas(builder)
    return builder.items


def add_volume_temporal(builder: CorpusBuilder) -> None:
    for year in YEARS:
        builder.add(
            persona="pessoa_comum",
            category="volume_temporal",
            difficulty="easy",
            question=f"Quantas internacoes foram registradas em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes"],
            reference_sql=(
                'SELECT COUNT(*) AS total_internacoes FROM internacoes i '
                f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year};'
            ),
            judge=result_judge(["total_internacoes"]),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.DT_INTER"],
            anti_overfit_family="volume_anual",
        )
    for year in [2020, 2021]:
        for uf in ["MA", "RS", "SP", "RJ"]:
            builder.add(
                persona="epidemiologista",
                category="volume_temporal",
                difficulty="medium",
                question=f"Como evoluiram mensalmente as internacoes em {uf} em {year}?",
                expected_behavior="answer_with_sql",
                expected_tables=["internacoes", "municipios"],
                reference_sql=(
                    'SELECT EXTRACT(MONTH FROM i."DT_INTER") AS mes, COUNT(*) AS total_internacoes '
                    'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
                    f'WHERE mu."SG_UF" = \'{uf}\' AND EXTRACT(YEAR FROM i."DT_INTER") = {year} '
                    "GROUP BY mes ORDER BY mes;"
                ),
                judge=result_judge(["mes", "total_internacoes"]),
                schema_basis=["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely"],
                anti_overfit_family="serie_mensal_uf",
            )
    for uf in ["MA", "RS", "SP", "RJ"]:
        builder.add(
            persona="epidemiologista",
            category="volume_temporal",
            difficulty="medium",
            question=f"Qual foi a serie anual de internacoes em {uf} de 2018 a 2023?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=(
                'SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano, COUNT(*) AS total_internacoes '
                'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
                f'WHERE mu."SG_UF" = \'{uf}\' AND EXTRACT(YEAR FROM i."DT_INTER") BETWEEN 2018 AND 2023 '
                "GROUP BY ano ORDER BY ano;"
            ),
            judge=result_judge(["ano", "total_internacoes"]),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.DT_INTER"],
            anti_overfit_family="serie_anual_uf",
        )
    for condition in ["doencas respiratorias", "covid", "dengue", "pneumonia"]:
        condition_sql = CONDITIONS[condition]["sql"]
        builder.add(
            persona="medico_pesquisador",
            category="volume_temporal",
            difficulty="hard",
            question=f"Qual foi a evolucao mensal de internacoes por {condition} em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=(
                'SELECT EXTRACT(MONTH FROM i."DT_INTER") AS mes, COUNT(*) AS total_internacoes '
                'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
                f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = 2021 AND {condition_sql} '
                "GROUP BY mes ORDER BY mes;"
            ),
            judge=result_judge(["mes", "total_internacoes"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.DIAG_PRINC->cid.CID confirmed"],
            anti_overfit_family="serie_mensal_condicao",
        )
    assert_category_added(builder, "volume_temporal", 22)


def add_mortalidade(builder: CorpusBuilder) -> None:
    for year in YEARS:
        builder.add(
            persona="epidemiologista",
            category="mortalidade_hospitalar",
            difficulty="medium",
            question=f"Qual foi a taxa de mortalidade hospitalar por UF de residencia em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=mortality_by_uf_sql(year),
            judge=result_judge(
                ["uf_residencia", "total_internacoes", "total_obitos", "taxa_mortalidade_percentual"],
                tolerance=0.01,
            ),
            schema_basis=["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely"],
            anti_overfit_family="mortalidade_por_geografia",
        )
    for year in [2019, 2020, 2021, 2022]:
        builder.add(
            persona="medico_pesquisador",
            category="mortalidade_hospitalar",
            difficulty="medium",
            question=f"Como a mortalidade hospitalar variou por sexo em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "sexo"],
            reference_sql=(
                'SELECT s."DESCRICAO" AS sexo, COUNT(*) AS total_internacoes, '
                'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos, '
                'ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual '
                'FROM internacoes i JOIN sexo s ON i."SEXO" = s."SEXO" '
                f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
                'GROUP BY s."DESCRICAO" ORDER BY taxa_mortalidade_percentual DESC;'
            ),
            judge=result_judge(["sexo", "total_internacoes", "total_obitos", "taxa_mortalidade_percentual"], tolerance=0.01),
            schema_basis=["docs/generated/join_policy.csv:internacoes.SEXO->sexo.SEXO confirmed"],
            anti_overfit_family="mortalidade_por_sexo",
        )
    for year in [2018, 2019, 2020, 2021]:
        builder.add(
            persona="medico_pesquisador",
            category="mortalidade_hospitalar",
            difficulty="hard",
            question=f"Qual foi a mortalidade por faixa etaria em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes"],
            reference_sql=age_band_mortality_sql(year),
            judge=result_judge(["faixa_etaria", "total_internacoes", "total_obitos", "taxa_mortalidade_percentual"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.IDADE,MORTE"],
            anti_overfit_family="mortalidade_faixa_etaria",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="mortalidade_hospitalar",
            difficulty="hard",
            question=f"Quais hospitais tiveram maior taxa de mortalidade em {year} considerando pelo menos 1000 internacoes?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "hospital"],
            reference_sql=hospital_mortality_sql(year),
            judge=result_judge(["hospital", "total_internacoes", "total_obitos", "taxa_mortalidade_percentual"], tolerance=0.01),
            schema_basis=["docs/generated/join_policy.csv:internacoes.CNES->hospital.CNES confirmed"],
            anti_overfit_family="mortalidade_hospital_minimo",
        )
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="medico_pesquisador",
            category="mortalidade_hospitalar",
            difficulty="medium",
            question=f"Quais diagnosticos principais concentraram mais obitos hospitalares em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=top_death_diagnoses_sql(year),
            judge=result_judge(["diagnostico", "total_obitos"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.DIAG_PRINC->cid.CID confirmed"],
            anti_overfit_family="obitos_por_diagnostico_principal",
        )
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="epidemiologista",
            category="mortalidade_hospitalar",
            difficulty="hard",
            question=f"Compare a taxa de mortalidade hospitalar entre MA e RS em {year}.",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=mortality_compare_uf_sql(year, ["MA", "RS"]),
            judge=result_judge(["uf_residencia", "total_internacoes", "total_obitos", "taxa_mortalidade_percentual"], tolerance=0.01),
            schema_basis=["historical failure: comparacao MA vs RS exige GROUP BY"],
            anti_overfit_family="comparacao_geografica_dupla",
        )
    assert_category_added(builder, "mortalidade_hospitalar", 28)


def add_diagnosticos(builder: CorpusBuilder) -> None:
    for year in YEARS:
        builder.add(
            persona="medico_pesquisador",
            category="diagnosticos_cid",
            difficulty="medium",
            question=f"Quais foram os 10 diagnosticos principais mais frequentes em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=top_diagnoses_sql(year),
            judge=result_judge(["diagnostico", "total_internacoes"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.DIAG_PRINC->cid.CID confirmed"],
            anti_overfit_family="diagnostico_principal_ranking",
        )
    for year in YEARS:
        builder.add(
            persona="epidemiologista",
            category="diagnosticos_cid",
            difficulty="medium",
            question=f"Quais capitulos CID concentraram mais internacoes em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=cid_chapters_sql(year),
            judge=result_judge(["capitulo_cid", "total_internacoes"]),
            schema_basis=["docs/generated/table_metadata.csv:cid.DS_CAPITULO"],
            anti_overfit_family="cid_capitulo_ranking",
        )
    for year in [2020, 2021]:
        for uf in ["MA", "RS", "SP", "RJ"]:
            builder.add(
                persona="medico_pesquisador",
                category="diagnosticos_cid",
                difficulty="hard",
                question=f"Quais diagnosticos principais foram mais frequentes em {uf} em {year}?",
                expected_behavior="answer_with_sql",
                expected_tables=["internacoes", "cid", "municipios"],
                reference_sql=top_diagnoses_by_uf_sql(year, uf),
                judge=result_judge(["diagnostico", "total_internacoes"]),
                schema_basis=["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely"],
                anti_overfit_family="diagnostico_por_uf",
            )
    for condition in list(CONDITIONS)[:8]:
        condition_sql = CONDITIONS[condition]["sql"]
        builder.add(
            persona="pessoa_comum",
            category="diagnosticos_cid",
            difficulty="medium",
            question=f"Quantas internacoes por {condition} ocorreram em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=(
                'SELECT COUNT(*) AS total_internacoes FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
                f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = 2021 AND {condition_sql};'
            ),
            judge=result_judge(["total_internacoes"]),
            schema_basis=["docs/generated/table_metadata.csv:cid.CID,DESCRICAO"],
            anti_overfit_family=str(CONDITIONS[condition]["family"]),
        )
    assert_category_added(builder, "diagnosticos_cid", 28)


def add_geografia(builder: CorpusBuilder) -> None:
    for year in [2020, 2021]:
        for uf in ["MA", "RS", "SP", "RJ"]:
            builder.add(
                persona="gestor_hospitalar",
                category="geografia",
                difficulty="medium",
                question=f"Quais municipios de residencia tiveram mais internacoes em {uf} em {year}?",
                expected_behavior="answer_with_sql",
                expected_tables=["internacoes", "municipios"],
                reference_sql=top_municipios_sql(year, uf),
                judge=result_judge(["municipio_residencia", "total_internacoes"]),
                schema_basis=["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely"],
                anti_overfit_family="municipios_residencia_top",
            )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="epidemiologista",
            category="geografia",
            difficulty="hard",
            question=f"Quantas internacoes ocorreram fora da UF de residencia do paciente em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "hospital", "municipios"],
            reference_sql=out_of_state_sql(year),
            judge=result_judge(["internacoes_fora_uf_residencia"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.CNES->hospital.CNES confirmed"],
            anti_overfit_family="internacao_fora_uf_residencia",
        )
    for uf in ["MA", "RS", "SP", "RJ", "BA"]:
        builder.add(
            persona="gestor_hospitalar",
            category="geografia",
            difficulty="medium",
            question=f"Quais regioes de saude de {uf} tiveram mais internacoes em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=region_health_sql(2021, uf),
            judge=result_judge(["regiao_saude", "total_internacoes"]),
            schema_basis=["docs/generated/table_metadata.csv:municipios.NO_REGIAO_SAUDE"],
            anti_overfit_family="regiao_saude_volume",
        )
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="pessoa_comum",
            category="geografia",
            difficulty="medium",
            question=f"Quais UFs tiveram mais internacoes em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=top_uf_volume_sql(year),
            judge=result_judge(["uf_residencia", "total_internacoes"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely"],
            anti_overfit_family="uf_volume_top",
        )
    assert_category_added(builder, "geografia", 22)


def add_procedimentos(builder: CorpusBuilder) -> None:
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="procedimentos",
            difficulty="medium",
            question=f"Quais foram os procedimentos mais frequentes em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacao_procedimento", "procedimentos"],
            reference_sql=top_procedures_sql(year),
            judge=result_judge(["procedimento", "total_procedimentos"]),
            schema_basis=["docs/generated/table_metadata.csv:procedimentos.NOME_PROC"],
            anti_overfit_family="procedimento_ranking",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="procedimentos",
            difficulty="hard",
            question=f"Qual foi a quantidade de partos cesareos por UF de residencia em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "internacao_procedimento", "procedimentos", "municipios"],
            reference_sql=cesarean_by_uf_sql(year),
            judge=result_judge(["uf_residencia", "total_procedimentos_cesarea"]),
            schema_basis=["historical failure: cesarea deve usar procedimentos, nao DIAG_PRINC"],
            anti_overfit_family="procedimento_obstetrico",
        )
    for uf in ["MA", "RS", "SP", "RJ"]:
        builder.add(
            persona="gestor_hospitalar",
            category="procedimentos",
            difficulty="hard",
            question=f"Quais procedimentos foram mais frequentes em {uf} em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "internacao_procedimento", "procedimentos", "municipios"],
            reference_sql=top_procedures_by_uf_sql(2021, uf),
            judge=result_judge(["procedimento", "total_procedimentos"]),
            schema_basis=["docs/generated/join_policy.csv:internacao_procedimento.N_AIH->internacoes.N_AIH confirmed"],
            anti_overfit_family="procedimento_por_uf",
        )
    for condition in ["doencas respiratorias", "diabetes", "pneumonia", "neoplasias"]:
        builder.add(
            persona="medico_pesquisador",
            category="procedimentos",
            difficulty="hard",
            question=f"Quais procedimentos apareceram com mais frequencia em internacoes por {condition} em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "internacao_procedimento", "procedimentos", "cid"],
            reference_sql=top_procedures_by_condition_sql(2021, CONDITIONS[condition]["sql"]),
            judge=result_judge(["procedimento", "total_procedimentos"]),
            schema_basis=["docs/generated/table_metadata.csv:internacao_procedimento.N_AIH,PROC_REA"],
            anti_overfit_family="procedimento_por_condicao",
        )
    assert_category_added(builder, "procedimentos", 17)


def add_custos_permanencia(builder: CorpusBuilder) -> None:
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="custos_permanencia",
            difficulty="medium",
            question=f"Qual foi o valor total de internacoes por UF em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=cost_by_uf_sql(year),
            judge=result_judge(["uf_residencia", "valor_total"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.VAL_TOT"],
            anti_overfit_family="custo_total_uf",
        )
    for condition in ["doencas respiratorias", "covid", "diabetes", "pneumonia", "neoplasias"]:
        builder.add(
            persona="medico_pesquisador",
            category="custos_permanencia",
            difficulty="hard",
            question=f"Qual foi o custo medio de internacao por {condition} em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=avg_cost_condition_sql(2021, CONDITIONS[condition]["sql"]),
            judge=result_judge(["total_internacoes", "custo_medio"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.VAL_TOT"],
            anti_overfit_family="custo_medio_condicao",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="custos_permanencia",
            difficulty="hard",
            question=f"Quais hospitais tiveram maior custo por dia de internacao em {year} com pelo menos 1000 internacoes?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "hospital"],
            reference_sql=hospital_cost_per_day_sql(year),
            judge=result_judge(["hospital", "total_internacoes", "custo_medio_por_dia"], tolerance=0.01),
            schema_basis=["historical failure: ordenar NULLS LAST e exigir DIAS_PERM > 0"],
            anti_overfit_family="custo_por_dia_hospital",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="custos_permanencia",
            difficulty="medium",
            question=f"Qual foi o valor total de UTI por UF em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=uti_cost_by_uf_sql(year),
            judge=result_judge(["uf_residencia", "valor_uti_total"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.VAL_UTI"],
            anti_overfit_family="custo_uti_uf",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="custos_permanencia",
            difficulty="medium",
            question=f"Qual foi a permanencia media por especialidade em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "especialidade"],
            reference_sql=avg_stay_by_specialty_sql(year),
            judge=result_judge(["especialidade", "permanencia_media"], tolerance=0.01),
            schema_basis=["docs/generated/join_policy.csv:internacoes.ESPEC->especialidade.ESPEC confirmed"],
            anti_overfit_family="permanencia_especialidade",
        )
    assert_category_added(builder, "custos_permanencia", 22)


def add_uti(builder: CorpusBuilder) -> None:
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="pessoa_comum",
            category="uti",
            difficulty="easy",
            question=f"Quantas internacoes tiveram uso de UTI em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes"],
            reference_sql=uti_count_sql(year),
            judge=result_judge(["internacoes_com_uti"]),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.MARCA_UTI,UTI_INT_TO"],
            anti_overfit_family="uso_uti_volume",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="medico_pesquisador",
            category="uti",
            difficulty="hard",
            question=f"Qual foi a mortalidade em internacoes com UTI por UF em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=uti_mortality_by_uf_sql(year),
            judge=result_judge(["uf_residencia", "total_internacoes", "total_obitos", "taxa_mortalidade_percentual"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.MORTE,MARCA_UTI,UTI_INT_TO"],
            anti_overfit_family="mortalidade_uti_geografia",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="uti",
            difficulty="medium",
            question=f"Como as internacoes com UTI se distribuem por marca de UTI em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "marca_uti"],
            reference_sql=uti_brand_distribution_sql(year),
            judge=result_judge(["tipo_uti", "total_internacoes"]),
            schema_basis=["docs/generated/table_metadata.csv:marca_uti"],
            anti_overfit_family="marca_uti_distribuicao",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="gestor_hospitalar",
            category="uti",
            difficulty="medium",
            question=f"Qual foi o gasto total de UTI em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes"],
            reference_sql=(
                'SELECT ROUND(SUM(i."VAL_UTI"), 2) AS valor_uti_total FROM internacoes i '
                f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year};'
            ),
            judge=result_judge(["valor_uti_total"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.VAL_UTI"],
            anti_overfit_family="custo_uti_total",
        )
    assert_category_added(builder, "uti", 17)


def add_perfil_demografico(builder: CorpusBuilder) -> None:
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="pessoa_comum",
            category="perfil_demografico",
            difficulty="medium",
            question=f"Como as internacoes se distribuem por sexo em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "sexo"],
            reference_sql=sex_distribution_sql(year),
            judge=result_judge(["sexo", "total_internacoes"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.SEXO->sexo.SEXO confirmed"],
            anti_overfit_family="perfil_sexo",
        )
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="medico_pesquisador",
            category="perfil_demografico",
            difficulty="hard",
            question=f"Qual foi a mortalidade por faixa etaria em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes"],
            reference_sql=age_band_mortality_sql(year),
            judge=result_judge(["faixa_etaria", "total_internacoes", "total_obitos", "taxa_mortalidade_percentual"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.IDADE"],
            anti_overfit_family="perfil_faixa_etaria",
        )
    for year in [2019, 2020, 2021, 2022, 2023]:
        builder.add(
            persona="auditor_dados",
            category="perfil_demografico",
            difficulty="medium",
            question=f"Como os obitos hospitalares se distribuem por raca/cor informada em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "raca_cor"],
            reference_sql=race_death_distribution_sql(year),
            judge=result_judge(["raca_cor", "total_obitos"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.RACA_COR->raca_cor.RACA_COR rejected audit_only"],
            anti_overfit_family="perfil_raca_cor_caveat",
        )
    for year in [2020, 2021, 2022, 2023]:
        builder.add(
            persona="auditor_dados",
            category="perfil_demografico",
            difficulty="medium",
            question=f"Qual e a cobertura de instrucao preenchida nas internacoes de {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "instrucao"],
            reference_sql=education_coverage_sql(year),
            judge=result_judge(["total_internacoes", "com_instrucao_mapeada", "percentual_mapeado"], tolerance=0.01),
            schema_basis=["docs/generated/join_policy.csv:internacoes.INSTRU->instrucao.INSTRU rejected audit_only"],
            anti_overfit_family="perfil_instrucao_caveat",
        )
    for condition in ["doencas respiratorias", "covid", "diabetes", "pneumonia"]:
        builder.add(
            persona="medico_pesquisador",
            category="perfil_demografico",
            difficulty="medium",
            question=f"Qual foi a idade media dos pacientes internados por {condition} em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=avg_age_condition_sql(2021, CONDITIONS[condition]["sql"]),
            judge=result_judge(["total_internacoes", "idade_media"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:internacoes.IDADE"],
            anti_overfit_family="idade_media_condicao",
        )
    assert_category_added(builder, "perfil_demografico", 22)


def add_socioeconomico(builder: CorpusBuilder) -> None:
    for year in [2019, 2020, 2021, 2022]:
        builder.add(
            persona="epidemiologista",
            category="socioeconomico_populacao",
            difficulty="medium",
            question=f"Qual era a populacao total por UF em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["socioeconomico", "municipios"],
            reference_sql=population_by_uf_sql(year),
            judge=result_judge(["uf", "populacao"]),
            schema_basis=["docs/generated/table_metadata.csv:socioeconomico.QT_POPULACAO"],
            anti_overfit_family="populacao_uf",
        )
    for metric_name, column in [
        ("leitos SUS por 1000 habitantes", "VL_LEITOS_SUS_1000"),
        ("medicos por 1000 habitantes", "VL_MEDICOS_1000"),
        ("total de leitos SUS", "QT_LEITOS_SUS"),
        ("total de medicos", "QT_MEDICOS"),
    ]:
        builder.add(
            persona="gestor_hospitalar",
            category="socioeconomico_populacao",
            difficulty="medium",
            question=f"Quais UFs tiveram maior {metric_name} em 2021?",
            expected_behavior="answer_with_sql",
            expected_tables=["socioeconomico", "municipios"],
            reference_sql=socio_metric_by_uf_sql(2021, column, metric_name),
            judge=result_judge(["uf", "valor_indicador"], tolerance=0.01),
            schema_basis=[f"docs/generated/table_metadata.csv:socioeconomico.{column}"],
            anti_overfit_family="socioeconomico_indicador_uf",
        )
    for year in [2019, 2020, 2021]:
        builder.add(
            persona="epidemiologista",
            category="socioeconomico_populacao",
            difficulty="hard",
            question=f"Quais municipios tiveram maior PIB per capita em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["socioeconomico", "municipios"],
            reference_sql=pib_municipios_sql(year),
            judge=result_judge(["municipio", "uf", "pib_per_capita"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:socioeconomico.VL_PIB_PERCAPITA"],
            anti_overfit_family="pib_per_capita_municipio",
        )
    for year in [2019, 2020, 2021]:
        builder.add(
            persona="epidemiologista",
            category="socioeconomico_populacao",
            difficulty="medium",
            question=f"Qual foi a mortalidade infantil socioeconomica media por UF em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["socioeconomico", "municipios"],
            reference_sql=infant_mortality_socio_by_uf_sql(year),
            judge=result_judge(["uf", "mortalidade_infantil_media"], tolerance=0.01),
            schema_basis=["docs/generated/table_metadata.csv:socioeconomico.VL_MORT_INFANTIL"],
            anti_overfit_family="mortalidade_infantil_socioeconomica",
        )
    for year in [2019, 2020, 2021]:
        builder.add(
            persona="epidemiologista",
            category="socioeconomico_populacao",
            difficulty="hard",
            question=f"Qual foi a taxa de internacoes por 100 mil habitantes por UF em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios", "socioeconomico"],
            reference_sql=hospitalization_rate_population_sql(year),
            judge=result_judge(["uf", "total_internacoes", "populacao", "taxa_por_100k"], tolerance=0.01),
            schema_basis=["historical failure: denominador populacional agregado antes do join com fatos"],
            anti_overfit_family="taxa_populacional",
        )
    assert_category_added(builder, "socioeconomico_populacao", 17)


def add_qualidade_dados(builder: CorpusBuilder) -> None:
    for year in [2020, 2021, 2022]:
        builder.add(
            persona="auditor_dados",
            category="qualidade_dados",
            difficulty="easy",
            question=f"Quantas internacoes tiveram diagnostico principal ausente ou em branco em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes"],
            reference_sql=missing_diag_sql(year),
            judge=result_judge(["internacoes_sem_diag_princ"]),
            schema_basis=["historical failure: sem preenchimento nao e o mesmo que CID sem lookup"],
            anti_overfit_family="nulidade_diagnostico",
        )
    for year in [2020, 2021, 2022]:
        builder.add(
            persona="auditor_dados",
            category="qualidade_dados",
            difficulty="medium",
            question=f"Quantos diagnosticos principais de {year} nao existem no catalogo CID?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "cid"],
            reference_sql=unmatched_cid_sql(year),
            judge=result_judge(["diagnosticos_sem_lookup"]),
            schema_basis=["docs/generated/ground_truth_semantic_audit.csv:DIAG_PRINC lookup"],
            anti_overfit_family="lookup_cid_incompleto",
        )
    for year in [2020, 2021, 2022]:
        builder.add(
            persona="auditor_dados",
            category="qualidade_dados",
            difficulty="medium",
            question=f"Quantas internacoes de {year} tem municipio de residencia sem cadastro territorial?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "municipios"],
            reference_sql=unmatched_municipio_sql(year),
            judge=result_judge(["municipios_residencia_sem_lookup"]),
            schema_basis=["docs/generated/join_policy.csv:internacoes.MUNIC_RES->municipios.CO_MUNICIPIO_6D likely"],
            anti_overfit_family="lookup_municipio_incompleto",
        )
    for year in [2020, 2021, 2022]:
        builder.add(
            persona="auditor_dados",
            category="qualidade_dados",
            difficulty="medium",
            question=f"Qual percentual dos obitos de {year} esta sem informacao de raca/cor mapeada?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes", "raca_cor"],
            reference_sql=race_missing_deaths_sql(year),
            judge=result_judge(["total_obitos", "obitos_sem_raca_cor_mapeada", "percentual_sem_raca_cor"], tolerance=0.01),
            schema_basis=["docs/generated/join_policy.csv:internacoes.RACA_COR->raca_cor.RACA_COR rejected audit_only"],
            anti_overfit_family="qualidade_raca_cor",
        )
    for year in [2020, 2021, 2022]:
        builder.add(
            persona="auditor_dados",
            category="qualidade_dados",
            difficulty="easy",
            question=f"Existem internacoes com data de saida anterior a data de entrada em {year}?",
            expected_behavior="answer_with_sql",
            expected_tables=["internacoes"],
            reference_sql=invalid_dates_sql(year),
            judge=result_judge(["altas_antes_da_internacao"]),
            schema_basis=["docs/generated/data_quality_checks.json:DQ001"],
            anti_overfit_family="qualidade_datas_internacao",
        )
    assert_category_added(builder, "qualidade_dados", 15)


def add_fora_do_schema(builder: CorpusBuilder) -> None:
    unsupported_cases = [
        ("antibioticos", ["medicamentos", "nao esta disponivel"], "medicamentos_inexistentes"),
        ("medicamentos de uso continuo", ["medicamentos", "nao esta disponivel"], "medicamentos_inexistentes"),
        ("exames laboratoriais", ["exames", "nao esta disponivel"], "exames_laboratoriais_inexistentes"),
        ("resultado de hemograma", ["laboratoriais", "nao esta disponivel"], "exames_laboratoriais_inexistentes"),
        ("cobertura vacinal", ["vacinacao", "nao esta disponivel"], "vacinacao_inexistente"),
        ("dose de vacina", ["vacinacao", "nao esta disponivel"], "vacinacao_inexistente"),
        ("zona rural ou urbana", ["rural", "nao esta disponivel"], "area_rural_urbana_inexistente"),
        ("bairro de residencia", ["bairro", "nao esta disponivel"], "bairro_inexistente"),
        ("renda individual do paciente", ["renda", "nao esta disponivel"], "renda_individual_inexistente"),
        ("plano de saude do paciente", ["plano", "nao esta disponivel"], "plano_saude_inexistente"),
        ("readmissao em 30 dias", ["identificador longitudinal", "nao esta disponivel"], "seguimento_longitudinal_inexistente"),
        ("sobrevida um ano apos alta", ["seguimento", "nao esta disponivel"], "seguimento_pos_alta_inexistente"),
        ("tempo ate consulta ambulatorial", ["ambulatorial", "nao esta disponivel"], "ambulatorio_inexistente"),
        ("resultado de imagem", ["imagem", "nao esta disponivel"], "imagem_inexistente"),
        ("pressao arterial na admissao", ["sinais vitais", "nao esta disponivel"], "sinais_vitais_inexistentes"),
    ]
    phrasings = [
        "Quais {concept} aparecem com maior frequencia nas internacoes por pneumonia?",
        "Qual foi a taxa relacionada a {concept} entre pacientes que morreram por covid?",
        "Compare {concept} entre MA e RS nas internacoes de 2021.",
        "Existe relacao entre {concept} e mortalidade hospitalar?",
    ]
    for concept, tokens, family in unsupported_cases:
        for phrasing in phrasings:
            builder.add(
                persona="pessoa_comum",
                category="fora_do_schema",
                difficulty="easy" if len(builder.items) % 2 == 0 else "medium",
                question=phrasing.format(concept=concept),
                expected_behavior="safe_refusal",
                expected_tables=[],
                reference_sql=None,
                judge=unsupported_judge(tokens),
                schema_basis=["docs/generated/column_catalog.csv nao contem este dado solicitado"],
                anti_overfit_family=family,
            )
    assert_category_added(builder, "fora_do_schema", 60)


def add_perguntas_analiticas(builder: CorpusBuilder) -> None:
    analytic_questions = [
        ("idade", "doencas respiratorias", "idade_condicao_respiratoria"),
        ("idade", "covid", "idade_condicao_covid"),
        ("idade", "diabetes", "idade_condicao_diabetes"),
        ("idade", "pneumonia", "idade_condicao_pneumonia"),
        ("sexo", "mortalidade hospitalar", "sexo_mortalidade"),
        ("raca/cor", "mortalidade hospitalar", "raca_mortalidade_caveat"),
        ("instrucao", "mortalidade hospitalar", "instrucao_mortalidade_caveat"),
        ("UF de residencia", "doencas respiratorias", "geografia_condicao_respiratoria"),
        ("UF de residencia", "covid", "geografia_condicao_covid"),
        ("ano", "doencas respiratorias", "tendencia_condicao_respiratoria"),
    ]
    phrasings = [
        "Existe relacao entre {factor} e {outcome} nas internacoes?",
        "O que os dados mostram sobre {factor} e {outcome}?",
        "Compare {outcome} segundo {factor}, com denominador e caveats.",
    ]
    for factor, outcome, family in analytic_questions:
        for phrasing in phrasings:
            builder.add(
                persona="medico_pesquisador",
                category="pergunta_cientifica_associativa",
                difficulty="hard",
                question=phrasing.format(factor=factor, outcome=outcome),
                expected_behavior="answer_with_analytic_template",
                expected_tables=["internacoes"],
                reference_sql=None,
                judge=analytic_judge(),
                schema_basis=["src/semantic/analytic_templates.py:analytic response requires denominator and no causal overclaim"],
                anti_overfit_family=family,
            )
    assert_category_added(builder, "pergunta_cientifica_associativa", 30)


def mortality_by_uf_sql(year: int) -> str:
    return (
        'SELECT mu."SG_UF" AS uf_residencia, COUNT(*) AS total_internacoes, '
        'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos, '
        'ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY mu."SG_UF" ORDER BY taxa_mortalidade_percentual DESC;'
    )


def mortality_compare_uf_sql(year: int, ufs: list[str]) -> str:
    quoted = ", ".join(f"'{uf}'" for uf in ufs)
    return mortality_by_uf_sql(year).replace(
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} ',
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND mu."SG_UF" IN ({quoted}) ',
    ).replace("ORDER BY taxa_mortalidade_percentual DESC", "ORDER BY uf_residencia")


def age_band_mortality_sql(year: int) -> str:
    return (
        'SELECT CASE WHEN i."IDADE" < 18 THEN \'00-17\' WHEN i."IDADE" BETWEEN 18 AND 39 THEN \'18-39\' '
        'WHEN i."IDADE" BETWEEN 40 AND 59 THEN \'40-59\' WHEN i."IDADE" BETWEEN 60 AND 79 THEN \'60-79\' ELSE \'80+\' END AS faixa_etaria, '
        'COUNT(*) AS total_internacoes, SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos, '
        'ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual '
        f'FROM internacoes i WHERE i."IDADE" IS NOT NULL AND EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        "GROUP BY faixa_etaria ORDER BY faixa_etaria;"
    )


def hospital_mortality_sql(year: int) -> str:
    return (
        'SELECT h."NO_HOSPITAL" AS hospital, COUNT(*) AS total_internacoes, '
        'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos, '
        'ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual '
        'FROM internacoes i JOIN hospital h ON i."CNES" = h."CNES" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY h."NO_HOSPITAL" HAVING COUNT(*) >= 1000 ORDER BY taxa_mortalidade_percentual DESC LIMIT 10;'
    )


def top_death_diagnoses_sql(year: int) -> str:
    return (
        'SELECT c."DESCRICAO" AS diagnostico, COUNT(*) AS total_obitos '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        f'WHERE i."MORTE" = true AND EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY c."DESCRICAO" ORDER BY total_obitos DESC LIMIT 10;'
    )


def top_diagnoses_sql(year: int) -> str:
    return (
        'SELECT c."DESCRICAO" AS diagnostico, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY c."DESCRICAO" ORDER BY total_internacoes DESC LIMIT 10;'
    )


def cid_chapters_sql(year: int) -> str:
    return (
        'SELECT c."DS_CAPITULO" AS capitulo_cid, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY c."DS_CAPITULO" ORDER BY total_internacoes DESC LIMIT 10;'
    )


def top_diagnoses_by_uf_sql(year: int, uf: str) -> str:
    return (
        'SELECT c."DESCRICAO" AS diagnostico, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE mu."SG_UF" = \'{uf}\' AND EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY c."DESCRICAO" ORDER BY total_internacoes DESC LIMIT 10;'
    )


def top_municipios_sql(year: int, uf: str) -> str:
    return (
        'SELECT mu."NO_MUNICIPIO" AS municipio_residencia, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE mu."SG_UF" = \'{uf}\' AND EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY mu."NO_MUNICIPIO" ORDER BY total_internacoes DESC LIMIT 10;'
    )


def out_of_state_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS internacoes_fora_uf_residencia FROM internacoes i '
        'JOIN municipios mr ON i."MUNIC_RES" = mr."CO_MUNICIPIO_6D" '
        'JOIN hospital h ON i."CNES" = h."CNES" '
        'JOIN municipios mh ON h."MUNIC_MOV" = mh."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND mr."SG_UF" <> mh."SG_UF";'
    )


def region_health_sql(year: int, uf: str) -> str:
    return (
        'SELECT mu."NO_REGIAO_SAUDE" AS regiao_saude, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE mu."SG_UF" = \'{uf}\' AND EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY mu."NO_REGIAO_SAUDE" ORDER BY total_internacoes DESC LIMIT 10;'
    )


def top_uf_volume_sql(year: int) -> str:
    return (
        'SELECT mu."SG_UF" AS uf_residencia, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY mu."SG_UF" ORDER BY total_internacoes DESC LIMIT 10;'
    )


def top_procedures_sql(year: int) -> str:
    return (
        'SELECT p."NOME_PROC" AS procedimento, COUNT(*) AS total_procedimentos '
        'FROM internacao_procedimento ip JOIN internacoes i ON ip."N_AIH" = i."N_AIH" '
        'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY p."NOME_PROC" ORDER BY total_procedimentos DESC LIMIT 10;'
    )


def cesarean_by_uf_sql(year: int) -> str:
    return (
        'SELECT mu."SG_UF" AS uf_residencia, COUNT(*) AS total_procedimentos_cesarea '
        'FROM internacao_procedimento ip JOIN internacoes i ON ip."N_AIH" = i."N_AIH" '
        'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA" '
        'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND p."NOME_PROC" ILIKE \'%CESAR%\' '
        'GROUP BY mu."SG_UF" ORDER BY total_procedimentos_cesarea DESC;'
    )


def top_procedures_by_uf_sql(year: int, uf: str) -> str:
    return top_procedures_sql(year).replace(
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} ',
        f'JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" WHERE mu."SG_UF" = \'{uf}\' AND EXTRACT(YEAR FROM i."DT_INTER") = {year} ',
    )


def top_procedures_by_condition_sql(year: int, condition_sql: str) -> str:
    return (
        'SELECT p."NOME_PROC" AS procedimento, COUNT(*) AS total_procedimentos '
        'FROM internacao_procedimento ip JOIN internacoes i ON ip."N_AIH" = i."N_AIH" '
        'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA" '
        'JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND {condition_sql} '
        'GROUP BY p."NOME_PROC" ORDER BY total_procedimentos DESC LIMIT 10;'
    )


def cost_by_uf_sql(year: int) -> str:
    return (
        'SELECT mu."SG_UF" AS uf_residencia, ROUND(SUM(i."VAL_TOT"), 2) AS valor_total '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY mu."SG_UF" ORDER BY valor_total DESC;'
    )


def avg_cost_condition_sql(year: int, condition_sql: str) -> str:
    return (
        'SELECT COUNT(*) AS total_internacoes, ROUND(AVG(i."VAL_TOT"), 2) AS custo_medio '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND {condition_sql};'
    )


def hospital_cost_per_day_sql(year: int) -> str:
    return (
        'SELECT h."NO_HOSPITAL" AS hospital, COUNT(*) AS total_internacoes, '
        'ROUND(SUM(i."VAL_TOT") / NULLIF(SUM(i."DIAS_PERM"), 0), 2) AS custo_medio_por_dia '
        'FROM internacoes i JOIN hospital h ON i."CNES" = h."CNES" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND i."DIAS_PERM" > 0 '
        'GROUP BY h."NO_HOSPITAL" HAVING COUNT(*) >= 1000 ORDER BY custo_medio_por_dia DESC NULLS LAST LIMIT 10;'
    )


def uti_cost_by_uf_sql(year: int) -> str:
    return (
        'SELECT mu."SG_UF" AS uf_residencia, ROUND(SUM(i."VAL_UTI"), 2) AS valor_uti_total '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY mu."SG_UF" ORDER BY valor_uti_total DESC;'
    )


def avg_stay_by_specialty_sql(year: int) -> str:
    return (
        'SELECT e."DESCRICAO" AS especialidade, ROUND(AVG(i."DIAS_PERM"), 2) AS permanencia_media '
        'FROM internacoes i JOIN especialidade e ON i."ESPEC" = e."ESPEC" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY e."DESCRICAO" ORDER BY permanencia_media DESC NULLS LAST LIMIT 10;'
    )


def uti_count_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS internacoes_com_uti FROM internacoes i '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND (i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0);'
    )


def uti_mortality_by_uf_sql(year: int) -> str:
    return (
        'SELECT mu."SG_UF" AS uf_residencia, COUNT(*) AS total_internacoes, '
        'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos, '
        'ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND (i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0) '
        'GROUP BY mu."SG_UF" ORDER BY taxa_mortalidade_percentual DESC;'
    )


def uti_brand_distribution_sql(year: int) -> str:
    return (
        'SELECT COALESCE(m."DESCRICAO", \'sem marca informada\') AS tipo_uti, COUNT(*) AS total_internacoes '
        'FROM internacoes i LEFT JOIN marca_uti m ON i."MARCA_UTI" = m."MARCA_UTI" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND (i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0) '
        'GROUP BY tipo_uti ORDER BY total_internacoes DESC;'
    )


def sex_distribution_sql(year: int) -> str:
    return (
        'SELECT s."DESCRICAO" AS sexo, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN sexo s ON i."SEXO" = s."SEXO" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY s."DESCRICAO" ORDER BY total_internacoes DESC;'
    )


def race_death_distribution_sql(year: int) -> str:
    return (
        'SELECT COALESCE(r."DESCRICAO", \'sem raca/cor mapeada\') AS raca_cor, COUNT(*) AS total_obitos '
        'FROM internacoes i LEFT JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" '
        f'WHERE i."MORTE" = true AND EXTRACT(YEAR FROM i."DT_INTER") = {year} '
        'GROUP BY COALESCE(r."DESCRICAO", \'sem raca/cor mapeada\') ORDER BY total_obitos DESC;'
    )


def education_coverage_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS total_internacoes, COUNT(ins."INSTRU") AS com_instrucao_mapeada, '
        'ROUND(COUNT(ins."INSTRU") * 100.0 / NULLIF(COUNT(*), 0), 2) AS percentual_mapeado '
        'FROM internacoes i LEFT JOIN instrucao ins ON i."INSTRU" = ins."INSTRU" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year};'
    )


def avg_age_condition_sql(year: int, condition_sql: str) -> str:
    return (
        'SELECT COUNT(*) AS total_internacoes, ROUND(AVG(i."IDADE"), 2) AS idade_media '
        'FROM internacoes i JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        f'WHERE i."IDADE" IS NOT NULL AND EXTRACT(YEAR FROM i."DT_INTER") = {year} AND {condition_sql};'
    )


def population_by_uf_sql(year: int) -> str:
    return (
        'SELECT m."SG_UF" AS uf, SUM(s."QT_POPULACAO") AS populacao '
        'FROM socioeconomico s JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D" '
        f'WHERE s."NU_ANO" = {year} GROUP BY m."SG_UF" ORDER BY populacao DESC;'
    )


def socio_metric_by_uf_sql(year: int, column: str, _metric_name: str) -> str:
    return (
        f'SELECT m."SG_UF" AS uf, ROUND(AVG(s."{column}"), 2) AS valor_indicador '
        'FROM socioeconomico s JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D" '
        f'WHERE s."NU_ANO" = {year} GROUP BY m."SG_UF" ORDER BY valor_indicador DESC NULLS LAST;'
    )


def pib_municipios_sql(year: int) -> str:
    return (
        'SELECT m."NO_MUNICIPIO" AS municipio, m."SG_UF" AS uf, ROUND(s."VL_PIB_PERCAPITA", 2) AS pib_per_capita '
        'FROM socioeconomico s JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D" '
        f'WHERE s."NU_ANO" = {year} ORDER BY pib_per_capita DESC NULLS LAST LIMIT 10;'
    )


def infant_mortality_socio_by_uf_sql(year: int) -> str:
    return (
        'SELECT m."SG_UF" AS uf, ROUND(AVG(s."VL_MORT_INFANTIL"), 2) AS mortalidade_infantil_media '
        'FROM socioeconomico s JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D" '
        f'WHERE s."NU_ANO" = {year} GROUP BY m."SG_UF" ORDER BY mortalidade_infantil_media DESC NULLS LAST;'
    )


def hospitalization_rate_population_sql(year: int) -> str:
    return (
        'WITH internacoes_por_uf AS (SELECT mu."SG_UF" AS uf, COUNT(*) AS total_internacoes '
        'FROM internacoes i JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} GROUP BY mu."SG_UF"), '
        'populacao_por_uf AS (SELECT m."SG_UF" AS uf, SUM(s."QT_POPULACAO") AS populacao '
        'FROM socioeconomico s JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D" '
        f'WHERE s."NU_ANO" = {year} GROUP BY m."SG_UF") '
        'SELECT i.uf, i.total_internacoes, p.populacao, ROUND(i.total_internacoes * 100000.0 / NULLIF(p.populacao, 0), 2) AS taxa_por_100k '
        'FROM internacoes_por_uf i JOIN populacao_por_uf p ON i.uf = p.uf ORDER BY taxa_por_100k DESC;'
    )


def missing_diag_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS internacoes_sem_diag_princ FROM internacoes i '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND (i."DIAG_PRINC" IS NULL OR TRIM(i."DIAG_PRINC") = \'\');'
    )


def unmatched_cid_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS diagnosticos_sem_lookup FROM internacoes i LEFT JOIN cid c ON i."DIAG_PRINC" = c."CID" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND i."DIAG_PRINC" IS NOT NULL AND c."CID" IS NULL;'
    )


def unmatched_municipio_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS municipios_residencia_sem_lookup FROM internacoes i LEFT JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D" '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND i."MUNIC_RES" IS NOT NULL AND mu."CO_MUNICIPIO_6D" IS NULL;'
    )


def race_missing_deaths_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS total_obitos, SUM(CASE WHEN r."RACA_COR" IS NULL THEN 1 ELSE 0 END) AS obitos_sem_raca_cor_mapeada, '
        'ROUND(SUM(CASE WHEN r."RACA_COR" IS NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS percentual_sem_raca_cor '
        'FROM internacoes i LEFT JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR" '
        f'WHERE i."MORTE" = true AND EXTRACT(YEAR FROM i."DT_INTER") = {year};'
    )


def invalid_dates_sql(year: int) -> str:
    return (
        'SELECT COUNT(*) AS altas_antes_da_internacao FROM internacoes i '
        f'WHERE EXTRACT(YEAR FROM i."DT_INTER") = {year} AND i."DT_SAIDA" < i."DT_INTER";'
    )


def assert_category_added(builder: CorpusBuilder, category: str, expected_count: int) -> None:
    actual = sum(1 for item in builder.items if item["category"] == category)
    if actual != expected_count:
        raise AssertionError(f"{category}: expected {expected_count}, got {actual}")


def write_jsonl(items: Iterable[dict[str, Any]], path: Path = OUTPUT_PATH) -> None:
    lines = [json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in items]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    write_jsonl(build_corpus())
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
