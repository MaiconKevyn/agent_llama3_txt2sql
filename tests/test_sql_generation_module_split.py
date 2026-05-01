import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")

from src.agent.prompt_builder import build_pregeneration_hints
from src.agent.schemas import SQLOutput
from src.agent.self_consistency import N_SQL_CANDIDATES
from src.agent.sql_generation import _build_pregeneration_hints


def test_sql_generation_module_split_preserves_hint_behavior():
    query = "Quais os 3 hospitais com maior custo médio de UTI por estado (MA e RS)?"

    direct = build_pregeneration_hints(["municipios"], query)
    compat = _build_pregeneration_hints(["municipios"], query)

    assert "PER-ESTADO" in direct
    assert compat == direct


def test_sql_output_schema_and_self_consistency_constants_available():
    model = SQLOutput(sql="select 1", reasoning="ok", confidence=0.5)

    assert model.sql == "select 1"
    assert N_SQL_CANDIDATES == 3
