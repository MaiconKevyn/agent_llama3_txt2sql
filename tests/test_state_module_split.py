import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from src.agent.state_helpers import create_initial_messages_state
from src.agent.state_models import ExecutionPhase, MessagesStateTXT2SQL


def test_state_models_exports_core_types():
    assert MessagesStateTXT2SQL.__name__ == "MessagesStateTXT2SQL"
    assert ExecutionPhase.INITIALIZATION.value == "initialization"


def test_state_helpers_create_typed_state():
    initial_state = create_initial_messages_state("consulta", session_id="s2")

    assert isinstance(initial_state, dict)
    assert initial_state["current_phase"] == ExecutionPhase.INITIALIZATION
    assert initial_state["execution_mode"] == "single"


def test_state_helpers_create_initial_state_message():
    initial_state = create_initial_messages_state("teste", session_id="s1")
    assert initial_state["messages"][0].__class__.__name__ == "HumanMessage"
