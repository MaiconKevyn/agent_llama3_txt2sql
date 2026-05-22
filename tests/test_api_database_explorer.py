import asyncio

import pytest
from fastapi import HTTPException

from src.interfaces.api import main as api_main


def test_prepare_database_query_rejects_non_select_sql():
    with pytest.raises(HTTPException) as exc_info:
        api_main._prepare_database_query("DROP TABLE internacoes", 100)

    assert exc_info.value.status_code == 400
    assert "Apenas consultas de leitura" in exc_info.value.detail


def test_prepare_database_query_wraps_select_with_limit():
    prepared = api_main._prepare_database_query("SELECT * FROM internacoes;", 25)

    assert prepared == "SELECT * FROM (SELECT * FROM internacoes) AS ui_query LIMIT 25"


def test_explorable_database_table_accepts_only_main_non_test_tables():
    assert api_main._is_explorable_database_table("main", "internacoes") is True
    assert api_main._is_explorable_database_table("analytics", "internacoes") is False
    assert api_main._is_explorable_database_table("main", "dbt_model_results") is False
    assert api_main._is_explorable_database_table("main", "unit_test_fixture") is False
    assert api_main._is_explorable_database_table("main", "tmp_internacoes") is False


def test_database_table_detail_rejects_non_explorable_tables(monkeypatch):
    with pytest.raises(HTTPException) as exc_info:
        api_main._build_database_table_detail("dbt_test", "internacoes", 2)

    assert exc_info.value.status_code == 404
    assert "Tabela nao disponivel" in exc_info.value.detail


def test_table_context_prompt_is_rehydrated_from_backend():
    table_context = api_main.TableContext(table_schema="main", table_name="internacoes")
    detail = api_main.DatabaseTableDetailResponse(
        table_schema="main",
        table_name="internacoes",
        columns=[
            api_main.DatabaseColumn(
                ordinal_position=1,
                column_name="MORTE",
                data_type="BOOLEAN",
                is_nullable="YES",
            ),
            api_main.DatabaseColumn(
                ordinal_position=2,
                column_name="MUNIC_RES",
                data_type="VARCHAR",
                is_nullable="YES",
            ),
        ],
        sample_columns=[],
        sample_rows=[],
        sample_limit=0,
        timestamp="2026-05-22T00:00:00",
    )

    enriched_query, metadata = api_main._apply_table_context_to_query(
        "Que perguntas posso fazer com ela?",
        table_context,
        detail,
    )

    assert "Contexto ativo de tabela: main.internacoes" in enriched_query
    assert "MORTE BOOLEAN" in enriched_query
    assert "MUNIC_RES VARCHAR" in enriched_query
    assert metadata == {
        "table_context_applied": True,
        "table_context": {
            "table_schema": "main",
            "table_name": "internacoes",
            "columns": ["MORTE", "MUNIC_RES"],
        },
    }


def test_process_query_validates_and_applies_table_context(monkeypatch):
    captured = {}

    class FakeOrchestrator:
        def process_query(self, query, session_id=None, streaming=False):
            captured["query"] = query
            captured["session_id"] = session_id
            captured["streaming"] = streaming
            return {
                "success": True,
                "response": "ok",
                "sql_query": "SELECT 1",
                "metadata": {"session_id": session_id},
            }

    detail = api_main.DatabaseTableDetailResponse(
        table_schema="main",
        table_name="internacoes",
        columns=[
            api_main.DatabaseColumn(
                ordinal_position=1,
                column_name="MORTE",
                data_type="BOOLEAN",
                is_nullable="YES",
            )
        ],
        sample_columns=[],
        sample_rows=[],
        sample_limit=0,
        timestamp="2026-05-22T00:00:00",
    )

    monkeypatch.setattr(api_main, "_orchestrator", FakeOrchestrator())
    monkeypatch.setattr(
        api_main,
        "_load_table_context_detail",
        lambda table_context: detail,
    )

    response = asyncio.run(
        api_main.process_query(
            api_main.QueryRequest(
                query="explique esta tabela",
                session_id="s1",
                table_context=api_main.TableContext(
                    table_schema="main",
                    table_name="internacoes",
                ),
            )
        )
    )

    assert "Contexto ativo de tabela: main.internacoes" in captured["query"]
    assert "explique esta tabela" in captured["query"]
    assert response.metadata["table_context_applied"] is True
    assert response.metadata["table_context"]["table_name"] == "internacoes"


def test_database_query_endpoint_uses_read_only_limited_sql(monkeypatch):
    executed = {}

    class FakeResult:
        def keys(self):
            return ["total"]

        def mappings(self):
            return self

        def all(self):
            return [{"total": 42}]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement):
            executed["sql"] = str(statement)
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(api_main, "_get_database_engine", lambda: FakeEngine())

    response = asyncio.run(
        api_main.database_query(
            api_main.DatabaseQueryRequest(sql="SELECT COUNT(*) AS total FROM internacoes", limit=10)
        )
    )

    assert executed["sql"] == (
        "SELECT * FROM (SELECT COUNT(*) AS total FROM internacoes) AS ui_query LIMIT 10"
    )
    assert response.columns == ["total"]
    assert response.rows == [{"total": 42}]
    assert response.row_count == 1
