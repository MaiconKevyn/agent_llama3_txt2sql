"""SQL generation pipeline: schema, CoT planning, and structured output."""

import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..semantic.plan_schema import SemanticPlan
from ..utils.logging_config import get_nodes_logger
from .llamaindex_context import should_use_llamaindex_sql_draft
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


def _build_deterministic_scalar_sql(semantic_plan) -> str | None:
    if not semantic_plan:
        return None
    try:
        plan = (
            semantic_plan
            if isinstance(semantic_plan, SemanticPlan)
            else SemanticPlan.model_validate(semantic_plan)
        )
    except Exception:
        return None

    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None

    race_color_code_map = {
        "branca": "1",
        "preta": "2",
        "parda": "3",
        "amarela": "4",
        "indigena": "5",
        "indígena": "5",
    }
    age_filter_conditions: list[tuple[str, int]] = []
    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        if field == "raca_cor_identificada":
            where_conditions.append('"RACA_COR" IN (1, 2, 3, 4, 5)')
            continue
        if field == "raca_cor" and semantic_filter.values:
            values = [str(value).strip().lower() for value in semantic_filter.values]
            codes = [race_color_code_map.get(value, value) for value in values]
            if not codes or not all(re.fullmatch(r"[1-5]", code) for code in codes):
                return None
            where_conditions.append(f'"RACA_COR" IN ({", ".join(sorted(set(codes)))})')
            continue
        if field != "idade" or not semantic_filter.values:
            return None
        operator = semantic_filter.operator.strip()
        if operator not in {"=", "<", "<=", ">", ">="}:
            return None
        values = [str(value).strip() for value in semantic_filter.values]
        if not all(re.fullmatch(r"\d+", value) for value in values):
            return None
        numeric_values = [int(value) for value in values]
        if operator == "=":
            age_filter_conditions.append((operator, numeric_values[0]))
        elif operator in {"<", "<="}:
            age_filter_conditions.append((operator, max(numeric_values)))
        else:
            age_filter_conditions.append((operator, min(numeric_values)))

    if ("=", 0) in age_filter_conditions and any(
        operator in {"<", "<="} and value <= 1 for operator, value in age_filter_conditions
    ):
        age_filter_conditions = [("=", 0)]

    where_conditions.extend(
        f'"IDADE" {operator} {value}' for operator, value in age_filter_conditions
    )
    where_clause = f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
    metric_names = {metric.name for metric in plan.metrics}
    scalar_metric_sql = {
        "valor_servico_profissional": {
            "max": ('MAX("VAL_SP")', "maior_valor_servico_profissional"),
            "min": ('MIN("VAL_SP")', "menor_valor_servico_profissional"),
        },
        "permanencia_hospitalar": {
            "max": ('MAX("DIAS_PERM")', "maior_permanencia_hospitalar"),
            "min": ('MIN("DIAS_PERM")', "menor_permanencia_hospitalar"),
        },
        "valor_servico_hospitalar": {
            "max": ('MAX("VAL_SH")', "maior_valor_servico_hospitalar"),
            "min": ('MIN("VAL_SH")', "menor_valor_servico_hospitalar"),
        },
        "valor_internacao": {
            "max": ('MAX("VAL_TOT")', "maior_valor_internacao"),
            "min": ('MIN("VAL_TOT")', "menor_valor_internacao"),
        },
        "total_dias_permanencia": {
            "sum": ('SUM("DIAS_PERM")', "total_dias_permanencia"),
        },
        "total_servico_profissional": {
            "sum": ('SUM("VAL_SP")', "total_servico_profissional"),
        },
        "total_servico_hospitalar": {
            "sum": ('SUM("VAL_SH")', "total_servico_hospitalar"),
        },
        "valor_total_internacoes": {
            "sum": ('SUM("VAL_TOT")', "valor_total_internacoes"),
        },
    }
    for metric in plan.metrics:
        expression = scalar_metric_sql.get(metric.name, {}).get(metric.expression_type)
        if expression:
            aggregate_sql, alias = expression
            return f"SELECT {aggregate_sql} AS {alias} FROM internacoes{where_clause};"

    if "idade_minima" in metric_names:
        return f'SELECT MIN("IDADE") AS idade_minima FROM internacoes{where_clause};'
    if "idade_maxima" in metric_names:
        return f'SELECT MAX("IDADE") AS idade_maxima FROM internacoes{where_clause};'
    if (
        any(metric.name == "total" and metric.expression_type == "count" for metric in plan.metrics)
        and where_conditions
    ):
        return f"SELECT COUNT(*) AS total_internacoes FROM internacoes{where_clause};"
    return None


def generate_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Generate SQL using ChatPromptTemplate with table-specific rules."""
    start_time = time.time()

    logger.info("SQL generation node started", extra={"user_query": state["user_query"][:100]})

    try:
        user_query = state["user_query"]
        schema_context = state.get("schema_context", "")
        selected_tables = state.get("selected_tables", [])
        semantic_plan = state.get("semantic_plan")
        chart_plan = state.get("chart_plan")

        deterministic_sql = _build_deterministic_scalar_sql(semantic_plan)
        if deterministic_sql:
            state["generated_sql"] = deterministic_sql
            state["current_error"] = None
            state = add_ai_message(
                state,
                f"Generated SQL query (deterministic_scalar): {deterministic_sql}",
            )
            meta = state.get("response_metadata", {}) or {}
            meta["sql_generation_confidence"] = 1.0
            meta["sql_generation_reasoning"] = (
                "Deterministic scalar SQL generated from the semantic plan."
            )
            state["response_metadata"] = meta
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)
            logger.info(
                "SQL generated via deterministic scalar macro",
                extra={"sql": deterministic_sql[:200], "execution_time": execution_time},
            )
            return state

        llm_manager = get_llm_manager()

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
        if chart_plan:
            try:
                from ..visualization.schema import ChartPlan

                parsed_chart_plan = ChartPlan.model_validate(chart_plan)
                chart_prompt = parsed_chart_plan.to_prompt_block()
            except Exception:
                chart_prompt = (
                    f"[CHART PLAN - SQL RESULT MUST SUPPORT THIS VISUALIZATION]\n{chart_plan}"
                )
            user_query = (
                f"{user_query}\n\n"
                f"{chart_prompt}\n"
                "Quando houver ChartPlan requested=true, a SQL deve retornar colunas compatíveis com required_columns. "
                "Prefira formato tidy/long para series_dimension: uma linha por x_dimension e series_dimension, "
                "com a métrica em y_column. Não gere colunas extras que sejam códigos de domínio se elas não forem necessárias ao gráfico."
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
                    meta = state.get("response_metadata", {}) or {}
                    meta["sql_generation_source"] = draft.source
                    meta["sql_generation_confidence"] = draft.confidence
                    meta["sql_generation_reasoning"] = draft.reasoning
                    state["response_metadata"] = meta
                    logger.info(
                        "SQL generated via LlamaIndex draft",
                        extra={
                            "sql": sql_query[:200],
                            "confidence": draft.confidence,
                        },
                    )
            except Exception as llama_err:
                meta = state.get("response_metadata", {}) or {}
                meta["llamaindex_sql_draft_error"] = str(llama_err)
                state["response_metadata"] = meta
                logger.warning(
                    "LlamaIndex SQL draft failed, falling back to current generator",
                    extra={"error": str(llama_err)},
                )

        if not sql_query:
            try:
                structured_result = llm_manager.invoke_chat_structured(
                    formatted_messages, SQLOutput
                )
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
                meta["sql_generation_source"] = "current_structured_output"
                state["response_metadata"] = meta
            except Exception as struct_err:
                logger.warning(
                    "Structured output failed, falling back to text parse",
                    extra={"error": str(struct_err)},
                )
                generation_method = "text_fallback"
                response = llm_manager.invoke_chat(formatted_messages)
                sql_query = (
                    response.content.strip() if hasattr(response, "content") else str(response)
                )
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
