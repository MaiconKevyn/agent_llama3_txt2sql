"""LLM-backed SQL generation fallback helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from ..utils.logging_config import get_nodes_logger
from .llamaindex_context import should_use_llamaindex_sql_draft

logger = get_nodes_logger()


class SQLOutput(BaseModel):
    """Structured output for SQL generation."""

    sql: str = Field(description="Valid DuckDB SELECT query answering the user question")
    reasoning: str = Field(description="Brief explanation of table/filter choices (1-2 sentences)")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1; use <0.6 for uncertain queries",
    )


@dataclass
class SQLFallbackResult:
    sql_query: str | None = None
    generation_method: str = "structured"
    metadata: dict[str, Any] = field(default_factory=dict)


def generate_sql_with_fallback(
    *,
    llm_manager: Any,
    formatted_messages: list[BaseMessage],
    user_query: str,
    schema_context: str,
    selected_tables: list[str],
    semantic_plan: dict[str, Any] | None,
    chart_plan: dict[str, Any] | None,
    ablation_flags: dict[str, Any] | None,
) -> SQLFallbackResult:
    """Generate SQL through LlamaIndex draft, structured output, then text fallback."""

    metadata: dict[str, Any] = {}
    sql_query: str | None = None
    generation_method = "structured"

    if should_use_llamaindex_sql_draft(ablation_flags):
        try:
            from .llamaindex_sql_generator import generate_llamaindex_sql_draft

            draft = generate_llamaindex_sql_draft(
                user_query=user_query,
                schema_context=schema_context,
                selected_tables=selected_tables,
                semantic_plan=semantic_plan if isinstance(semantic_plan, dict) else None,
                chart_plan=chart_plan if isinstance(chart_plan, dict) else None,
                model=llm_manager.config.llm_model,
                temperature=llm_manager.config.llm_temperature,
            )
            sql_query = llm_manager._clean_sql_query(draft.sql)
            if sql_query:
                generation_method = draft.source
                metadata.update(
                    {
                        "sql_generation_source": draft.source,
                        "sql_generation_confidence": draft.confidence,
                        "sql_generation_reasoning": draft.reasoning,
                    }
                )
                logger.info(
                    "SQL generated via LlamaIndex draft",
                    extra={
                        "sql": sql_query[:200],
                        "confidence": draft.confidence,
                    },
                )
        except Exception as llama_err:
            metadata["llamaindex_sql_draft_error"] = str(llama_err)
            logger.warning(
                "LlamaIndex SQL draft failed, falling back to current generator",
                extra={"error": str(llama_err)},
            )

    if sql_query:
        return SQLFallbackResult(
            sql_query=sql_query,
            generation_method=generation_method,
            metadata=metadata,
        )

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
        metadata.update(
            {
                "sql_generation_confidence": structured_result.confidence,
                "sql_generation_reasoning": structured_result.reasoning,
                "sql_generation_source": "current_structured_output",
            }
        )
    except Exception as struct_err:
        logger.warning(
            "Structured output failed, falling back to text parse",
            extra={"error": str(struct_err)},
        )
        generation_method = "text_fallback"
        response = llm_manager.invoke_chat(formatted_messages)
        sql_query = response.content.strip() if hasattr(response, "content") else str(response)
        sql_query = llm_manager._clean_sql_query(sql_query)

    return SQLFallbackResult(
        sql_query=sql_query,
        generation_method=generation_method,
        metadata=metadata,
    )
