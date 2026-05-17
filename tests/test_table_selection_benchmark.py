import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_community")

from evaluation.table_selection.benchmark import score_table_selection
from src.agent import table_selection as ts
from src.application.config.simple_config import OrchestratorConfig


def test_score_table_selection_marks_optional_tables_as_acceptable():
    score = score_table_selection(
        selected_tables=["internacao_procedimento", "procedimentos", "internacoes"],
        gold_core_tables=["internacao_procedimento", "procedimentos"],
        gold_optional_tables=["internacoes"],
        gold_forbidden_tables=["socioeconomico"],
    )

    assert score["acceptable"] is True
    assert score["exact_core_match"] is False
    assert score["core_recall"] == 1.0
    assert score["allowed_precision"] == 1.0


def test_score_table_selection_detects_missing_and_forbidden_tables():
    score = score_table_selection(
        selected_tables=["internacoes", "socioeconomico"],
        gold_core_tables=["internacoes", "municipios"],
        gold_optional_tables=[],
        gold_forbidden_tables=["socioeconomico"],
    )

    assert score["acceptable"] is False
    assert score["forbidden_hit"] is True
    assert score["missing_core"] == ["municipios"]
    assert score["forbidden_selected"] == ["socioeconomico"]


def test_validate_table_selection_forces_wide_socioeconomic_metric_tables():
    validated = ts._validate_table_selection(
        user_query="Qual o total de medicos registrados nos estados do MA e RS?",
        selected_tables=["hospital", "municipios"],
        available_tables=["hospital", "municipios", "socioeconomico"],
    )

    assert validated == ["socioeconomico", "municipios"]


def test_validate_table_selection_removes_socioeconomico_from_diagnosis_lookup():
    validated = ts._validate_table_selection(
        user_query="tem diagnostico de covid?",
        selected_tables=["cid", "internacoes", "socioeconomico"],
        available_tables=["cid", "internacoes", "socioeconomico"],
    )

    assert validated == ["cid", "internacoes"]


def test_validate_table_selection_removes_procedure_tables_from_diagnosis_association():
    validated = ts._validate_table_selection(
        user_query="existe relação entre idade e cancer de prostata?",
        selected_tables=["internacoes", "cid", "procedimentos"],
        available_tables=["internacoes", "cid", "procedimentos"],
    )

    assert validated == ["internacoes", "cid"]


def test_validate_table_selection_removes_redundant_sexo_lookup():
    validated = ts._validate_table_selection(
        user_query="Quais são as três causas de morte mais frequentes entre mulheres?",
        selected_tables=["internacoes", "sexo", "cid"],
        available_tables=["internacoes", "sexo", "cid"],
    )

    assert validated == ["internacoes", "cid"]


def test_validate_table_selection_adds_hospital_for_municipios_que_atendem():
    validated = ts._validate_table_selection(
        user_query="Quais são os 10 municípios que atendem mais pacientes?",
        selected_tables=["internacoes", "municipios"],
        available_tables=["internacoes", "hospital", "municipios"],
    )

    assert validated == ["internacoes", "municipios", "hospital"]


def test_validate_table_selection_adds_hospital_location_path_for_hospital_by_state():
    validated = ts._validate_table_selection(
        user_query="Quais são os 3 hospitais com maior custo médio de UTI por estado?",
        selected_tables=["internacoes"],
        available_tables=["internacoes", "hospital", "municipios"],
    )

    assert validated == ["internacoes", "hospital", "municipios"]


def test_orchestrator_config_defaults_use_llamaindex_context():
    cfg = OrchestratorConfig()

    assert cfg.enable_llamaindex_context is True
    assert cfg.llamaindex_mode == "context"
