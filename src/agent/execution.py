"""SQL execution and repair nodes."""

import ast
import re
import time
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ..utils.logging_config import get_nodes_logger
from ..utils.sql_safety import is_select_only
from .llm_manager import get_llm_manager
from .schema_node import _refresh_schema_context, _should_refresh_schema
from .schema_utils import _check_columns_against_schema
from .state_helpers import (
    add_ai_message,
    add_error,
    add_tool_call_result,
    add_tool_message,
    update_phase,
)
from .state_models import (
    TX,
    ExecutionPhase,
    MessagesStateTXT2SQL,
    SQLExecutionResult,
    ToolCallResult,
)

logger = get_nodes_logger()


def _parse_tool_result_rows(tool_result_str: str) -> list[dict]:
    """Parse LangChain SQL tool output into row-level result records."""
    text = tool_result_str.strip()
    if not text:
        return []

    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        parsed = None

    if isinstance(parsed, list):
        return [{"result": row} for row in parsed]
    if isinstance(parsed, tuple):
        return [{"result": parsed}]

    return [{"result": line.strip()} for line in text.split("\n") if line.strip()]


def execute_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Execute SQL Node - Using SQLDatabaseToolkit query tool

    Uses the sql_db_query tool from SQLDatabaseToolkit
    Following official LangGraph SQL agent patterns
    """
    start_time = time.time()

    try:
        validated_sql = state.get("validated_sql") or state.get("generated_sql")

        if not validated_sql:
            raise ValueError("No validated SQL query to execute")

        # Block non-SELECT/unsafe SQL before touching the LLM manager or DB
        ok, reason = is_select_only(validated_sql)
        if not ok:
            error_message = f"SQL execution blocked: {reason}"
            state = add_error(
                state,
                error_message,
                "sql_execution_error",
                ExecutionPhase.SQL_EXECUTION,
                taxonomy=TX.WRONG_FILTER,
            )
            state["retry_count"] = state.get("retry_count", 0) + 1
            state["execution_retry_count"] = state.get("execution_retry_count", 0) + 1
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)
            return state

        llm_manager = get_llm_manager()

        # Low-confidence SQL warning (observability only — does NOT block execution)
        confidence = state.get("response_metadata", {}).get("sql_generation_confidence")
        if confidence is not None and confidence < 0.5:
            logger.warning(
                "Low-confidence SQL about to execute",
                extra={
                    "confidence": confidence,
                    "sql": (state.get("validated_sql") or state.get("generated_sql", ""))[:200],
                    "user_query": state.get("user_query", "")[:100],
                },
            )

        # Column existence check (skip if DB-validated)
        if state.get("validated_sql") is None:
            schema_context = state.get("schema_context", "")
            col_check = _check_columns_against_schema(schema_context, validated_sql)
            if not col_check.get("ok", True):
                missing_items = col_check.get("issues", [])
                sugg = col_check.get("suggestions", {})
                parts = []
                for alias, col, base in missing_items:
                    key = f"{alias}.{col}"
                    cand = sugg.get(key, [])
                    base_info = f" na tabela {base}" if base else ""
                    if cand:
                        parts.append(
                            f"Coluna ausente {key}{base_info}; candidatos: {', '.join(cand)}"
                        )
                    else:
                        parts.append(f"Coluna/alias ausente {key}{base_info}")
                msg = "; ".join(parts)
                error_message = f"SQL validation failed (schema check): {msg}"
                state = add_error(
                    state,
                    error_message,
                    "sql_validation_error",
                    ExecutionPhase.SQL_VALIDATION,
                    taxonomy=TX.SCHEMA_ERROR,
                )
                state["retry_count"] = state.get("retry_count", 0) + 1
                state["validation_retry_count"] = state.get("validation_retry_count", 0) + 1
                meta = state.get("response_metadata", {}) or {}
                meta["column_check_suggestions"] = {
                    "missing": missing_items,
                    "suggestions": sugg,
                    "alias_map": col_check.get("alias_map", {}),
                    "schema_map": col_check.get("schema_map", {}),
                }
                state["response_metadata"] = meta
                state = add_ai_message(state, f"SQL schema check falhou: {msg}")
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_VALIDATION, execution_time)
                return state

        tools = llm_manager.get_sql_tools()
        query_tool = next((tool for tool in tools if tool.name == "sql_db_query"), None)

        if not query_tool:
            raise ValueError("sql_db_query tool not found")

        logger.info("SQL execution started", extra={"sql": validated_sql})
        tool_result = query_tool.invoke(validated_sql)

        results = []
        row_count = 0
        execution_success = True
        error_message = None

        if isinstance(tool_result, str) and tool_result.strip():
            tool_result_str = tool_result.strip()

            error_indicators = [
                "does not exist",
                "não existe",
                "ERRO:",
                "ERROR:",
                "psycopg2.errors",
                "column.*not found",
                "coluna.*não existe",
                "relation.*does not exist",
                "tabela.*não existe",
                "invalid sql",
                "syntax error",
            ]

            lower_result = tool_result_str.lower()
            if any(indicator.lower() in lower_result for indicator in error_indicators):
                execution_success = False
                error_message = tool_result_str
                logger.error("SQL tool returned error", extra={"error_in_result": tool_result_str})
            else:
                results = _parse_tool_result_rows(tool_result_str)
                row_count = len(results)

        sql_execution_result = SQLExecutionResult(
            success=execution_success,
            sql_query=validated_sql,
            results=results,
            row_count=row_count,
            execution_time=time.time() - start_time,
            validation_passed=True,
            error_message=error_message,
        )

        state["sql_execution_result"] = sql_execution_result

        if not execution_success:
            state = add_error(
                state, error_message, "sql_execution_error", ExecutionPhase.SQL_EXECUTION
            )
            state["retry_count"] = state.get("retry_count", 0) + 1
            state["execution_retry_count"] = state.get("execution_retry_count", 0) + 1

            tool_call_result = ToolCallResult(
                tool_name="sql_db_query",
                tool_input={"query": validated_sql},
                tool_output=tool_result,
                success=False,
                execution_time=time.time() - start_time,
            )
            state = add_tool_call_result(state, tool_call_result)

            ai_response = f"SQL execution failed: {error_message}"
            state = add_ai_message(state, ai_response)

            logger.error(
                "SQL execution failed with tool error",
                extra={
                    "sql": validated_sql[:200],
                    "error": error_message,
                },
            )

            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)
            return state

        # Success
        tool_call_result = ToolCallResult(
            tool_name="sql_db_query",
            tool_input={"query": validated_sql},
            tool_output=tool_result,
            success=True,
            execution_time=time.time() - start_time,
        )
        state = add_tool_call_result(state, tool_call_result)

        ai_response = f"Query executed successfully. Found {row_count} results."
        if row_count > 0 and results:
            ai_response += f" Sample: {results[:3]}"

        state = add_ai_message(state, ai_response)

        state["current_error"] = None
        state["retry_count"] = 0

        execution_time = time.time() - start_time
        logger.info(
            "Query executed successfully",
            extra={
                "sql": validated_sql[:200],
                "row_count": row_count,
                "execution_time": execution_time,
            },
        )
        state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)

        return state

    except Exception as e:
        error_message = f"SQL execution failed: {str(e)}"
        logger.error(
            "SQL execution failed",
            extra={
                "sql": validated_sql if "validated_sql" in dir() else "",
                "error": str(e),
            },
        )
        state = add_error(state, error_message, "sql_execution_error", ExecutionPhase.SQL_EXECUTION)
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["execution_retry_count"] = state.get("execution_retry_count", 0) + 1

        sql_execution_result = SQLExecutionResult(
            success=False,
            sql_query=validated_sql if "validated_sql" in dir() else "",
            results=[],
            row_count=0,
            execution_time=time.time() - start_time,
            validation_passed=False,
            error_message=error_message,
        )
        state["sql_execution_result"] = sql_execution_result

        try:
            state = add_tool_message(
                state,
                tool_call_id=f"call_{len(state['tool_calls']) + 1}",
                content=error_message,
                tool_name="sql_db_query",
            )
        except Exception:
            pass

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)

        return state


def repair_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Repair SQL Node - regenerate SQL after execution failure."""

    start_time = time.time()

    try:
        llm_manager = get_llm_manager()
        previous_sql = state.get("generated_sql")

        if not previous_sql:
            raise ValueError("No SQL available for repair")

        error_message = state.get("current_error") or ""
        logger.info(
            "Repair node triggered",
            extra={
                "previous_sql": previous_sql[:200],
                "current_error": error_message,
            },
        )
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == "sql_db_query":
                error_message = msg.content
                break

        if not error_message:
            error_message = "Erro desconhecido ao executar a consulta."

        user_query = state.get("user_query", "")

        if _should_refresh_schema(error_message):
            refreshed = _refresh_schema_context(state, error_message, llm_manager)
            logger.info(
                "Schema refresh attempted during repair",
                extra={
                    "refreshed": refreshed,
                    "selected_tables": state.get("selected_tables", []),
                },
            )

        selected_tables = state.get("selected_tables", [])
        schema_context = state.get("schema_context", "") or ""

        col_check = _check_columns_against_schema(schema_context, previous_sql)
        schema_map = col_check.get("schema_map", {})
        alias_map = col_check.get("alias_map", {})
        meta_for_suggestions = state.get("response_metadata", {}) or {}
        column_hints = meta_for_suggestions.get("column_check_suggestions", {})
        missing = column_hints.get("missing", [])
        sugg_map = column_hints.get("suggestions", {})

        MAX_SCHEMA_CHARS = 4000
        if len(schema_context) > MAX_SCHEMA_CHARS:
            schema_context = schema_context[:MAX_SCHEMA_CHARS] + "\n... (schema truncado)"

        whitelist_lines = []
        for alias, table in alias_map.items():
            cols = schema_map.get((table or "").lower(), [])
            if cols:
                preview = ", ".join(cols[:50]) + (" ..." if len(cols) > 50 else "")
                whitelist_lines.append(f"Alias {alias} → tabela {table}: {preview}")
        whitelist_text = "\n".join(whitelist_lines) if whitelist_lines else "(não encontrado)"

        suggestion_lines = []
        for a, c, base in missing:
            key = f"{a}.{c}"
            cands = sugg_map.get(key, [])
            if cands:
                suggestion_lines.append(f"{key} → candidatos: {', '.join(cands)}")
        suggestions_text = "\n".join(suggestion_lines) if suggestion_lines else "(sem sugestões)"

        system_prompt = (
            "Você é um especialista em PostgreSQL responsável por corrigir consultas SQL para o banco SUS. "
            "Restrições obrigatórias: USE APENAS colunas da lista branca por alias/tabela; se uma coluna não existir, substitua por uma das sugeridas; "
            "corrija os JOINs usando chaves que existam em ambas as tabelas. "
            "CRÍTICO — ASPAS DUPLAS: em PostgreSQL TODOS os nomes de colunas DEVEM usar aspas duplas. "
            "Se o erro mencionar 'coluna X não existe', quase sempre é falta de aspas duplas — adicione-as: "
            'c.cd_descricao → c."CD_DESCRICAO"; c.cid → c."CID"; alias.coluna → alias."COLUNA". '
            "Responda apenas com a SQL válida, sem comentários, markdown ou texto adicional."
        )

        human_prompt = (
            f"Consulta do usuário (contexto):\n{user_query}\n\n"
            f"SQL anterior gerada:\n{previous_sql}\n\n"
            f"Erro retornado pelo banco de dados/validação:\n{error_message}\n\n"
            f"Tabelas selecionadas: {', '.join(selected_tables) if selected_tables else 'N/D'}\n\n"
            f"Lista branca de colunas por alias/tabela:\n{whitelist_text}\n\n"
            f"Sugestões de substituição de colunas ausentes:\n{suggestions_text}\n\n"
            f"Schema disponível:\n{schema_context}\n\n"
            "Reescreva a consulta corrigindo o problema identificado, usando SOMENTE colunas da lista branca e as sugestões quando necessário."
        )

        response = llm_manager.invoke_chat(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]
        )

        repaired_sql = response.content.strip() if hasattr(response, "content") else str(response)
        repaired_sql = llm_manager._clean_sql_query(repaired_sql)

        if not repaired_sql:
            raise ValueError("LLM returned empty SQL during repair")

        # Early-exit if repeated same SQL
        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", (s or "").lower()).rstrip(";")

        meta = state.get("response_metadata", {}) or {}
        history = meta.get("repair_attempts", [])
        prevs = []
        if history:
            prevs.append(history[-1].get("previous_sql", ""))
        prevs.append(previous_sql)
        if len(prevs) >= 2 and all(_norm(p) == _norm(repaired_sql) for p in prevs):
            diag = "Reparo produziu a mesma SQL das últimas tentativas. Use apenas colunas válidas conforme lista branca e sugestões."
            state = add_error(
                state, diag, "sql_repair_error", ExecutionPhase.SQL_REPAIR, taxonomy=TX.REPAIR_LOOP
            )
            state["retry_count"] = state.get("max_retries", 3)
            meta["repair_early_exit"] = {
                "reason": diag,
                "whitelist": whitelist_lines,
                "suggestions": suggestion_lines,
            }
            state["response_metadata"] = meta
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
            return state

        # Record repair attempt
        metadata = state.get("response_metadata", {}) or {}
        repair_history = metadata.get("repair_attempts", [])
        repair_history.append(
            {
                "previous_sql": previous_sql,
                "error_message": error_message,
                "timestamp": datetime.now().isoformat(),
            }
        )
        metadata["repair_attempts"] = repair_history
        state["response_metadata"] = metadata

        state["generated_sql"] = repaired_sql
        state["current_error"] = None

        state = add_ai_message(state, "Gerada nova versão da consulta após erro de execução.")

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)

        attempt_number = len(repair_history)
        logger.info(
            "SQL repair completed",
            extra={
                "status": "success",
                "attempt_number": attempt_number,
                "user_query": user_query[:100],
                "error_message": error_message[:200],
                "previous_sql": previous_sql[:200],
                "repaired_sql": repaired_sql[:200],
                "selected_tables": selected_tables,
                "execution_time": execution_time,
            },
        )

        return state

    except Exception as e:
        error_message = f"SQL repair failed: {str(e)}"
        state = add_error(
            state,
            error_message,
            "sql_repair_error",
            ExecutionPhase.SQL_GENERATION,
            taxonomy=TX.REPAIR_LOOP,
        )

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)

        logger.warning(
            "SQL repair failed",
            extra={
                "status": "failure",
                "error": str(e),
                "user_query": state.get("user_query", "")[:100],
                "previous_sql": state.get("generated_sql", "")[:200],
                "execution_time": execution_time,
            },
        )

        return state
