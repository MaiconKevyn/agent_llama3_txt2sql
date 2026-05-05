import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_community")

from evaluation.table_selection.benchmark import score_table_selection
from src.agent import table_selection as ts
from src.application.config.simple_config import OrchestratorConfig
from src.application.prompts.table_selection.catalog import (
    get_available_description_variants,
    get_available_prompt_variants,
    get_available_table_selection_presets,
    load_table_selection_catalog,
    resolve_table_selection_strategy,
)


def test_score_table_selection_marks_optional_tables_as_acceptable():
    score = score_table_selection(
        selected_tables=["atendimentos", "procedimentos", "internacoes"],
        gold_core_tables=["atendimentos", "procedimentos"],
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


def test_select_tables_with_debug_heuristic_mode_uses_heuristic_stage():
    debug = ts.select_tables_with_debug(
        user_query="Quantas mortes foram registradas no estado do RS?",
        available_tables=["internacoes", "municipios", "socioeconomico"],
        llm_manager=None,
        mode=ts.TABLE_SELECTION_MODE_HEURISTIC_ONLY,
    )

    assert debug["stage_used"] == "heuristic"
    assert debug["validated_selected_tables"] == ["internacoes", "municipios"]


def test_select_tables_with_debug_llm_disabled_uses_fallback():
    def fake_embedding(*args, **kwargs):
        return [], 0.0

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(ts, "_run_embedding_table_selection", fake_embedding)

    debug = ts.select_tables_with_debug(
        user_query="Qual o total gasto em internações de UTI?",
        available_tables=["internacoes", "socioeconomico"],
        llm_manager=None,
        mode=ts.TABLE_SELECTION_MODE_LLM_DISABLED_FALLBACK,
    )

    assert debug["stage_used"] in {"heuristic", "embedding", "fallback"}
    assert "internacoes" in debug["validated_selected_tables"]
    monkeypatch.undo()


def test_select_tables_with_debug_llm_only_uses_mocked_llm(monkeypatch):
    def fake_llm(*args, **kwargs):
        return {
            "prompt": "mock prompt",
            "raw_response": "internacoes, municipios",
            "parsed_tables": ["internacoes", "municipios"],
        }

    monkeypatch.setattr(ts, "_run_llm_table_selection", fake_llm)

    debug = ts.select_tables_with_debug(
        user_query="Quais municípios têm mais internações?",
        available_tables=["internacoes", "municipios"],
        llm_manager=object(),
        mode=ts.TABLE_SELECTION_MODE_LLM_ONLY,
        description_variant="minimal",
        prompt_variant="compact",
    )

    assert debug["stage_used"] == "llm"
    assert debug["validated_selected_tables"] == ["internacoes", "municipios"]
    assert debug["llm"]["raw_response"] == "internacoes, municipios"


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


def test_schema_contract_and_selection_protocol_variants_include_core_invariants():
    available = ["internacoes", "tempo", "hospital", "municipios", "socioeconomico"]

    lines = ts._build_table_description_lines(available, "schema_contract")
    prompt = ts._build_llm_selection_prompt(
        "Quantas internações ocorreram em 2015?",
        available,
        description_variant="schema_contract",
        prompt_variant="selection_protocol",
    )

    assert any("grain=1 row per hospitalization" in line for line in lines)
    assert any("do_not_use for year/month/weekend filters" in line for line in lines)
    assert "`internacoes` is the primary fact table" in prompt
    assert "patient residence geography" in prompt
    assert "avoid `tempo`" in prompt


def test_decision_protocol_variant_combines_protocol_and_checklist_constraints():
    available = ["internacoes", "tempo", "hospital", "municipios", "socioeconomico", "cid"]

    prompt = ts._build_llm_selection_prompt(
        "Quais municípios que atendem mais pacientes por diagnóstico?",
        available,
        description_variant="role_guardrails",
        prompt_variant="decision_protocol",
    )

    assert "NON-NEGOTIABLE DATABASE INVARIANTS" in prompt
    assert "DECISION CHECKLIST" in prompt
    assert "MANDATORY DISTINCTIONS" in prompt
    assert "disease/cause names or descriptions -> add `cid`" in prompt
    assert "hospital geography -> `internacoes.CNES` + `hospital.MUNIC_MOV` + `municipios`" in prompt


def test_table_selection_catalog_exposes_known_variants():
    catalog = load_table_selection_catalog()

    assert "role_guardrails" in get_available_description_variants()
    assert "schema_contract" in get_available_description_variants()
    assert "llm_best" in get_available_table_selection_presets()
    assert "decision_checklist" in get_available_prompt_variants()
    assert "selection_protocol" in get_available_prompt_variants()
    assert "decision_protocol" in get_available_prompt_variants()
    assert "current" in catalog["prompt_variants"]


def test_table_selection_strategy_resolves_named_preset_and_allows_overrides():
    strategy = resolve_table_selection_strategy(preset_name="llm_best")
    assert strategy == {
        "preset_name": "llm_best",
        "mode": "llm_only",
        "description_variant": "role_guardrails",
        "prompt_variant": "decision_checklist",
    }

    overridden = resolve_table_selection_strategy(
        preset_name="llm_best",
        prompt_variant="selection_protocol",
    )
    assert overridden["preset_name"] == "llm_best"
    assert overridden["mode"] == "llm_only"
    assert overridden["description_variant"] == "role_guardrails"
    assert overridden["prompt_variant"] == "selection_protocol"


def test_orchestrator_config_defaults_do_not_mask_table_selection_preset():
    cfg = OrchestratorConfig()
    strategy = resolve_table_selection_strategy(
        preset_name=cfg.table_selection_preset,
        mode=cfg.table_selection_mode,
        description_variant=cfg.table_selection_description_variant,
        prompt_variant=cfg.table_selection_prompt_variant,
    )

    assert strategy["preset_name"] == "llm_best"
    assert strategy["mode"] == "llm_only"
    assert strategy["description_variant"] == "role_guardrails"
    assert strategy["prompt_variant"] == "decision_checklist"
