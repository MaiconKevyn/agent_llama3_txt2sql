import pytest

# Skip if langgraph not installed (nodes/state depend on it)
pytest.importorskip("langgraph")

import src.agent.classification as classification_module
import src.agent.nodes as nodes
from src.agent.state_helpers import create_initial_messages_state
from src.agent.state_models import QueryRoute


class DummyResp:
    def __init__(self, content):
        self.content = content


class DummyLLM:
    def invoke(self, messages):
        # Last human message content contains the user query
        user = None
        for m in messages[::-1]:
            if getattr(m, "type", None) == "human":
                user = m.content
                break
        # Simple routing based on query text for test purposes
        if user and "o que significa" in user.lower():
            return DummyResp('{"route":"CONVERSATIONAL","confidence":0.9,"reasons":"definição"}')
        if user and "tabelas" in user.lower():
            return DummyResp('{"route":"SCHEMA","confidence":0.9,"reasons":"estrutura"}')
        return DummyResp('{"route":"DATABASE","confidence":0.9,"reasons":"contagem"}')


class DummyLLMManager:
    def __init__(self):
        self._llm = DummyLLM()

    def get_bound_llm(self):
        return self._llm

    def invoke_chat(self, messages):
        return self._llm.invoke(messages)


def test_classification_node_database(monkeypatch):
    monkeypatch.setattr(classification_module, "get_llm_manager", lambda: DummyLLMManager())

    state = create_initial_messages_state("Quantos óbitos ocorreram?", session_id="s1")
    new_state = nodes.query_classification_node(state)

    assert new_state["classification"].route == QueryRoute.DATABASE
    assert new_state["classification"].confidence_score >= 0.7


def test_classification_node_conversational(monkeypatch):
    monkeypatch.setattr(classification_module, "get_llm_manager", lambda: DummyLLMManager())

    state = create_initial_messages_state("O que significa o CID J189?", session_id="s2")
    new_state = nodes.query_classification_node(state)

    assert new_state["classification"].route == QueryRoute.CONVERSATIONAL
    assert new_state["classification"].confidence_score >= 0.7


def test_classification_node_schema(monkeypatch):
    monkeypatch.setattr(classification_module, "get_llm_manager", lambda: DummyLLMManager())

    state = create_initial_messages_state("Quais tabelas existem no banco?", session_id="s3")
    new_state = nodes.query_classification_node(state)

    assert new_state["classification"].route == QueryRoute.SCHEMA
    assert new_state["classification"].confidence_score >= 0.7


def test_classification_node_detects_explicit_sql(monkeypatch):
    # Even if LLM says conversational, presence of SQL snippet should force DATABASE early
    class ConversationalLLM(DummyLLM):
        def invoke(self, messages):
            return DummyResp('{"route":"CONVERSATIONAL","confidence":0.9,"reasons":"texto"}')

    class Mgr:
        def __init__(self):
            self._llm = ConversationalLLM()

        def get_bound_llm(self):
            return self._llm

        def invoke_chat(self, messages):
            return self._llm.invoke(messages)

    monkeypatch.setattr(classification_module, "get_llm_manager", lambda: Mgr())

    state = create_initial_messages_state("```sql\nSELECT 1;\n```", session_id="s4")
    new_state = nodes.query_classification_node(state)

    assert new_state["classification"].route == QueryRoute.DATABASE


def test_classification_node_routes_health_analytic_difference_to_database(monkeypatch):
    class ConversationalLLM(DummyLLM):
        def invoke(self, messages):
            return DummyResp('{"route":"CONVERSATIONAL","confidence":0.95,"reasons":"diferença"}')

    class Mgr:
        def __init__(self):
            self._llm = ConversationalLLM()

        def get_bound_llm(self):
            return self._llm

        def invoke_chat(self, messages):
            return self._llm.invoke(messages)

    monkeypatch.setattr(classification_module, "get_llm_manager", lambda: Mgr())

    state = create_initial_messages_state(
        "Existe diferença de mortalidade entre homens e mulheres?",
        session_id="s-analytic-route",
    )
    new_state = nodes.query_classification_node(state)

    assert new_state["classification"].route == QueryRoute.DATABASE


def test_classification_node_routes_explicit_chart_columns_to_database(monkeypatch):
    class SchemaLLM(DummyLLM):
        def invoke(self, messages):
            return DummyResp('{"route":"SCHEMA","confidence":0.95,"reasons":"colunas"}')

    class Mgr:
        def __init__(self):
            self._llm = SchemaLLM()

        def get_bound_llm(self):
            return self._llm

        def invoke_chat(self, messages):
            return self._llm.invoke(messages)

    monkeypatch.setattr(classification_module, "get_llm_manager", lambda: Mgr())

    state = create_initial_messages_state(
        "Mostre um grafico de colunas com internacoes por estado.",
        session_id="s5",
        visualization_intent={"requested": True, "chart_hint": "bar"},
    )
    new_state = nodes.query_classification_node(state)

    assert new_state["classification"].route == QueryRoute.DATABASE
