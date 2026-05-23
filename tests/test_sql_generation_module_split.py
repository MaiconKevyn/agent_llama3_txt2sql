import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")
pytest.importorskip("langchain_community")

from src.agent.prompt_builder import build_pregeneration_hints
from src.agent.sql_fallback import generate_sql_with_fallback
from src.agent.sql_generation import (
    SQLOutput,
    _build_deterministic_scalar_sql,
    _build_pregeneration_hints,
)
from src.semantic.planner import build_semantic_plan


def test_sql_generation_module_split_preserves_hint_behavior():
    query = "Quais os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?"

    direct = build_pregeneration_hints(["municipios"], query)
    compat = _build_pregeneration_hints(["municipios"], query)

    assert "PER-ESTADO" in direct
    assert compat == direct


def test_sql_output_schema_available():
    model = SQLOutput(sql="select 1", reasoning="ok", confidence=0.5)

    assert model.sql == "select 1"


class DummyStructuredManager:
    config = type("Config", (), {"llm_model": "test-model", "llm_temperature": 0.0})()

    def invoke_chat_structured(self, messages, output_schema):
        return output_schema(sql="SELECT 42", reasoning="structured ok", confidence=0.8)

    def invoke_chat(self, messages):
        raise AssertionError("text fallback should not run")

    def _clean_sql_query(self, sql):
        return sql if sql.endswith(";") else f"{sql};"


def test_sql_fallback_uses_structured_output_metadata():
    result = generate_sql_with_fallback(
        llm_manager=DummyStructuredManager(),
        formatted_messages=[],
        user_query="teste",
        schema_context="TABLE internacoes",
        selected_tables=["internacoes"],
        semantic_plan=None,
        chart_plan=None,
        ablation_flags={},
    )

    assert result.sql_query == "SELECT 42;"
    assert result.generation_method == "structured"
    assert result.metadata["sql_generation_source"] == "current_structured_output"
    assert result.metadata["sql_generation_confidence"] == 0.8


class DummyTextFallbackManager:
    config = type("Config", (), {"llm_model": "test-model", "llm_temperature": 0.0})()

    def invoke_chat_structured(self, messages, output_schema):
        raise RuntimeError("structured unavailable")

    def invoke_chat(self, messages):
        return "SELECT 99"

    def _clean_sql_query(self, sql):
        return sql if sql.endswith(";") else f"{sql};"


def test_sql_fallback_uses_text_when_structured_output_fails():
    result = generate_sql_with_fallback(
        llm_manager=DummyTextFallbackManager(),
        formatted_messages=[],
        user_query="teste",
        schema_context="TABLE internacoes",
        selected_tables=["internacoes"],
        semantic_plan=None,
        chart_plan=None,
        ablation_flags={},
    )

    assert result.sql_query == "SELECT 99;"
    assert result.generation_method == "text_fallback"


def test_deterministic_scalar_sql_handles_age_minimum():
    plan = build_semantic_plan("Qual a menor idade registrada nas internações?")

    sql = _build_deterministic_scalar_sql(plan)

    assert sql == 'SELECT MIN("IDADE") AS idade_minima FROM internacoes;'


def test_deterministic_scalar_sql_handles_under_one_year_count():
    plan = build_semantic_plan(
        "Quantas internações foram registradas para pacientes com menos de 1 ano de idade?"
    )

    sql = _build_deterministic_scalar_sql(plan)

    assert sql == 'SELECT COUNT(*) AS total_internacoes FROM internacoes WHERE "IDADE" = 0;'
