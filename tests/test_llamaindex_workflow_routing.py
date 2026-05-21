import pytest

from src.agent import schema_node, table_selection
from src.agent.state_helpers import create_initial_messages_state


class _FakeListTablesTool:
    name = "sql_db_list_tables"

    def invoke(self, _input):
        return "internacoes: fact table\nmunicipios: geography dimension\ncid: diagnosis catalog"


class _FakeLLMManager:
    def get_sql_tools(self):
        return [_FakeListTablesTool()]

    def get_database(self):
        raise AssertionError("database fallback should not be needed")


def test_list_tables_node_uses_llamaindex_context_by_default(monkeypatch):
    monkeypatch.setattr(table_selection, "get_llm_manager", lambda: _FakeLLMManager())

    class _FakeContext:
        selected_tables = ["cid"]
        table_context = ["TABLE: cid\nPURPOSE: catalog"]
        schema_context = "TABLE: cid\nPURPOSE: catalog"
        retrieval_mode = "llamaindex_schema"
        confidence = 0.91
        error = ""

    monkeypatch.setattr(
        table_selection,
        "retrieve_llamaindex_schema_context",
        lambda **_kwargs: _FakeContext(),
    )
    state = create_initial_messages_state(
        "Quantos códigos CID-10 distintos existem?",
        session_id="test",
    )

    new_state = table_selection.list_tables_node(state)

    assert new_state["selected_tables"] == ["cid"]
    assert new_state["response_metadata"]["llamaindex_enabled"] is True
    assert new_state["response_metadata"]["table_selection_mode"] == "llamaindex_context"


def test_list_tables_node_uses_llamaindex_context_when_available(monkeypatch):
    monkeypatch.setattr(table_selection, "get_llm_manager", lambda: _FakeLLMManager())

    class _FakeContext:
        selected_tables = ["cid"]
        table_context = ["TABLE: cid\nPURPOSE: catalog"]
        schema_context = "TABLE: cid\nPURPOSE: catalog"
        retrieval_mode = "llamaindex_schema"
        confidence = 0.91
        error = ""

    monkeypatch.setattr(
        table_selection,
        "retrieve_llamaindex_schema_context",
        lambda **_kwargs: _FakeContext(),
    )
    state = create_initial_messages_state(
        "Quantos códigos CID-10 distintos existem?",
        session_id="test",
        ablation_flags={
            "enable_llamaindex_context": True,
            "llamaindex_mode": "context",
        },
    )

    new_state = table_selection.list_tables_node(state)

    assert new_state["selected_tables"] == ["cid"]
    assert new_state["llamaindex_context"]["schema_context"].startswith("TABLE: cid")
    assert new_state["response_metadata"]["llamaindex_enabled"] is True
    assert new_state["response_metadata"]["table_selection_mode"] == "llamaindex_context"


def test_list_tables_node_rebuilds_schema_context_after_financial_table_validation(monkeypatch):
    class _FinancialListTablesTool:
        name = "sql_db_list_tables"

        def invoke(self, _input):
            return "socioeconomico: municipal indicators\ninternacoes: hospitalization facts"

    class _FinancialLLMManager:
        def get_sql_tools(self):
            return [_FinancialListTablesTool()]

        def get_database(self):
            raise AssertionError("database fallback should not be needed")

    class _FakeContext:
        selected_tables = ["socioeconomico"]
        table_context = ["TABLE: socioeconomico\n- NU_ANO: INTEGER"]
        schema_context = "TABLE: socioeconomico\n- NU_ANO: INTEGER"
        retrieval_mode = "llamaindex_schema"
        confidence = 0.91
        error = ""

    class _Doc:
        metadata = {"table_name": "internacoes"}

        def get_content(self):
            return 'TABLE: internacoes\n- VAL_TOT: NUMERIC\n- DT_INTER: DATE'

    monkeypatch.setattr(table_selection, "get_llm_manager", lambda: _FinancialLLMManager())
    monkeypatch.setattr(
        table_selection,
        "retrieve_llamaindex_schema_context",
        lambda **_kwargs: _FakeContext(),
    )
    monkeypatch.setattr(
        table_selection,
        "build_llamaindex_schema_documents",
        lambda tables: [_Doc()] if tables == ["internacoes"] else [],
    )
    state = create_initial_messages_state(
        "Mostre em grafico de area o valor total por ano.",
        session_id="test",
    )

    new_state = table_selection.list_tables_node(state)

    assert new_state["selected_tables"] == ["internacoes"]
    assert new_state["response_metadata"]["raw_selected_tables"] == ["socioeconomico"]
    assert "TABLE: internacoes" in new_state["llamaindex_context"]["schema_context"]
    assert "TABLE: socioeconomico" not in new_state["llamaindex_context"]["schema_context"]


def test_list_tables_node_does_not_fallback_when_llamaindex_has_no_tables(monkeypatch):
    monkeypatch.setattr(table_selection, "get_llm_manager", lambda: _FakeLLMManager())

    class _EmptyContext:
        selected_tables = []
        table_context = []
        schema_context = ""
        retrieval_mode = "llamaindex_unavailable"
        confidence = 0.0
        error = "missing dependency"

    monkeypatch.setattr(
        table_selection,
        "retrieve_llamaindex_schema_context",
        lambda **_kwargs: _EmptyContext(),
    )
    state = create_initial_messages_state(
        "Quantas mortes foram registradas no estado do RS?",
        session_id="test",
        ablation_flags={
            "enable_llamaindex_context": True,
            "llamaindex_mode": "context",
        },
    )

    new_state = table_selection.list_tables_node(state)

    assert new_state["selected_tables"] == []
    assert new_state["response_metadata"]["llamaindex_retrieval_mode"] == "llamaindex_unavailable"
    assert new_state["response_metadata"]["table_selection_mode"] == "llamaindex_unavailable"
    assert any(error["type"] == "table_discovery_error" for error in new_state["errors"])


def test_list_tables_node_rejects_invalid_llamaindex_tables(monkeypatch):
    monkeypatch.setattr(table_selection, "get_llm_manager", lambda: _FakeLLMManager())

    class _InvalidContext:
        selected_tables = ["not_a_real_table"]
        table_context = ["invalid"]
        schema_context = "invalid"
        retrieval_mode = "llamaindex_schema"
        confidence = 0.7
        error = ""

    monkeypatch.setattr(
        table_selection,
        "retrieve_llamaindex_schema_context",
        lambda **_kwargs: _InvalidContext(),
    )
    state = create_initial_messages_state(
        "Quantas mortes foram registradas no estado do RS?",
        session_id="test",
        ablation_flags={
            "enable_llamaindex_context": True,
            "llamaindex_mode": "context",
        },
    )

    new_state = table_selection.list_tables_node(state)

    assert new_state["selected_tables"] == []
    assert new_state["response_metadata"]["table_selection_mode"] == "llamaindex_unavailable"
    assert any(error["type"] == "table_discovery_error" for error in new_state["errors"])


def test_get_schema_node_does_not_default_to_available_tables_without_selection(monkeypatch):
    class _SchemaTool:
        name = "sql_db_schema"

        def invoke(self, _input):
            raise AssertionError("schema tool should not be called without selected tables")

    class _SchemaLLMManager:
        def get_sql_tools(self):
            return [_SchemaTool()]

    monkeypatch.setattr(schema_node, "get_llm_manager", lambda: _SchemaLLMManager())
    state = create_initial_messages_state(
        "Quantas mortes foram registradas no estado do RS?",
        session_id="test",
    )
    state["available_tables"] = ["internacoes", "municipios"]
    state["selected_tables"] = []

    new_state = schema_node.get_schema_node(state)

    assert new_state["schema_context"] == ""
    assert any(error["type"] == "schema_error" for error in new_state["errors"])


def test_get_schema_node_uses_llamaindex_schema_context_without_db_schema_by_default(monkeypatch):
    calls = {"schema": 0}

    class _SchemaTool:
        name = "sql_db_schema"

        def invoke(self, _input):
            calls["schema"] += 1
            return "LIVE DB DDL SHOULD NOT BE USED BY DEFAULT"

    class _SchemaLLMManager:
        def get_sql_tools(self):
            return [_SchemaTool()]

    monkeypatch.setattr(schema_node, "get_llm_manager", lambda: _SchemaLLMManager())
    state = create_initial_messages_state(
        "Quantas mortes foram registradas?",
        session_id="test",
    )
    state["selected_tables"] = ["internacoes"]
    state["llamaindex_context"] = {
        "schema_context": 'TABLE internacoes\n- MORTE: BOOLEAN\n- MUNIC_RES: VARCHAR',
        "retrieval_mode": "llamaindex_schema",
    }

    new_state = schema_node.get_schema_node(state)

    assert calls["schema"] == 0
    assert new_state["schema_context"] == 'TABLE internacoes\n- MORTE: BOOLEAN\n- MUNIC_RES: VARCHAR'
    assert new_state["response_metadata"]["schema_context_source"] == "llamaindex"
    assert new_state["response_metadata"]["schema_context_verified_with_db"] is False


def test_get_schema_node_can_verify_llamaindex_schema_context_with_db_when_enabled(monkeypatch):
    calls = {"schema": 0}

    class _SchemaTool:
        name = "sql_db_schema"

        def invoke(self, _input):
            calls["schema"] += 1
            return 'CREATE TABLE internacoes ("MORTE" BOOLEAN);'

    class _SchemaLLMManager:
        def get_sql_tools(self):
            return [_SchemaTool()]

    monkeypatch.setattr(schema_node, "get_llm_manager", lambda: _SchemaLLMManager())
    state = create_initial_messages_state(
        "Quantas mortes foram registradas?",
        session_id="test",
        ablation_flags={"verify_llamaindex_schema_with_db": True},
    )
    state["selected_tables"] = ["internacoes"]
    state["llamaindex_context"] = {
        "schema_context": "TABLE internacoes\n- MORTE: BOOLEAN",
        "retrieval_mode": "llamaindex_schema",
    }

    new_state = schema_node.get_schema_node(state)

    assert calls["schema"] == 1
    assert 'CREATE TABLE internacoes ("MORTE" BOOLEAN);' in new_state["schema_context"]
    assert "TABLE internacoes\n- MORTE: BOOLEAN" in new_state["schema_context"]
    assert new_state["response_metadata"]["schema_context_source"] == "sql_db_schema"
    assert new_state["response_metadata"]["schema_context_verified_with_db"] is True


def test_refresh_schema_context_uses_llamaindex_schema_without_db_schema_by_default(monkeypatch):
    calls = {"schema": 0}

    class _ListTablesTool:
        name = "sql_db_list_tables"

        def invoke(self, _input):
            return "internacoes: fact table\nmunicipios: geography dimension"

    class _SchemaTool:
        name = "sql_db_schema"

        def invoke(self, _input):
            calls["schema"] += 1
            return "LIVE DB DDL SHOULD NOT BE USED BY DEFAULT"

    class _RefreshLLMManager:
        def get_sql_tools(self):
            return [_ListTablesTool(), _SchemaTool()]

        def get_database(self):
            raise AssertionError("database fallback should not be needed")

    class _FakeContext:
        selected_tables = ["internacoes"]
        table_context = ["TABLE internacoes"]
        schema_context = "TABLE internacoes\n- MORTE: BOOLEAN"
        retrieval_mode = "llamaindex_schema"
        confidence = 0.9
        error = ""

    monkeypatch.setattr(
        table_selection,
        "select_tables_with_llamaindex",
        lambda **_kwargs: (["internacoes"], ["internacoes"], _FakeContext()),
    )
    state = create_initial_messages_state(
        "Quantas mortes foram registradas?",
        session_id="test",
    )

    refreshed = schema_node._refresh_schema_context(
        state,
        'Binder Error: Referenced column "MORTE" not found',
        _RefreshLLMManager(),
    )

    assert refreshed is True
    assert calls["schema"] == 0
    assert state["schema_context"] == "TABLE internacoes\n- MORTE: BOOLEAN"
    assert state["response_metadata"]["schema_context_source"] == "llamaindex"
    assert state["response_metadata"]["schema_context_verified_with_db"] is False


def test_pytest_is_available_for_llamaindex_routing_tests():
    assert pytest
