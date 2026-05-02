"""SQL generation pipeline: schema, self-consistency, voting, and CoT planning."""

import concurrent.futures
import os
import time
from typing import Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from .llm_manager import get_llm_manager
from .prompt_builder import build_pregeneration_hints, build_sql_generation_messages
from .state_models import ExecutionPhase, MessagesStateTXT2SQL
from .state_helpers import add_ai_message, add_error, update_phase
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class SQLOutput(BaseModel):
    """Structured output for SQL generation."""

    sql: str = Field(description="Valid PostgreSQL SELECT query answering the user question")
    reasoning: str = Field(description="Brief explanation of table/filter choices (1-2 sentences)")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1; use <0.6 for uncertain queries",
    )


# ---------------------------------------------------------------------------
# Self-consistency: parallel candidate generation
# ---------------------------------------------------------------------------

N_SQL_CANDIDATES = 3
TEMPERATURE_CANDIDATES = 0.1
SEED_CANDIDATES = 42


def generate_sql_candidates(
    formatted_messages: list,
    llm_manager,
    primary_sql: str,
    primary_confidence: float,
    n: int = N_SQL_CANDIDATES,
) -> List[Dict]:
    """Generate N SQL candidates in parallel for majority voting."""
    candidates: List[Dict] = [{"sql": primary_sql, "confidence": primary_confidence}]

    if n <= 1:
        return candidates

    api_key = os.getenv("OPENAI_API_KEY")
    diverse_llm = ChatOpenAI(
        model=llm_manager.config.llm_model,
        temperature=TEMPERATURE_CANDIDATES,
        seed=SEED_CANDIDATES,
        api_key=api_key,
    ).with_structured_output(SQLOutput)

    def _one(_) -> Optional[Dict]:
        try:
            result = diverse_llm.invoke(formatted_messages)
            sql = llm_manager._clean_sql_query(result.sql)
            return {"sql": sql, "confidence": result.confidence} if sql else None
        except Exception as exc:
            logger.debug("Candidate generation failed", extra={"error": str(exc)})
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=n - 1) as pool:
        futures = [pool.submit(_one, index) for index in range(n - 1)]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result and result.get("sql"):
                candidates.append(result)

    logger.info(
        "SQL candidates generated",
        extra={"n_requested": n, "n_generated": len(candidates)},
    )
    return candidates


# ---------------------------------------------------------------------------
# Voting node (SelECT-SQL style self-consistency)
# ---------------------------------------------------------------------------

def _result_fingerprint(raw: str) -> str:
    """Normalise execution result for order-insensitive comparison."""
    lines = sorted(line.strip() for line in raw.strip().splitlines() if line.strip())
    return "\n".join(lines)


def _execute_safe(query_tool, sql: str) -> Optional[str]:
    """Execute a candidate SQL; return normalised fingerprint or None on error."""
    try:
        raw = query_tool.invoke(sql)
        if isinstance(raw, str):
            lower = raw.lower()
            error_tokens = [
                "does not exist", "syntax error", "error:", "psycopg2.errors",
                "invalid sql", "relation", "column", "não existe",
            ]
            if any(tok in lower for tok in error_tokens):
                return None
            return _result_fingerprint(raw)
        return None
    except Exception:
        return None


def vote_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """SQL Majority Voting Node — SelECT-SQL style self-consistency.

    Executes every candidate from state["sql_candidates"], groups by
    execution-result fingerprint, and promotes the majority winner to
    state["generated_sql"].  Falls back to the original primary SQL when:
      - fewer than 2 candidates are available
      - all candidates fail execution
      - the sql_db_query tool is unavailable
    """
    start_time = time.time()

    candidates: Optional[List[Dict]] = state.get("sql_candidates")

    if not candidates or len(candidates) < 2:
        logger.info("vote_sql: skipping — fewer than 2 candidates", extra={
            "n_candidates": len(candidates) if candidates else 0,
        })
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start_time)
        return state

    try:
        llm_manager = get_llm_manager()
        tools = llm_manager.get_sql_tools()
        query_tool = next((t for t in tools if t.name == "sql_db_query"), None)

        if not query_tool:
            logger.warning("vote_sql: sql_db_query tool not found, skipping vote")
            state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start_time)
            return state

        executed: List[Tuple[str, float, Optional[str]]] = []
        for c in candidates:
            sql = c.get("sql", "")
            confidence = c.get("confidence", 0.5)
            if not sql:
                continue
            fp = _execute_safe(query_tool, sql)
            executed.append((sql, confidence, fp))

        successful = [(sql, conf, fp) for sql, conf, fp in executed if fp is not None]

        if not successful:
            logger.warning("vote_sql: all candidates failed execution, keeping primary SQL")
            state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start_time)
            return state

        groups: Dict[str, List[Tuple[str, float]]] = {}
        for sql, conf, fp in successful:
            groups.setdefault(fp, []).append((sql, conf))

        majority_fp = max(groups, key=lambda k: (len(groups[k]), max(c for _, c in groups[k])))
        majority_size = len(groups[majority_fp])
        winner_sql, winner_conf = max(groups[majority_fp], key=lambda x: x[1])

        original_sql = state.get("generated_sql", "")
        changed = winner_sql != original_sql

        # Only override primary when winner has a clear majority (≥3 of 5 agree).
        PRIMARY_OVERRIDE_MIN_SIZE = 3
        if changed and majority_size < PRIMARY_OVERRIDE_MIN_SIZE:
            logger.warning(
                "vote_sql: winner group too small to override primary — keeping primary SQL",
                extra={"majority_size": majority_size, "threshold": PRIMARY_OVERRIDE_MIN_SIZE},
            )
            winner_sql = original_sql
            changed = False

        logger.info("vote_sql: voting complete", extra={
            "n_candidates": len(candidates),
            "n_successful": len(successful),
            "n_groups": len(groups),
            "majority_size": majority_size,
            "winner_confidence": winner_conf,
            "changed": changed,
            "winner_sql": winner_sql[:200],
        })

        if majority_size == 1:
            logger.warning(
                "vote_sql: no consensus — all candidates produced different results; "
                "using primary SQL",
                extra={"n_groups": len(groups)},
            )

        if changed:
            state["generated_sql"] = winner_sql

        meta = state.get("response_metadata", {}) or {}
        meta["voting"] = {
            "n_candidates": len(candidates),
            "n_successful": len(successful),
            "n_groups": len(groups),
            "majority_size": majority_size,
            "winner_confidence": winner_conf,
            "changed": changed,
            "consensus": majority_size > 1,
        }
        state["response_metadata"] = meta

        state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start_time)
        return state

    except Exception as e:
        logger.error("vote_sql: unexpected error, keeping primary SQL", extra={"error": str(e)})
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start_time)
        return state


# ---------------------------------------------------------------------------
# CoT planning node (runs before generate_sql_node)
# ---------------------------------------------------------------------------

_COT_SYSTEM_PROMPT = """\
Você é um especialista em SQL PostgreSQL para dados de saúde pública do DATASUS (SIH-RS).

Analise a pergunta do usuário e produza um PLANO SQL ESTRUTURADO em até 8 linhas para guiar a geração.
Indique:
1. Tabelas e colunas principais necessárias
2. Padrão SQL obrigatório (escolha um): CTE com média global → filtro local | ROW_NUMBER OVER PARTITION BY | CASE WHEN pivot colunas | NOT EXISTS anti-join | dois períodos em CTEs separadas + delta absoluto | subquery simples
3. Filtros e condições de escopo (HAVING, WHERE com threshold, filtros de valor)
4. Uma armadilha específica a evitar para esta pergunta

Seja direto e técnico. NÃO escreva SQL — apenas o plano textual.
"""


def reasoning_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """CoT SQL planning: generate a structured SQL sketch before generation."""
    start = time.time()

    user_query = state.get("user_query", "")
    plan_type = state.get("plan_type", "single_default")
    selected_tables = state.get("selected_tables", [])

    try:
        llm_manager = get_llm_manager()
        human_prompt = (
            f"Pergunta: {user_query}\n\n"
            f"Tipo de consulta detectado: {plan_type}\n"
            f"Tabelas selecionadas: {', '.join(selected_tables) if selected_tables else 'a determinar'}\n\n"
            "Produza o plano SQL estruturado:"
        )
        response = llm_manager.invoke_chat([
            SystemMessage(content=_COT_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ])
        reasoning_plan = response.content.strip() if hasattr(response, "content") else str(response)
        state["reasoning_plan"] = reasoning_plan
        logger.info("CoT reasoning plan generated", extra={
            "plan_type": plan_type,
            "plan_length": len(reasoning_plan),
        })
    except Exception as e:
        logger.warning("reasoning_node CoT failed — continuing without plan", extra={"error": str(e)})
        state["reasoning_plan"] = None

    state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start)
    return state


# ---------------------------------------------------------------------------
# Main generation node
# ---------------------------------------------------------------------------

def _build_pregeneration_hints(selected_tables, user_query):
    """Backward-compatible alias."""
    return build_pregeneration_hints(selected_tables, user_query)


def _generate_sql_candidates(
    formatted_messages: list,
    llm_manager,
    primary_sql: str,
    primary_confidence: float,
    n: int = 3,
):
    """Backward-compatible alias."""
    return generate_sql_candidates(
        formatted_messages=formatted_messages,
        llm_manager=llm_manager,
        primary_sql=primary_sql,
        primary_confidence=primary_confidence,
        n=n,
    )


def generate_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Generate SQL using ChatPromptTemplate with table-specific rules."""
    start_time = time.time()

    logger.info("SQL generation node started", extra={
        "user_query": state["user_query"][:100]
    })

    try:
        llm_manager = get_llm_manager()
        user_query = state["user_query"]
        schema_context = state.get("schema_context", "")
        selected_tables = state.get("selected_tables", [])

        reasoning_plan = state.get("reasoning_plan")
        if reasoning_plan:
            user_query = (
                f"{user_query}\n\n"
                f"[PLANO DE RACIOCÍNIO PRÉ-GERADO]\n"
                f"{reasoning_plan}\n"
                f"Siga este plano ao gerar o SQL."
            )

        logger.info("Tables selected for SQL generation", extra={"tables": selected_tables})

        ablation_flags = state.get("ablation_flags") or {}
        formatted_messages, pregeneration_hints = build_sql_generation_messages(
            user_query=user_query,
            schema_context=schema_context,
            selected_tables=selected_tables,
            ablation_flags=ablation_flags,
        )

        logger.debug("Template prepared", extra={
            "message_count": len(formatted_messages),
            "has_pregeneration_hints": bool(pregeneration_hints),
        })

        sql_query: Optional[str] = None
        generation_method = "structured"
        try:
            structured_result = llm_manager.invoke_chat_structured(formatted_messages, SQLOutput)
            sql_query = llm_manager._clean_sql_query(structured_result.sql)
            logger.info("SQL generated via structured output", extra={
                "sql": sql_query[:200],
                "reasoning": structured_result.reasoning[:120],
                "confidence": structured_result.confidence,
            })
            meta = state.get("response_metadata", {}) or {}
            meta["sql_generation_confidence"] = structured_result.confidence
            meta["sql_generation_reasoning"] = structured_result.reasoning
            state["response_metadata"] = meta
        except Exception as struct_err:
            logger.warning("Structured output failed, falling back to text parse", extra={
                "error": str(struct_err)
            })
            generation_method = "text_fallback"
            response = llm_manager.invoke_chat(formatted_messages)
            sql_query = response.content.strip() if hasattr(response, "content") else str(response)
            sql_query = llm_manager._clean_sql_query(sql_query)

        if sql_query:
            state["generated_sql"] = sql_query
            state["current_error"] = None
            state = add_ai_message(state, f"Generated SQL query ({generation_method}): {sql_query}")
            logger.info("SQL generated successfully", extra={
                "sql": sql_query[:200],
                "method": generation_method,
            })

            primary_confidence = (state.get("response_metadata", {}) or {}).get(
                "sql_generation_confidence", 0.5
            )
            if not ablation_flags.get("disable_self_consistency"):
                state["sql_candidates"] = generate_sql_candidates(
                    formatted_messages=formatted_messages,
                    llm_manager=llm_manager,
                    primary_sql=sql_query,
                    primary_confidence=primary_confidence,
                )
            else:
                state["sql_candidates"] = [{"sql": sql_query, "confidence": primary_confidence}]
        else:
            logger.warning("SQL generation: empty response on first attempt, trying simplified prompt")
            try:
                simplified_messages = [
                    SystemMessage(content=(
                        "You are a PostgreSQL expert. Generate ONLY a valid SQL SELECT query "
                        "for the Brazilian healthcare database sihrd5. "
                        "Return ONLY the SQL, no explanation.\n\n"
                        f"DATABASE SCHEMA:\n{schema_context}"
                    )),
                    HumanMessage(content=f"USER QUERY: {user_query}\n\nGenerate the SQL query:"),
                ]
                retry_response = llm_manager.invoke_chat(simplified_messages)
                retry_sql = retry_response.content.strip() if hasattr(retry_response, "content") else str(retry_response)
                retry_sql = llm_manager._clean_sql_query(retry_sql)
                if retry_sql:
                    state["generated_sql"] = retry_sql
                    state["current_error"] = None
                    state = add_ai_message(state, f"Generated SQL (simplified retry): {retry_sql}")
                    logger.info("SQL generated on retry", extra={"sql": retry_sql[:200]})
                else:
                    raise ValueError("Retry also produced empty SQL")
            except Exception as retry_err:
                error_message = "Failed to generate SQL query - empty response (all attempts)"
                state = add_error(state, error_message, "sql_generation_error", ExecutionPhase.SQL_GENERATION)
                state["retry_count"] = state.get("retry_count", 0) + 1
                state["generation_retry_count"] = state.get("generation_retry_count", 0) + 1
                logger.warning("SQL generation failed on all attempts", extra={"error": str(retry_err)})

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)

        logger.info("SQL generation completed", extra={"execution_time": execution_time})

        return state

    except Exception as e:
        error_message = f"SQL generation failed: {str(e)}"
        state = add_error(state, error_message, "sql_generation_error", ExecutionPhase.SQL_GENERATION)
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["generation_retry_count"] = state.get("generation_retry_count", 0) + 1

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)

        logger.error("SQL generation failed", extra={
            "error": str(e),
            "execution_time": execution_time,
        })

        return state


__all__ = [
    "SQLOutput",
    "N_SQL_CANDIDATES",
    "SEED_CANDIDATES",
    "TEMPERATURE_CANDIDATES",
    "generate_sql_candidates",
    "vote_sql_node",
    "reasoning_node",
    "_build_pregeneration_hints",
    "_generate_sql_candidates",
    "build_sql_generation_messages",
    "generate_sql_node",
]
