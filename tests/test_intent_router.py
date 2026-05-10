from types import SimpleNamespace
from unittest.mock import patch

from src.agent import intent_router


class _StubRouter:
    def __init__(self, response):
        self._response = response

    def __call__(self, _query):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _patched_router(stub):
    """Drop the cached router so each test gets a clean stub."""
    intent_router._router_instance = None
    return patch.object(intent_router, "get_router", return_value=stub)


def test_returns_route_when_router_picks_one():
    stub = _StubRouter(SimpleNamespace(name="DATABASE", similarity_score=0.81))
    with _patched_router(stub):
        result = intent_router.classify_intent("Quantos obitos em 2023?")

    assert result.route == "DATABASE"
    assert result.score == 0.81
    assert result.fallback_reason is None


def test_routes_meta_query_to_conversational():
    stub = _StubRouter(SimpleNamespace(name="CONVERSATIONAL", similarity_score=0.62))
    with _patched_router(stub):
        result = intent_router.classify_intent(
            "me de ideias de graficos para fazer usando a base de dados"
        )

    assert result.route == "CONVERSATIONAL"
    assert result.score == 0.62


def test_returns_no_route_when_router_returns_none_name():
    stub = _StubRouter(SimpleNamespace(name=None, similarity_score=None))
    with _patched_router(stub):
        result = intent_router.classify_intent("alguma coisa qualquer")

    assert result.route is None
    assert result.fallback_reason == "no_route_above_threshold"


def test_returns_fallback_when_router_init_fails():
    intent_router._router_instance = None
    with patch.object(intent_router, "get_router", side_effect=RuntimeError("no api key")):
        result = intent_router.classify_intent("qualquer coisa")

    assert result.route is None
    assert "router_init_error" in (result.fallback_reason or "")


def test_returns_fallback_when_router_call_raises():
    stub = _StubRouter(RuntimeError("boom"))
    with _patched_router(stub):
        result = intent_router.classify_intent("qualquer coisa")

    assert result.route is None
    assert "router_call_error" in (result.fallback_reason or "")


def test_empty_query_skips_router_call():
    intent_router._router_instance = None
    with patch.object(intent_router, "get_router") as get_router_mock:
        result = intent_router.classify_intent("   ")
    get_router_mock.assert_not_called()
    assert result.route is None
    assert result.fallback_reason == "empty_query"


def test_database_utterances_cover_chart_data_questions():
    assert any(
        "internacoes" in utterance.lower()
        for utterance in intent_router._DATABASE_UTTERANCES
    )


def test_conversational_utterances_cover_meta_queries():
    meta_phrases = ("ideias", "que tipos", "sugira", "que insights", "o que posso")
    matches = sum(
        1
        for phrase in meta_phrases
        if any(phrase in utterance.lower() for utterance in intent_router._CONVERSATIONAL_UTTERANCES)
    )
    assert matches >= 3, "router should ground at least 3 meta-style examples"


def test_schema_utterances_cover_structure_questions():
    assert any(
        keyword in utterance.lower()
        for utterance in intent_router._SCHEMA_UTTERANCES
        for keyword in ("tabelas", "colunas", "schema", "estrutura")
    )
