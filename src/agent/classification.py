"""Query classification node — routes queries to DATABASE / CONVERSATIONAL / SCHEMA."""

import time
from typing import Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .llm_manager import OpenAILLMManager, get_llm_manager
from .state_models import MessagesStateTXT2SQL, QueryRoute, ExecutionPhase, QueryClassification
from .state_helpers import add_ai_message, update_phase, add_error, clean_conversation_messages
from ..utils.logging_config import get_nodes_logger
from ..utils.classification import (
    detect_sql_snippets,
    heuristic_route,
    try_extract_json_block,
    combine_scores,
)

logger = get_nodes_logger()

# Prefixes/words that strongly indicate a follow-up turn in Portuguese
_FOLLOWUP_PREFIXES = ("e ", "e se ", "e para ", "mas ", "também ", "quais foram", "qual foi")
_FOLLOWUP_ANAPHORA = ("isso", "disso", "esse", "essa", "esses", "essas", "mesmo", "mesma",
                      "anterior", "delas", "deles", "tal", "acima", "abaixo")


def _extract_prior_context(messages: list) -> Tuple[Optional[str], Optional[str]]:
    """Return (prior_human_query, prior_ai_final_response) from accumulated messages.

    Uses clean_conversation_messages to strip workflow artifacts, then scans
    backwards for the most recent (human, ai) pair before the current turn.
    """
    # Strip internal markers and apply sliding window, then exclude last message
    # (the current HumanMessage that triggered this classification)
    clean = clean_conversation_messages(messages[:-1])

    prior_ai: Optional[str] = None
    prior_human: Optional[str] = None

    for msg in reversed(clean):
        if isinstance(msg, AIMessage) and prior_ai is None:
            prior_ai = msg.content
        elif isinstance(msg, HumanMessage) and prior_ai is not None:
            prior_human = msg.content
            break

    return prior_human, prior_ai


def _is_followup(query: str, prior_human: Optional[str]) -> bool:
    """Heuristic: return True when the query looks like a follow-up turn."""
    if prior_human is None:
        return False
    q = query.lower().strip()
    if len(q) < 50 and q.startswith(_FOLLOWUP_PREFIXES):
        return True
    if any(ref in q for ref in _FOLLOWUP_ANAPHORA):
        return True
    return False


def query_classification_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Query Classification Node - Official LangGraph Pattern

    Classifies user queries to determine routing:
    - DATABASE: Requires SQL generation and execution
    - CONVERSATIONAL: Direct LLM response
    - SCHEMA: Schema introspection queries

    Following LangGraph SQL Agent tutorial classification approach
    """
    start_time = time.time()

    logger.info("Classification node started")

    try:
        # Extract user query from different possible state formats
        user_query = None

        if "user_query" in state:
            user_query = state["user_query"]
        elif "messages" in state and state["messages"]:
            for msg in reversed(state["messages"]):
                if hasattr(msg, 'type') and msg.type == 'human':
                    user_query = msg.content
                    break
                elif isinstance(msg, dict) and msg.get('type') == 'human':
                    user_query = msg.get('content', '')
                    break
                elif isinstance(msg, dict) and msg.get('role') == 'human':
                    user_query = msg.get('content', '')
                    break

        if not user_query:
            logger.debug("State parsing failed", extra={"state_keys": list(state.keys())})
            if "messages" in state:
                logger.debug("Messages found in state", extra={"messages": str(state['messages'])})
            raise ValueError("No user query found in state")

        logger.info("User query extracted", extra={"query": user_query[:100]})

        if "user_query" not in state:
            state["user_query"] = user_query

        # ------------------------------------------------------------------ #
        # Multi-turn: resolve anaphoric follow-up queries before classifying  #
        # ------------------------------------------------------------------ #
        messages_history = state.get("messages", [])
        prior_human, prior_ai = _extract_prior_context(messages_history)

        if _is_followup(user_query, prior_human):
            llm_manager = get_llm_manager()
            resolve_messages = [
                SystemMessage(content=(
                    "Reescreva a PERGUNTA ATUAL como uma pergunta autossuficiente, "
                    "incorporando o contexto da conversa anterior. "
                    "Responda APENAS com a pergunta reescrita, sem explicações adicionais."
                )),
                HumanMessage(content=(
                    f"Pergunta anterior: {prior_human}\n"
                    f"Resposta anterior (resumo): {prior_ai[:300] if prior_ai else ''}\n"
                    f"Pergunta atual: {user_query}"
                )),
            ]
            resolved_response = llm_manager.invoke_chat(resolve_messages)
            resolved_query = getattr(resolved_response, "content", user_query).strip()
            if resolved_query and resolved_query != user_query:
                logger.info(
                    "Follow-up resolved",
                    extra={"original": user_query, "resolved": resolved_query}
                )
                user_query = resolved_query
                state["user_query"] = resolved_query

        # Heuristic pre-pass
        heur_route_str, heur_scores = heuristic_route(user_query)

        HEURISTIC_SKIP_THRESHOLD = 2
        if detect_sql_snippets(user_query):
            query_route = QueryRoute.DATABASE
            confidence_score = 0.95
            reasoning = "Explicit SQL detected in input."
        elif (
            heur_scores.get("DATABASE", 0) >= HEURISTIC_SKIP_THRESHOLD
            and heur_route_str == "DATABASE"
            and heur_scores.get("CONVERSATIONAL", 0) == 0
            and heur_scores.get("SCHEMA", 0) == 0
        ):
            query_route = QueryRoute.DATABASE
            confidence_score = 0.9
            reasoning = (
                f"Heuristic fast-path: route=DATABASE, score={heur_scores.get('DATABASE', 0)}, skipping LLM"
            )
            logger.info(
                f"Heuristic fast-path: route=DATABASE, score={heur_scores.get('DATABASE', 0)}, skipping LLM"
            )
        elif (
            heur_scores.get("DATABASE", 0) >= 1
            and heur_scores.get("CONVERSATIONAL", 0) == 0
            and heur_scores.get("SCHEMA", 0) == 0
        ):
            query_route = QueryRoute.DATABASE
            confidence_score = 0.8
            reasoning = (
                f"Heuristic soft fast-path: DATABASE≥1, no CONV/SCHEMA signals, "
                f"score={heur_scores.get('DATABASE', 0)}, skipping LLM"
            )
            logger.info(reasoning)
        else:
            llm_manager = get_llm_manager()
            system_prompt = (
                "Você é um classificador de consultas. Decida a ROTA em {DATABASE, CONVERSATIONAL, SCHEMA}.\n"
                "Responda APENAS em JSON com campos: {\\\"route\\\":<string>,\\\"confidence\\\":<float>,\\\"reasons\\\":<string>}\n"
                "DATABASE: perguntas de dados (contagem, ranking, listar, filtros, por cidade/ano/sexo...)\n"
                "CONVERSATIONAL: explicações/definições (\\\"o que é\\\", \\\"significa\\\", \\\"como funciona\\\", diferenças)\n"
                "SCHEMA: estrutura do banco (tabelas, colunas, schema, dicionário de dados).\n"
                "Exemplos:\n"
                "Q: Quantos óbitos ocorreram em 2023?\n"
                "A: {\\\"route\\\":\\\"DATABASE\\\",\\\"confidence\\\":0.9,\\\"reasons\\\":\\\"contagem temporal\\\"}\n"
                "Q: O que significa o CID J189?\n"
                "A: {\\\"route\\\":\\\"CONVERSATIONAL\\\",\\\"confidence\\\":0.9,\\\"reasons\\\":\\\"pedido de definição\\\"}\n"
                "Q: Quais colunas existem na tabela internacoes?\n"
                "A: {\\\"route\\\":\\\"SCHEMA\\\",\\\"confidence\\\":0.95,\\\"reasons\\\":\\\"estrutura da tabela\\\"}"
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query),
            ]

            response = llm_manager.invoke_chat(messages)
            content = getattr(response, "content", str(response))
            data = try_extract_json_block(content)

            llm_route = None
            llm_conf = None
            llm_reasons = ""
            if isinstance(data, dict):
                r = str(data.get("route", "")).upper().strip()
                if r in ["DATABASE", "CONVERSATIONAL", "SCHEMA"]:
                    llm_route = r
                try:
                    llm_conf = float(data.get("confidence", None))
                except Exception:
                    llm_conf = None
                llm_reasons = str(data.get("reasons", "")).strip()

            threshold = 0.75
            if llm_route and llm_conf is not None and llm_conf >= threshold:
                final_route_str = llm_route
                confidence_score = float(llm_conf)
                reasoning = f"LLM(JSON) high confidence. Heuristic={heur_scores}"
            else:
                final_route_str = combine_scores(llm_route, llm_conf, heur_scores, w_llm=0.7)
                confidence_score = float(llm_conf) if llm_conf is not None else (
                    1.0 if heur_scores.get(final_route_str, 0) > 0 else 0.6
                )
                reasoning = (
                    f"Hybrid decision. llm_route={llm_route} conf={llm_conf} heur={heur_scores}"
                    + (f"; llm_reasons={llm_reasons}" if llm_reasons else "")
                )

            query_route = {
                "DATABASE": QueryRoute.DATABASE,
                "CONVERSATIONAL": QueryRoute.CONVERSATIONAL,
                "SCHEMA": QueryRoute.SCHEMA,
            }[final_route_str]

        classification = QueryClassification(
            route=query_route,
            confidence_score=confidence_score,
            reasoning=reasoning,
            requires_tools=query_route in [QueryRoute.DATABASE, QueryRoute.SCHEMA],
            estimated_complexity=0.5 if query_route == QueryRoute.CONVERSATIONAL else 0.8,
            suggested_approach=f"Use {query_route.value} processing pipeline",
        )

        state["query_route"] = query_route
        state["classification"] = classification
        state["requires_sql"] = query_route == QueryRoute.DATABASE

        ai_response = f"Query classified as {query_route.value} (confidence: {confidence_score:.1f})"
        state = add_ai_message(state, ai_response)

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.QUERY_CLASSIFICATION, execution_time)

        logger.info("Query classified successfully", extra={
            "result": query_route.value,
            "confidence": confidence_score,
            "execution_time": execution_time,
            "route_type": "SQL Pipeline" if query_route == QueryRoute.DATABASE else "Direct Response",
        })

        return state

    except Exception as e:
        error_message = f"Query classification failed: {str(e)}"
        state = add_error(state, error_message, "classification_error", ExecutionPhase.QUERY_CLASSIFICATION)

        state["query_route"] = QueryRoute.DATABASE
        state["requires_sql"] = True
        state["classification"] = QueryClassification(
            route=QueryRoute.DATABASE,
            confidence_score=0.5,
            reasoning="Fallback classification due to error",
            requires_tools=True,
            estimated_complexity=0.8,
            suggested_approach="Use database processing pipeline",
        )

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.QUERY_CLASSIFICATION, execution_time)

        return state
