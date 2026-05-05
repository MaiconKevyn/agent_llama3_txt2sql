import pytest

pytest.importorskip("langgraph")

from src.agent.state_helpers import create_initial_messages_state
from src.agent.state_models import ExecutionPhase


def test_execute_sql_node_blocks_non_select(monkeypatch):
    """execute_sql_node deve bloquear DDL/DML antes de tocar em ferramentas."""
    # Import tardio para permitir monkeypatch de get_llm_manager dentro de nodes
    import src.agent.nodes as nodes

    # Monkeypatch get_llm_manager para não inicializar nada pesado
    class DummyLLMManager:
        pass

    monkeypatch.setattr(nodes, "get_llm_manager", lambda: DummyLLMManager())

    # Criar estado inicial e injetar SQL inválido
    state = create_initial_messages_state(user_query="teste", session_id="s1")
    state["validated_sql"] = "DROP TABLE t;"
    state["current_phase"] = ExecutionPhase.SQL_EXECUTION
    new_state = nodes.execute_sql_node(state)

    # Deve registrar erro e não executar
    assert new_state["current_error"]
    assert any(
        "blocked" in (err.get("message", "").lower()) for err in new_state["errors"]
    ) or "blocked" in (new_state.get("current_error", "").lower())


def test_llm_manager_execute_sql_query_blocks_non_select():
    """OpenAILLMManager.execute_sql_query deve bloquear DDL/DML (sem DB real)."""
    from src.agent.llm_manager import OpenAILLMManager

    # Criar instância sem __init__ para evitar inicialização pesada
    inst = OpenAILLMManager.__new__(OpenAILLMManager)
    # Simular que há um database inicializado (qualquer objeto não-None serve para passar pela checagem)
    inst._sql_database = object()

    result = OpenAILLMManager.execute_sql_query(inst, "UPDATE t SET a=1;")
    assert result["success"] is False
    assert "blocked" in result.get("error", "").lower()


def test_parse_tool_result_rows_expands_stringified_tuple_list():
    from src.agent.execution import _parse_tool_result_rows

    rows = _parse_tool_result_rows("[(2772299, 109261), (2457121, 89982)]")

    assert len(rows) == 2
    assert rows[0]["result"] == (2772299, 109261)


def test_parse_tool_result_rows_keeps_multiline_fallback():
    from src.agent.execution import _parse_tool_result_rows

    rows = _parse_tool_result_rows("first row\nsecond row")

    assert rows == [{"result": "first row"}, {"result": "second row"}]
