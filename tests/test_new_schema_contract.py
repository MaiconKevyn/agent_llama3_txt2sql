from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "src" / "application" / "schema" / "generated"


def _columns_for(table_name: str) -> set[str]:
    with (GENERATED / "column_catalog.csv").open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return {row["column_name"] for row in reader if row["table_name"] == table_name}


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generated_schema_contract_for_core_tables() -> None:
    assert {"CID", "DESCRICAO"} <= _columns_for("cid")
    assert {
        "CO_MUNICIPIO_6D",
        "CO_MUNICIPIO_7D",
        "NO_MUNICIPIO",
        "SG_UF",
    } <= _columns_for("municipios")
    assert {
        "CO_MUNICIPIO_6D",
        "NU_ANO",
        "QT_POPULACAO",
        "VL_PIB_PERCAPITA",
        "VL_MORT_INFANTIL",
        "QT_LEITOS_SUS",
        "VL_LEITOS_SUS_1000",
        "QT_MEDICOS",
        "VL_MEDICOS_1000",
    } <= _columns_for("socioeconomico")
    assert "GESTRISCO" in _columns_for("internacoes")


def test_removed_columns_are_not_in_generated_schema() -> None:
    old_cid_description = "CD_" + "DESCRICAO"
    old_municipality_code = "codigo" + "_6d"
    old_ibge_code = "codigo" + "_ibge"
    old_obstetric_column = "GEST" + "RICO"

    assert old_cid_description not in _columns_for("cid")
    assert old_municipality_code not in _columns_for("municipios")
    assert old_ibge_code not in _columns_for("municipios")
    assert "nome" not in _columns_for("municipios")
    assert "estado" not in _columns_for("municipios")
    assert "metrica" not in _columns_for("socioeconomico")
    assert "valor" not in _columns_for("socioeconomico")
    assert old_obstetric_column not in _columns_for("internacoes")


def test_active_schema_context_does_not_use_removed_column_names() -> None:
    active_files = [
        "src/application/config/table_descriptions.py",
        "src/application/config/table_templates.py",
        "src/application/prompts/table_selection/variants.yml",
        "src/agent/schema_node.py",
        "src/agent/prompt_builder.py",
        "src/agent/table_selection.py",
        "src/semantic/catalog.yml",
        "src/semantic/planner.py",
        "src/semantic/validators.py",
        "src/agent/execution.py",
    ]
    forbidden_positive_snippets = [
        'SUM(s."' + 'valor")',
        'AVG(s."' + 'valor")',
        'MAX(CASE WHEN s."' + 'metrica"',
        's."' + 'metrica" =',
        's."' + 'metrica" IN',
        "grain: municipio_ano" + "_metrica",
        "default_scope: socioeconomico rows where metrica",
        "GEST" + "RICO",
        "CD_" + "DESCRICAO",
        "codigo" + "_6d",
        'mu."' + 'nome"',
        "mu." + "nome",
        'mu."' + 'estado"',
        "mu." + "estado",
    ]
    offenders: list[str] = []
    for path in active_files:
        text = _text(path)
        for snippet in forbidden_positive_snippets:
            if snippet in text:
                offenders.append(f"{path}: {snippet}")
    assert offenders == []


def test_memory_examples_do_not_use_removed_schema_artifacts() -> None:
    examples_text = _text("src/memory/examples.json")
    forbidden_snippets = [
        "FROM mortes",
        "JOIN mortes",
        "uti_detalhes",
        "dado_ibge",
        "CD_" + "DESCRICAO",
        "codigo" + "_6d",
        "GEST" + "RICO",
    ]

    offenders = [snippet for snippet in forbidden_snippets if snippet in examples_text]

    assert offenders == []
