"""SQL generation node and compatibility exports."""

import time
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .llm_manager import get_llm_manager
from .prompt_builder import build_pregeneration_hints, build_sql_generation_messages
from .schemas import SQLOutput
from .self_consistency import generate_sql_candidates
from .state import (
    ExecutionPhase,
    MessagesStateTXT2SQL,
    add_ai_message,
    add_error,
    update_phase,
)
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()


def _build_pregeneration_hints(selected_tables, user_query):
    """Backward-compatible alias for extracted prompt warnings."""
    return build_pregeneration_hints(selected_tables, user_query)


def _generate_sql_candidates(
    formatted_messages: list,
    llm_manager,
    primary_sql: str,
    primary_confidence: float,
    n: int = 3,
):
    """Backward-compatible alias for extracted self-consistency generation."""
    return generate_sql_candidates(
        formatted_messages=formatted_messages,
        llm_manager=llm_manager,
        primary_sql=primary_sql,
        primary_confidence=primary_confidence,
        n=n,
    )


def generate_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Generate SQL Node - Using ChatPromptTemplate with Table-Specific Rules

    Generates SQL queries using ChatPromptTemplate with dynamic table-specific rules.
    """
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

        formatted_messages, pregeneration_hints = build_sql_generation_messages(
            user_query=user_query,
            schema_context=schema_context,
            selected_tables=selected_tables,
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
            state["sql_candidates"] = generate_sql_candidates(
                formatted_messages=formatted_messages,
                llm_manager=llm_manager,
                primary_sql=sql_query,
                primary_confidence=primary_confidence,
            )
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
    "_build_pregeneration_hints",
    "_generate_sql_candidates",
    "build_sql_generation_messages",
    "generate_sql_node",
]
