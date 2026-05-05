"""SQL generation pipeline: schema, CoT planning, and structured output."""

import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..utils.logging_config import get_nodes_logger
from .llm_manager import get_llm_manager
from .prompt_builder import build_pregeneration_hints, build_sql_generation_messages
from .state_helpers import add_ai_message, add_error, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL

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
        response = llm_manager.invoke_chat(
            [
                SystemMessage(content=_COT_SYSTEM_PROMPT),
                HumanMessage(content=human_prompt),
            ]
        )
        reasoning_plan = response.content.strip() if hasattr(response, "content") else str(response)
        state["reasoning_plan"] = reasoning_plan
        logger.info(
            "CoT reasoning plan generated",
            extra={
                "plan_type": plan_type,
                "plan_length": len(reasoning_plan),
            },
        )
    except Exception as e:
        logger.warning(
            "reasoning_node CoT failed — continuing without plan", extra={"error": str(e)}
        )
        state["reasoning_plan"] = None

    state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start)
    return state


# ---------------------------------------------------------------------------
# Main generation node
# ---------------------------------------------------------------------------


def _build_pregeneration_hints(selected_tables, user_query):
    """Backward-compatible alias."""
    return build_pregeneration_hints(selected_tables, user_query)


def generate_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Generate SQL using ChatPromptTemplate with table-specific rules."""
    start_time = time.time()

    logger.info("SQL generation node started", extra={"user_query": state["user_query"][:100]})

    try:
        llm_manager = get_llm_manager()
        user_query = state["user_query"]
        schema_context = state.get("schema_context", "")
        selected_tables = state.get("selected_tables", [])
        semantic_plan = state.get("semantic_plan")

        reasoning_plan = state.get("reasoning_plan")
        if reasoning_plan:
            user_query = (
                f"{user_query}\n\n"
                f"[PLANO DE RACIOCÍNIO PRÉ-GERADO]\n"
                f"{reasoning_plan}\n"
                f"Siga este plano ao gerar o SQL."
            )
        if semantic_plan:
            try:
                from ..semantic.catalog import render_catalog_context_for_plan
                from ..semantic.plan_schema import SemanticPlan

                parsed_plan = SemanticPlan.model_validate(semantic_plan)
                semantic_prompt = parsed_plan.to_prompt_block()
                catalog_prompt = render_catalog_context_for_plan(parsed_plan)
                if catalog_prompt.strip() != "[SEMANTIC CATALOG CONTEXT]":
                    semantic_prompt = f"{semantic_prompt}\n\n{catalog_prompt}"
            except Exception:
                semantic_prompt = f"[SEMANTIC PLAN - SQL MUST SATISFY]\n{semantic_plan}"
            user_query = (
                f"{user_query}\n\n"
                f"{semantic_prompt}\n"
                "Antes de escrever a SQL, preserve métricas, dimensões, filtros, granularidade e shape desse plano."
            )

        logger.info("Tables selected for SQL generation", extra={"tables": selected_tables})

        ablation_flags = state.get("ablation_flags") or {}
        formatted_messages, pregeneration_hints = build_sql_generation_messages(
            user_query=user_query,
            schema_context=schema_context,
            selected_tables=selected_tables,
            ablation_flags=ablation_flags,
        )

        logger.debug(
            "Template prepared",
            extra={
                "message_count": len(formatted_messages),
                "has_pregeneration_hints": bool(pregeneration_hints),
            },
        )

        sql_query: str | None = None
        generation_method = "structured"
        try:
            structured_result = llm_manager.invoke_chat_structured(formatted_messages, SQLOutput)
            sql_query = llm_manager._clean_sql_query(structured_result.sql)
            logger.info(
                "SQL generated via structured output",
                extra={
                    "sql": sql_query[:200],
                    "reasoning": structured_result.reasoning[:120],
                    "confidence": structured_result.confidence,
                },
            )
            meta = state.get("response_metadata", {}) or {}
            meta["sql_generation_confidence"] = structured_result.confidence
            meta["sql_generation_reasoning"] = structured_result.reasoning
            state["response_metadata"] = meta
        except Exception as struct_err:
            logger.warning(
                "Structured output failed, falling back to text parse",
                extra={"error": str(struct_err)},
            )
            generation_method = "text_fallback"
            response = llm_manager.invoke_chat(formatted_messages)
            sql_query = response.content.strip() if hasattr(response, "content") else str(response)
            sql_query = llm_manager._clean_sql_query(sql_query)

        if sql_query:
            state["generated_sql"] = sql_query
            state["current_error"] = None
            state = add_ai_message(state, f"Generated SQL query ({generation_method}): {sql_query}")
            logger.info(
                "SQL generated successfully",
                extra={
                    "sql": sql_query[:200],
                    "method": generation_method,
                },
            )

        else:
            logger.warning(
                "SQL generation: empty response on first attempt, trying simplified prompt"
            )
            try:
                simplified_messages = [
                    SystemMessage(
                        content=(
                            "You are a PostgreSQL expert. Generate ONLY a valid SQL SELECT query "
                            "for the Brazilian healthcare database sihrd5. "
                            "Return ONLY the SQL, no explanation.\n\n"
                            f"DATABASE SCHEMA:\n{schema_context}"
                        )
                    ),
                    HumanMessage(content=f"USER QUERY: {user_query}\n\nGenerate the SQL query:"),
                ]
                retry_response = llm_manager.invoke_chat(simplified_messages)
                retry_sql = (
                    retry_response.content.strip()
                    if hasattr(retry_response, "content")
                    else str(retry_response)
                )
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
                state = add_error(
                    state, error_message, "sql_generation_error", ExecutionPhase.SQL_GENERATION
                )
                state["retry_count"] = state.get("retry_count", 0) + 1
                state["generation_retry_count"] = state.get("generation_retry_count", 0) + 1
                logger.warning(
                    "SQL generation failed on all attempts", extra={"error": str(retry_err)}
                )

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)

        logger.info("SQL generation completed", extra={"execution_time": execution_time})

        return state

    except Exception as e:
        error_message = f"SQL generation failed: {str(e)}"
        state = add_error(
            state, error_message, "sql_generation_error", ExecutionPhase.SQL_GENERATION
        )
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["generation_retry_count"] = state.get("generation_retry_count", 0) + 1

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)

        logger.error(
            "SQL generation failed",
            extra={
                "error": str(e),
                "execution_time": execution_time,
            },
        )

        return state


__all__ = [
    "SQLOutput",
    "reasoning_node",
    "_build_pregeneration_hints",
    "build_sql_generation_messages",
    "generate_sql_node",
]
