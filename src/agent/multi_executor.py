"""Multi-query executor — generates, validates, repairs and executes each sub-query."""

import ast
import time

from langchain_core.messages import HumanMessage, SystemMessage

from ..utils.logging_config import get_nodes_logger
from ..utils.sql_safety import is_select_only
from .llm_manager import get_llm_manager
from .sql_generation import SQLOutput, build_sql_generation_messages
from .state_helpers import add_ai_message, add_error, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL, QueryPlan, SubQuery
from .table_selection import select_tables_with_llamaindex
from .validation import check_semantic_rules

logger = get_nodes_logger()

MAX_SUB_QUERIES = 4
MAX_SUBQUERY_REPAIRS = 1

_ERROR_INDICATORS = [
    "does not exist",
    "syntax error",
    "invalid sql",
    "error:",
    "psycopg2.errors",
    "relation",
    "column",
    "violates",
]


def _parse_result_rows(result_raw: str) -> list | None:
    if not result_raw:
        return []

    text = result_raw.strip()
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            rows = []
            for item in parsed:
                rows.append(item if isinstance(item, tuple) else (item,))
            return rows
        return [(parsed,)]
    except Exception:
        return None


def _topological_sort(sub_queries: list[SubQuery]) -> list[SubQuery]:
    if not any(sq.depends_on for sq in sub_queries):
        return list(sub_queries)

    id_to_sq = {sq.id: sq for sq in sub_queries}
    visited: set = set()
    ordered: list[SubQuery] = []

    def _visit(sq_id: str) -> None:
        if sq_id in visited:
            return
        visited.add(sq_id)
        sq = id_to_sq.get(sq_id)
        if sq:
            for dep in sq.depends_on:
                _visit(dep)
            ordered.append(sq)

    for sq in sub_queries:
        _visit(sq.id)

    return ordered


def _format_dependency_context(prior_results: dict[str, str]) -> str:
    if not prior_results:
        return ""
    lines = ["", "[CONTEXT FROM PRIOR QUERIES]"]
    for dep_id, result_text in prior_results.items():
        lines.append(f"{dep_id}: {result_text[:500]}")
    return "\n".join(lines)


def _generate_sql_for_subquery(
    sq: SubQuery,
    schema_context: str,
    selected_tables: list[str],
    prior_results: dict[str, str],
    llm_manager,
) -> str:
    subquery_question = sq.description + _format_dependency_context(prior_results)

    formatted_messages, _ = build_sql_generation_messages(
        user_query=subquery_question,
        schema_context=schema_context,
        selected_tables=selected_tables,
    )

    try:
        result = llm_manager.invoke_chat_structured(formatted_messages, SQLOutput)
        return llm_manager._clean_sql_query(result.sql)
    except Exception:
        response = llm_manager.invoke_chat(formatted_messages)
        raw = response.content.strip() if hasattr(response, "content") else str(response)
        return llm_manager._clean_sql_query(raw)


def _validate_subquery_sql(
    user_query: str,
    sql: str,
    llm_manager,
) -> tuple[bool, str]:
    if not sql:
        return False, "No SQL generated."

    ok, reason = is_select_only(sql)
    if not ok:
        return False, f"Blocked non-SELECT SQL: {reason}"

    checker_tool = next(
        (tool for tool in llm_manager.get_sql_tools() if tool.name == "sql_db_query_checker"),
        None,
    )
    if checker_tool:
        try:
            checker_result = str(checker_tool.invoke(sql))
            lowered = checker_result.lower()
            if "invalid" in lowered or "error" in lowered:
                return False, checker_result
        except Exception as checker_error:
            return False, f"Query checker failed: {checker_error}"

    db_val = llm_manager.validate_sql_query(sql)
    if not db_val.get("is_valid", False):
        return False, db_val.get("error", "DB validation failed")

    semantic_ok, semantic_message = check_semantic_rules(user_query, sql)
    if not semantic_ok:
        return False, semantic_message or "Semantic validation failed"

    return True, "ok"


def _repair_subquery_sql(
    sq: SubQuery,
    user_query: str,
    schema_context: str,
    selected_tables: list[str],
    previous_sql: str,
    error_message: str,
    llm_manager,
) -> str | None:
    system_prompt = (
        "Você é um especialista em PostgreSQL responsável por corrigir uma subconsulta SQL do banco SUS. "
        "Preserve as constraints da subconsulta, use apenas SELECT e responda somente com a SQL corrigida."
    )
    human_prompt = (
        f"Pergunta original: {user_query}\n\n"
        f"Subconsulta: {sq.description}\n\n"
        f"Tabelas selecionadas: {', '.join(selected_tables) if selected_tables else 'N/D'}\n\n"
        f"Schema:\n{schema_context[:3000]}\n\n"
        f"SQL anterior:\n{previous_sql}\n\n"
        f"Erro/validação:\n{error_message}\n\n"
        "Reescreva a SQL corrigida, preservando a intenção e as constraints."
    )
    response = llm_manager.invoke_chat(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]
    )
    raw = response.content.strip() if hasattr(response, "content") else str(response)
    return llm_manager._clean_sql_query(raw)


def _select_tables_for_subquery(
    state: MessagesStateTXT2SQL,
    sq: SubQuery,
    llm_manager,
) -> list[str]:
    available_tables = state.get("available_tables", []) or state.get("selected_tables", [])
    global_tables = state.get("selected_tables", [])
    subquery_prompt = sq.description
    if sq.required_constraints:
        subquery_prompt += "\nConstraints: " + "; ".join(sq.required_constraints)

    try:
        selected_tables, _, llama_context = select_tables_with_llamaindex(
            user_query=subquery_prompt,
            available_tables=available_tables,
            ablation_flags=state.get("ablation_flags") or {},
        )
        if selected_tables:
            return selected_tables
        logger.warning(
            "Sub-query LlamaIndex table selection returned no tables",
            extra={
                "sq_id": sq.id,
                "retrieval_mode": getattr(llama_context, "retrieval_mode", None),
                "error": getattr(llama_context, "error", ""),
            },
        )
    except Exception as table_error:
        logger.warning(
            "Sub-query table selection failed",
            extra={
                "sq_id": sq.id,
                "error": str(table_error),
            },
        )

    return global_tables


def _execute_sql(sql: str, llm_manager) -> tuple[bool, str]:
    query_tool = next(
        (tool for tool in llm_manager.get_sql_tools() if tool.name == "sql_db_query"),
        None,
    )
    if not query_tool:
        raise ValueError("sql_db_query tool not found in LLM manager.")

    tool_result = query_tool.invoke(sql)
    result_str = str(tool_result).strip()
    lower_result = result_str.lower()
    is_error = any(ind in lower_result for ind in _ERROR_INDICATORS)
    return (not is_error), result_str


def multi_sql_executor_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Execute each sub-query with local table selection and validation."""
    start_time = time.time()

    try:
        llm_manager = get_llm_manager()
        query_plan: QueryPlan = state.get("query_plan")

        if not query_plan:
            raise ValueError("No query_plan in state — cannot execute multi-query.")

        if query_plan.strategy != "multi":
            state = update_phase(state, ExecutionPhase.SQL_EXECUTION, time.time() - start_time)
            return state

        user_query = state.get("user_query", "")
        schema_context = state.get("schema_context", "")

        if len(query_plan.sub_queries) > MAX_SUB_QUERIES:
            logger.warning(
                "LLM returned too many sub-queries; truncating to %d",
                MAX_SUB_QUERIES,
                extra={"original_count": len(query_plan.sub_queries)},
            )
            query_plan.sub_queries = query_plan.sub_queries[:MAX_SUB_QUERIES]

        ordered_sqs = _topological_sort(query_plan.sub_queries)
        sub_query_results = []
        completed_raw: dict[str, str] = {}

        for sq in ordered_sqs:
            sq_start = time.time()

            if any(dep not in completed_raw for dep in sq.depends_on):
                missing = [dep for dep in sq.depends_on if dep not in completed_raw]
                sq.success = False
                sq.error = f"Missing dependency results: {', '.join(missing)}"
                sub_query_results.append(_make_result(sq, time.time() - sq_start))
                continue

            prior_results = {dep: completed_raw[dep] for dep in sq.depends_on}
            sq.selected_tables = _select_tables_for_subquery(state, sq, llm_manager)

            try:
                sql = _generate_sql_for_subquery(
                    sq=sq,
                    schema_context=schema_context,
                    selected_tables=sq.selected_tables,
                    prior_results=prior_results,
                    llm_manager=llm_manager,
                )
                sq.sql = sql
            except Exception as gen_err:
                sq.success = False
                sq.error = f"SQL generation failed: {gen_err}"
                sub_query_results.append(_make_result(sq, time.time() - sq_start))
                logger.error(
                    "Sub-query SQL generation failed", extra={"sq_id": sq.id, "error": str(gen_err)}
                )
                continue

            validated_sql = sq.sql
            validation_ok, validation_msg = _validate_subquery_sql(
                user_query, validated_sql, llm_manager
            )
            if not validation_ok:
                if sq.repair_attempts < MAX_SUBQUERY_REPAIRS:
                    try:
                        sq.repair_attempts += 1
                        validated_sql = _repair_subquery_sql(
                            sq=sq,
                            user_query=user_query,
                            schema_context=schema_context,
                            selected_tables=sq.selected_tables,
                            previous_sql=sq.sql or "",
                            error_message=validation_msg,
                            llm_manager=llm_manager,
                        )
                        validation_ok, validation_msg = _validate_subquery_sql(
                            user_query,
                            validated_sql,
                            llm_manager,
                        )
                    except Exception as repair_error:
                        validation_ok = False
                        validation_msg = f"{validation_msg} | repair failed: {repair_error}"

            if not validation_ok:
                sq.success = False
                sq.error = validation_msg
                sq.validated_sql = None
                sub_query_results.append(_make_result(sq, time.time() - sq_start))
                continue

            sq.validated_sql = validated_sql

            execution_ok, result_str = _execute_sql(validated_sql, llm_manager)
            if not execution_ok and sq.repair_attempts < MAX_SUBQUERY_REPAIRS:
                try:
                    sq.repair_attempts += 1
                    repaired_sql = _repair_subquery_sql(
                        sq=sq,
                        user_query=user_query,
                        schema_context=schema_context,
                        selected_tables=sq.selected_tables,
                        previous_sql=validated_sql,
                        error_message=result_str,
                        llm_manager=llm_manager,
                    )
                    validation_ok, validation_msg = _validate_subquery_sql(
                        user_query,
                        repaired_sql,
                        llm_manager,
                    )
                    if validation_ok:
                        sq.validated_sql = repaired_sql
                        execution_ok, result_str = _execute_sql(repaired_sql, llm_manager)
                except Exception as repair_error:
                    result_str = f"{result_str} | repair failed: {repair_error}"

            if execution_ok:
                sq.success = True
                sq.result_raw = result_str
                sq.parsed_rows = _parse_result_rows(result_str)
                completed_raw[sq.id] = result_str
            else:
                sq.success = False
                sq.error = result_str
                sq.parsed_rows = None

            sub_query_results.append(_make_result(sq, time.time() - sq_start))
            logger.info(
                "Sub-query executed",
                extra={
                    "sq_id": sq.id,
                    "success": sq.success,
                    "output_role": sq.output_role,
                    "selected_tables": sq.selected_tables,
                },
            )

        state["sub_query_results"] = sub_query_results
        state["query_plan"] = query_plan

        successful = sum(1 for r in sub_query_results if r["success"])
        total = len(sub_query_results)
        state = add_ai_message(
            state,
            f"Multi-query execution complete: {successful}/{total} sub-consultas executadas com sucesso.",
        )

        state = update_phase(state, ExecutionPhase.SQL_EXECUTION, time.time() - start_time)
        return state

    except Exception as e:
        error_msg = f"Multi-query executor failed: {str(e)}"
        logger.error("multi_sql_executor_node error", extra={"error": str(e)})
        state = add_error(state, error_msg, "sql_execution_error", ExecutionPhase.SQL_EXECUTION)
        state = update_phase(state, ExecutionPhase.SQL_EXECUTION, time.time() - start_time)
        return state


def _make_result(sq: SubQuery, elapsed: float) -> dict:
    return {
        "id": sq.id,
        "description": sq.description,
        "purpose": sq.purpose,
        "output_role": sq.output_role,
        "depends_on": list(sq.depends_on),
        "expected_result_kind": sq.expected_result_kind,
        "expected_max_rows": sq.expected_max_rows,
        "required_constraints": list(sq.required_constraints),
        "selected_tables": list(sq.selected_tables),
        "bind_keys": list(sq.bind_keys),
        "sql": sq.sql,
        "validated_sql": sq.validated_sql,
        "result": sq.result_raw,
        "parsed_rows": sq.parsed_rows,
        "success": sq.success,
        "error": sq.error,
        "repair_attempts": sq.repair_attempts,
        "execution_time": elapsed,
    }
