import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")
pytest.importorskip("langchain_community")

from src.agent.prompt_builder import build_pregeneration_hints
from src.agent.sql_generation import SQLOutput
from src.agent.sql_generation import _build_pregeneration_hints
from src.agent.sql_generation import _build_deterministic_scalar_sql
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
