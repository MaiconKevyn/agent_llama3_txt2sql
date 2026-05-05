"""SQL validation node."""

import re
import time

from ..semantic.error_taxonomy import build_semantic_error_record
from ..semantic.validators import validate_sql_against_semantic_plan
from ..utils.logging_config import get_nodes_logger
from .llm_manager import get_llm_manager
from .state_helpers import add_ai_message, add_error, add_tool_call_result, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL, ToolCallResult

logger = get_nodes_logger()


def check_semantic_rules(user_query: str, generated_sql: str):
    """
    Run all semantic validation rules against a (user_query, generated_sql) pair.

    Returns (passed: bool, message: str | None).
    ``passed=True, message=None`` means no rule was violated.
    This function has no external dependencies (no LLM, no DB) so it can be
    unit-tested in isolation.
    """
    if not generated_sql:
        return True, None

    sql_lower = generated_sql.lower()
    user_query_lower = (user_query or "").lower()

    # Semantic: socioeconomico requires metrica filter
    if "socioeconomico" in sql_lower and "metrica" not in sql_lower:
        return False, (
            "SEMANTIC ERROR: Query uses 'socioeconomico' table but is missing a "
            "WHERE metrica = '...' filter. The socioeconomico table is long-format "
            "(one row per metric × municipality × year). Without a metrica filter, "
            "the query aggregates across ALL metrics (population, IDHM, bolsa familia, "
            "etc.) which produces meaningless results. "
            "FIX EXACTLY: "
            "SELECT mu.nome AS municipio_maior_populacao "
            "FROM socioeconomico s "
            "JOIN municipios mu ON s.codigo_6d = mu.codigo_6d "
            "WHERE s.metrica = 'populacao_total' "
            "ORDER BY s.valor DESC LIMIT 1; "
            "IMPORTANT: SELECT ONLY the column(s) that directly answer the question. "
            "Do NOT include s.valor or extra columns unless explicitly requested."
        )

    # Semantic: tempo table cartesian explosion
    if re.search(r"\bjoin\s+tempo\b", generated_sql, re.I):
        has_proper_equijoin = bool(
            re.search(
                r'on\s+\w+\."DT_INTER"\s*=\s*\w+\."data"',
                generated_sql,
                re.I,
            )
        )
        if not has_proper_equijoin:
            return False, (
                "TEMPO TABLE ERROR: Non-equijoin on tempo table detected "
                '(e.g., ON EXTRACT(YEAR FROM "DT_INTER") = t.ano or ON t.mes BETWEEN ...). '
                "This creates a CARTESIAN PRODUCT multiplying rows by hundreds or thousands! "
                "SOLUTION: Remove the JOIN tempo entirely. Use EXTRACT() directly without any JOIN: "
                '✅ WHERE EXTRACT(YEAR FROM "DT_INTER") = 2015 '
                '✅ WHERE EXTRACT(MONTH FROM "DT_INTER") IN (6, 7, 8) '
                '✅ WHERE EXTRACT(MONTH FROM "DT_INTER") BETWEEN 6 AND 8'
            )

    # Semantic: spurious VAL_UTI on obstetric query
    espec_2 = bool(re.search(r'"ESPEC"\s*=\s*2\b', generated_sql))
    val_uti = bool(re.search(r'"VAL_UTI"\s*>\s*0', generated_sql))
    if espec_2 and val_uti:
        uti_mentioned = any(
            k in user_query_lower
            for k in [
                "uti",
                "unidade de terapia",
                "custo de uti",
                "valor de uti",
                "custo uti",
                "icú",
            ]
        )
        if not uti_mentioned:
            return False, (
                "ERROR: Added 'VAL_UTI > 0' to an obstetric query when UTI was not mentioned. "
                'Obstetric = WHERE "ESPEC" = 2 ONLY (no UTI filter needed here). '
                'REMOVE the AND "VAL_UTI" > 0 condition from this query. '
                "Only add VAL_UTI > 0 when the question explicitly asks about UTI/ICU."
            )

    # Semantic: "quantos" in question but SQL returns a list of rows, not a COUNT
    count_question = any(
        t in user_query_lower
        for t in [
            "quantos ",
            "quantas ",
            "número de ",
            "total de hospitais",
            "total de municípios",
            "total de procedimentos",
            "quantidade de ",
        ]
    )
    if count_question:
        outer_select = re.sub(
            r"\bWITH\b.*?\)\s*SELECT", "SELECT", generated_sql, flags=re.I | re.DOTALL
        )
        has_count_outer = bool(re.search(r"\bCOUNT\s*\(", outer_select, re.I))
        if not has_count_outer:
            return False, (
                "SEMANTIC ERROR: A pergunta pede QUANTIDADE ('quantos'/'quantas') mas a query "
                "retorna uma lista de registros em vez de COUNT(*). "
                "FIX: envolva o resultado em SELECT COUNT(*) AS total FROM (...) sub, "
                "ou use COUNT(*) diretamente no SELECT principal."
            )

    # Semantic: NOT IN with non-trivial subquery — suggest NOT EXISTS
    if re.search(r"\bNOT\s+IN\s*\(\s*SELECT\b", generated_sql, re.I):
        return False, (
            "ANTI-JOIN WARNING: NOT IN with a subquery is unsafe when the subquery may return NULL "
            "values (all rows are filtered out). "
            "REPLACE with NOT EXISTS pattern: "
            "WHERE NOT EXISTS (SELECT 1 FROM tabela b WHERE b.fk = a.pk AND <condição>). "
            "This is correct even when the subquery returns NULLs."
        )

    # Semantic: "por estado" / "por especialidade" ranking without PARTITION BY
    per_group_question = any(
        t in user_query_lower
        for t in [
            "por estado",
            "em cada estado",
            "de cada estado",
            "por especialidade",
            "em cada especialidade",
            "por hospital",
            "em cada hospital",
        ]
    )
    has_partition = bool(re.search(r"\bPARTITION\s+BY\b", generated_sql, re.I))
    has_limit = bool(re.search(r"\bLIMIT\s+\d+\b", generated_sql, re.I))
    top_n_question = any(
        t in user_query_lower
        for t in [
            "maior",
            "menor",
            "principal",
            "principais",
            "top",
            "mais alto",
            "mais baixo",
            "mais comum",
            "mais frequente",
            "3 hospital",
            "3 municip",
            "3 diagnós",
        ]
    )
    if per_group_question and top_n_question and has_limit and not has_partition:
        return False, (
            "SEMANTIC ERROR: A pergunta pede top-N POR GRUPO (por estado/especialidade/hospital) "
            "mas a query usa apenas LIMIT global sem ROW_NUMBER() OVER (PARTITION BY <dimensão>). "
            "LIMIT global seleciona os N melhores no total, não N melhores por grupo. "
            "FIX: use ROW_NUMBER() OVER (PARTITION BY <col_grupo> ORDER BY <métrica> DESC) AS rn "
            "em uma subquery, depois WHERE rn <= N no outer SELECT."
        )

    # Semantic: spurious MORTE = false
    has_morte_false = bool(re.search(r'"MORTE"\s*=\s*(false|FALSE)\b', generated_sql))
    if has_morte_false:
        discharge_asked = any(
            k in user_query_lower
            for k in [
                "alta",
                "sobrevivente",
                "não morreram",
                "sem óbito",
                "recuper",
                "vivos",
                "saíram vivos",
            ]
        )
        if not discharge_asked:
            return False, (
                "ERROR: Added 'MORTE = false' filter but the question does not ask specifically "
                "about discharged (non-death) patients. "
                "REMOVE the '\"MORTE\" = false' condition. "
                "Count ALL patients matching the other conditions, regardless of outcome."
            )

    return True, None


def validate_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Validate SQL Node - Using SQLDatabaseToolkit query checker

    Uses the sql_db_query_checker tool from SQLDatabaseToolkit
    Following official LangGraph SQL agent patterns
    """
    start_time = time.time()

    try:
        llm_manager = get_llm_manager()
        generated_sql = state.get("generated_sql")

        if not generated_sql:
            raise ValueError("No SQL query to validate")

        tools = llm_manager.get_sql_tools()
        checker_tool = next((tool for tool in tools if tool.name == "sql_db_query_checker"), None)

        validation_passed = True
        validation_message = "SQL query is valid"
        checker_msg = None

        # LLM-based checker
        if checker_tool:
            try:
                checker_result = checker_tool.invoke(generated_sql)
                checker_msg = str(checker_result)
                if "error" in checker_msg.lower() or "invalid" in checker_msg.lower():
                    validation_passed = False
                    validation_message = checker_msg
            except Exception as checker_error:
                validation_passed = False
                validation_message = f"Query checker failed: {str(checker_error)}"

        # DB EXPLAIN — takes precedence
        db_val = llm_manager.validate_sql_query(generated_sql)
        if not db_val.get("is_valid", False):
            validation_passed = False
            validation_message = db_val.get("error", "DB validation failed")
        elif validation_passed is False and db_val.get("is_valid", False):
            validation_passed = True
            validation_message = "DB validation passed"

        # Semantic rules (pure logic — no LLM/DB required)
        if validation_passed and generated_sql:
            sem_passed, sem_message = check_semantic_rules(
                state.get("user_query") or "", generated_sql
            )
            if not sem_passed:
                validation_passed = False
                validation_message = sem_message
                logger.warning("Semantic rule rejected query: %s", sem_message[:120])

        if validation_passed and generated_sql:
            plan_passed, plan_message = validate_sql_against_semantic_plan(
                state.get("semantic_plan"), generated_sql
            )
            meta = state.get("response_metadata", {}) or {}
            meta["semantic_validation"] = {
                "passed": plan_passed,
                "constraints": (state.get("semantic_plan") or {}).get("constraints", []),
                "null_policy": (state.get("semantic_plan") or {}).get("null_policy", []),
                "message": plan_message,
            }
            state["response_metadata"] = meta
            if not plan_passed:
                validation_passed = False
                validation_message = plan_message
                logger.warning("Semantic plan rejected query: %s", (plan_message or "")[:120])

        # Update state
        if validation_passed:
            state["validated_sql"] = generated_sql
            state["current_error"] = None
            ai_response = f"SQL query validated successfully: {generated_sql}"
        else:
            semantic_error = build_semantic_error_record(validation_message)
            state = add_error(
                state,
                validation_message,
                "sql_validation_error",
                ExecutionPhase.SQL_VALIDATION,
                taxonomy=semantic_error.category.value,
            )
            state["retry_count"] = state.get("retry_count", 0) + 1
            state["validation_retry_count"] = state.get("validation_retry_count", 0) + 1
            meta = state.get("response_metadata", {}) or {}
            meta["semantic_error"] = {
                "category": semantic_error.category.value,
                "severity": semantic_error.severity,
                "message": semantic_error.message,
            }
            state["response_metadata"] = meta
            errs = state.get("validation_errors", []) or []
            errs.append(validation_message)
            state["validation_errors"] = errs
            ai_response = f"SQL validation failed: {validation_message}"

        state = add_ai_message(state, ai_response)

        if checker_tool:
            tool_call_result = ToolCallResult(
                tool_name="sql_db_query_checker",
                tool_input={"query": generated_sql},
                tool_output=checker_msg or validation_message,
                success=(checker_msg is None)
                or (
                    "error" not in (checker_msg or "").lower()
                    and "invalid" not in (checker_msg or "").lower()
                ),
                execution_time=time.time() - start_time,
            )
            state = add_tool_call_result(state, tool_call_result)

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_VALIDATION, execution_time)

        return state

    except Exception as e:
        error_message = f"SQL validation failed: {str(e)}"
        state = add_error(
            state, error_message, "sql_validation_error", ExecutionPhase.SQL_VALIDATION
        )
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["validation_retry_count"] = state.get("validation_retry_count", 0) + 1

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_VALIDATION, execution_time)

        return state
