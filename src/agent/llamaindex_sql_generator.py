"""Optional LlamaIndex SQL draft generation.

The functions in this module only produce candidate SQL text. They do not
execute SQL and must remain behind the normal validation/repair/execution flow.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class LlamaIndexSQLDraft:
    sql: str
    reasoning: str
    confidence: float
    source: str = "llamaindex_sql_draft"


class _LlamaIndexSQLDraftOutput(BaseModel):
    sql: str = Field(description="SQL SELECT query that answers the question")
    reasoning: str = Field(
        description="Brief rationale for table, join, filter, and metric choices"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0 to 1")


_SQL_DRAFT_PROMPT = """\
You are a Text-to-SQL specialist for Brazilian DATASUS/SIH analytics.

Generate exactly one safe SQL SELECT query. Do not execute SQL.

Rules:
- Return DuckDB-compatible SELECT or WITH SQL only.
- Use the schema, table names, column names, semantic plan, chart plan, and domain notes provided.
- Preserve requested answer shape: scalar, grouped table, time series, top-N, or chart-ready rows.
- Do not invent tables or columns.
- Do not generate INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, COPY, or PRAGMA.

Question:
{user_query}

Selected tables:
{selected_tables}

Schema and domain context:
{schema_context}

Semantic plan:
{semantic_plan}

Chart plan:
{chart_plan}
"""


def generate_llamaindex_sql_draft(
    *,
    user_query: str,
    schema_context: str,
    selected_tables: list[str],
    semantic_plan: dict[str, Any] | None,
    chart_plan: dict[str, Any] | None,
    model: str,
    temperature: float,
) -> LlamaIndexSQLDraft:
    """Generate a candidate SQL query through LlamaIndex structured prediction."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LlamaIndex SQL draft generation")

    try:
        from llama_index.core import PromptTemplate
        from llama_index.llms.openai import OpenAI
    except Exception as exc:
        raise RuntimeError(f"LlamaIndex SQL draft dependencies unavailable: {exc}") from exc

    llm = OpenAI(
        model=model,
        temperature=temperature,
        timeout=120,
        api_key=api_key,
    )
    prompt = PromptTemplate(_SQL_DRAFT_PROMPT)
    output = llm.structured_predict(
        _LlamaIndexSQLDraftOutput,
        prompt,
        user_query=user_query,
        selected_tables=", ".join(selected_tables) if selected_tables else "(none)",
        schema_context=schema_context,
        semantic_plan=semantic_plan or {},
        chart_plan=chart_plan or {},
    )
    return LlamaIndexSQLDraft(
        sql=output.sql,
        reasoning=output.reasoning,
        confidence=output.confidence,
    )
