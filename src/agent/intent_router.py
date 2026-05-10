"""Semantic intent router (semantic-router + OpenAI embeddings).

Replaces the brittle keyword-list classifier as the primary route picker.
Falls back to the existing hybrid heuristic + LLM classifier when the
semantic match score is below ``MIN_SIMILARITY``.

Routes:
    - DATABASE      → SQL pipeline (counts, rankings, filters, charts on data)
    - CONVERSATIONAL → free-form LLM answer (definitions, ideas, suggestions,
                       meta/exploratory prompts like "give me chart ideas")
    - SCHEMA        → table/column structure introspection
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()

MIN_SIMILARITY = 0.40

ROUTE_NAMES = ("DATABASE", "CONVERSATIONAL", "SCHEMA")

_DATABASE_UTTERANCES = (
    "Quais sao os 10 municipios com mais internacoes?",
    "Quantos obitos ocorreram em 2023?",
    "Qual a taxa de mortalidade hospitalar por estado?",
    "Liste as 5 principais causas de morte por sexo",
    "Total de internacoes por ano nos ultimos 5 anos",
    "Mortes entre homens e mulheres por faixa etaria",
    "Distribuicao de procedimentos cirurgicos por hospital",
    "Gere um grafico de barras das internacoes por municipio",
    "Idade media dos pacientes que morreram",
    "Ranking de hospitais por numero de pacientes atendidos",
)

_CONVERSATIONAL_UTTERANCES = (
    "O que significa o CID J189?",
    "Qual a diferenca entre internacao e atendimento?",
    "Como funciona a classificacao de raca cor no SUS?",
    "O que e a base de dados SIH-RS?",
    "Explique o que e taxa de mortalidade hospitalar",
    "Por que algumas mortes nao tem CID registrado?",
    # Meta / exploratory prompts (the case that misrouted today):
    "Me de ideias de graficos para fazer com essa base",
    "Que tipos de analise eu posso explorar nessa base?",
    "Sugira algumas perguntas que eu posso fazer ao agente",
    "Quais perguntas interessantes posso fazer com esses dados?",
    "Que insights eu consigo extrair desse banco?",
    "Me ajude a comecar, o que posso pesquisar aqui?",
    "Que tipo de perguntas eu posso fazer?",
    "Que perguntas de exemplo voce sugere?",
    "Quais sao bons exemplos de pergunta para esse banco?",
    "Como eu posso usar esse agente?",
    "Para que serve esse sistema?",
    "Quais analises sao possiveis com esses dados?",
)

_SCHEMA_UTTERANCES = (
    "Quais tabelas existem no banco?",
    "Quais colunas a tabela internacoes tem?",
    "Mostre o schema da tabela municipios",
    "Descreva a estrutura da tabela cid",
    "Quais campos existem em socioeconomico?",
    "Mostre o dicionario de dados",
    "Como esta organizado o banco de dados?",
    "Liste as tabelas disponiveis e seus relacionamentos",
)


@dataclass
class IntentRouterResult:
    """Outcome of a semantic-router classification."""

    route: Optional[str]
    score: Optional[float]
    matched_utterance: Optional[str] = None
    fallback_reason: Optional[str] = None


_router_lock = threading.Lock()
_router_instance = None  # type: ignore[var-annotated]


def _build_router():
    """Build the semantic router lazily — encoder needs OPENAI_API_KEY."""

    from semantic_router import Route
    from semantic_router.encoders import OpenAIEncoder
    from semantic_router.routers import SemanticRouter

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; semantic router requires it.")

    routes = [
        Route(name="DATABASE", utterances=list(_DATABASE_UTTERANCES), score_threshold=MIN_SIMILARITY),
        Route(
            name="CONVERSATIONAL",
            utterances=list(_CONVERSATIONAL_UTTERANCES),
            score_threshold=MIN_SIMILARITY,
        ),
        Route(name="SCHEMA", utterances=list(_SCHEMA_UTTERANCES), score_threshold=MIN_SIMILARITY),
    ]

    encoder = OpenAIEncoder(name="text-embedding-3-small")
    return SemanticRouter(encoder=encoder, routes=routes, auto_sync="local")


def get_router():
    """Singleton accessor for the semantic router."""

    global _router_instance
    if _router_instance is not None:
        return _router_instance
    with _router_lock:
        if _router_instance is None:
            _router_instance = _build_router()
    return _router_instance


def classify_intent(user_query: str) -> IntentRouterResult:
    """Run the semantic router. Returns ``IntentRouterResult`` with a route name
    if the top utterance scored above ``MIN_SIMILARITY``; otherwise the route is
    ``None`` and ``fallback_reason`` is set so callers can defer to the LLM
    classifier.
    """

    if not user_query or not user_query.strip():
        return IntentRouterResult(route=None, score=None, fallback_reason="empty_query")

    try:
        router = get_router()
    except Exception as exc:
        logger.warning("Semantic router unavailable; falling back", extra={"error": str(exc)})
        return IntentRouterResult(route=None, score=None, fallback_reason=f"router_init_error: {exc}")

    try:
        choice = router(user_query)
    except Exception as exc:
        logger.warning("Semantic router call failed; falling back", extra={"error": str(exc)})
        return IntentRouterResult(route=None, score=None, fallback_reason=f"router_call_error: {exc}")

    route_name = getattr(choice, "name", None)
    if route_name is None:
        return IntentRouterResult(
            route=None,
            score=None,
            fallback_reason="no_route_above_threshold",
        )

    similarity_score = getattr(choice, "similarity_score", None)
    return IntentRouterResult(
        route=route_name,
        score=float(similarity_score) if similarity_score is not None else None,
        matched_utterance=getattr(choice, "function_call", None),
    )
