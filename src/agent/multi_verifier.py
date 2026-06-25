"""Verifier for multi-query plans before accepting merged rows as final output."""

import time
import re
from typing import Any, Dict, List, Optional, Tuple

from .state_models import ExecutionPhase, MessagesStateTXT2SQL, QueryPlan
from .state_helpers import add_ai_message, update_phase
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()

_SUPPORTED_MERGES = {"concat", "scalar_bind", "final_sql", "verifier_only"}


def _get_result_map(sub_query_results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {result["id"]: result for result in sub_query_results}


def _append_failure(state: MessagesStateTXT2SQL, failure_code: str) -> None:
    failures = state.get("failure_taxonomy", [])
    if failure_code not in failures:
        failures.append(failure_code)
    state["failure_taxonomy"] = failures


def _validate_constraints(plan: QueryPlan, output_results: List[Dict[str, Any]]) -> Optional[str]:
    required_constraints = plan.required_constraints or []
    if not required_constraints:
        return None

    combined_sql = "\n".join(result.get("validated_sql") or result.get("sql") or "" for result in output_results)
    lower_sql = combined_sql.lower()

    for constraint in required_constraints:
        value = constraint.get("value") if isinstance(constraint, dict) else str(constraint)
        if not value:
            continue
        looks_sql_like = bool(re.search(r"[=<>]|\d|'.+?'|\".+?\"", value))
        if looks_sql_like and len(value) <= 80 and value.lower() not in lower_sql:
            return f"Missing required constraint in output SQL: {value}"
    return None


def _validate_required_groups(plan: QueryPlan, merged_rows: List) -> Optional[str]:
    shape = plan.expected_output_shape or {}
    group_labels = shape.get("group_labels") or []
    if not group_labels:
        return None

    merged_text = "\n".join(" | ".join(str(item) for item in row) for row in merged_rows)
    for label in group_labels:
        if str(label) not in merged_text:
            return f"Missing required group label: {label}"
    return None


def _validate_row_shape(plan: QueryPlan, merged_rows: List) -> Optional[str]:
    shape = plan.expected_output_shape or {}
    column_count = shape.get("column_count")
    if column_count is not None:
        for row in merged_rows:
            if len(row) != column_count:
                return f"Column count mismatch: expected {column_count}, got {len(row)}"

    row_mode = shape.get("row_mode")
    row_count = shape.get("row_count")
    if row_count is not None and row_mode:
        actual = len(merged_rows)
        if row_mode == "exact" and actual != row_count:
            return f"Row count mismatch: expected exactly {row_count}, got {actual}"
        if row_mode == "at_most" and actual > row_count:
            return f"Row count mismatch: expected at most {row_count}, got {actual}"
        if row_mode == "at_least" and actual < row_count:
            return f"Row count mismatch: expected at least {row_count}, got {actual}"

    return None


def _validate_binding_limits(sub_query_results: List[Dict[str, Any]]) -> Optional[str]:
    for result in sub_query_results:
        if result.get("purpose") != "binding":
            continue
        expected_max_rows = result.get("expected_max_rows")
        parsed_rows = result.get("parsed_rows") or []
        if expected_max_rows is not None and len(parsed_rows) > expected_max_rows:
            return (
                f"Binding sub-query {result['id']} returned {len(parsed_rows)} rows; "
                f"expected at most {expected_max_rows}"
            )
    return None


def _merge_output_rows(plan: QueryPlan, sub_query_results: List[Dict[str, Any]]) -> Tuple[Optional[List], Optional[str], Optional[str]]:
    result_map = _get_result_map(sub_query_results)
    merge_strategy = plan.merge_strategy

    if merge_strategy not in _SUPPORTED_MERGES:
        return None, None, f"Unsupported merge strategy: {merge_strategy}"

    output_results: List[Dict[str, Any]] = []
    for node_id in plan.output_nodes:
        result = result_map.get(node_id)
        if not result or not result.get("success"):
            return None, None, f"Missing successful output node: {node_id}"
        output_results.append(result)

    if merge_strategy == "concat":
        merged_rows: List = []
        for result in output_results:
            parsed_rows = result.get("parsed_rows")
            if parsed_rows is None:
                return None, None, f"Output node {result['id']} has unparsable rows."
            merged_rows.extend(parsed_rows)
        return merged_rows, "output_nodes_concat", None

    if len(output_results) != 1:
        return None, None, f"Merge strategy {merge_strategy} requires exactly one output node."

    output_result = output_results[0]
    parsed_rows = output_result.get("parsed_rows")
    if parsed_rows is None:
        return None, None, f"Output node {output_result['id']} has unparsable rows."

    return parsed_rows, output_result["id"], None


def multi_verifier_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Verify merged multi-query output before final synthesis."""
    start_time = time.time()

    query_plan: QueryPlan = state.get("query_plan")
    sub_query_results = state.get("sub_query_results", [])

    if not query_plan or query_plan.strategy != "multi":
        state["verifier_outcome"] = {"passed": True, "reason": "not_multi"}
        state = update_phase(state, ExecutionPhase.SQL_VALIDATION, time.time() - start_time)
        return state

    verifier_outcome: Dict[str, Any] = {
        "passed": False,
        "plan_type": query_plan.plan_type,
        "merge_strategy": query_plan.merge_strategy,
        "checks": [],
    }

    merged_rows, merged_rows_source, merge_error = _merge_output_rows(query_plan, sub_query_results)
    if merge_error:
        _append_failure(state, "unsupported_merge_strategy" if "Unsupported" in merge_error else "missing_output_node")
        state["single_fallback_active"] = True
        state["single_fallback_reason"] = merge_error
        state["execution_mode"] = "single_fallback"
        verifier_outcome["reason"] = merge_error
        state["verifier_outcome"] = verifier_outcome
        state = add_ai_message(state, f"Multi-query verifier acionou fallback single: {merge_error}")
        state = update_phase(state, ExecutionPhase.SQL_VALIDATION, time.time() - start_time)
        return state

    result_map = _get_result_map(sub_query_results)
    output_results = [result_map[node_id] for node_id in query_plan.output_nodes if node_id in result_map]

    checks = [
        ("binding_cardinality", _validate_binding_limits(sub_query_results), "binding_cardinality_exceeded"),
        ("row_shape", _validate_row_shape(query_plan, merged_rows), "wrong_shape"),
        ("required_groups", _validate_required_groups(query_plan, merged_rows), "missing_constraint"),
        ("constraints", _validate_constraints(query_plan, output_results), "missing_constraint"),
    ]

    for check_name, maybe_error, failure_code in checks:
        verifier_outcome["checks"].append({
            "name": check_name,
            "passed": maybe_error is None,
            "error": maybe_error,
        })
        if maybe_error is not None:
            _append_failure(state, failure_code)
            state["single_fallback_active"] = True
            state["single_fallback_reason"] = maybe_error
            state["execution_mode"] = "single_fallback"
            verifier_outcome["reason"] = maybe_error
            state["verifier_outcome"] = verifier_outcome
            state = add_ai_message(state, f"Multi-query verifier acionou fallback single: {maybe_error}")
            state = update_phase(state, ExecutionPhase.SQL_VALIDATION, time.time() - start_time)
            return state

    # No intermediate rows should leak into the final output.
    allowed_output_ids = set(query_plan.output_nodes)
    leaked_ids = [
        result["id"] for result in sub_query_results
        if result.get("success")
        and result.get("parsed_rows")
        and result["id"] not in allowed_output_ids
        and result.get("output_role") != "verifier"
        and result.get("purpose") != "binding"
    ]
    verifier_outcome["checks"].append({
        "name": "no_intermediate_rows",
        "passed": not leaked_ids,
        "error": f"Unexpected intermediate rows from {', '.join(leaked_ids)}" if leaked_ids else None,
    })
    if leaked_ids:
        _append_failure(state, "intermediate_row_leak")
        state["single_fallback_active"] = True
        state["single_fallback_reason"] = verifier_outcome["checks"][-1]["error"]
        state["execution_mode"] = "single_fallback"
        verifier_outcome["reason"] = state["single_fallback_reason"]
        state["verifier_outcome"] = verifier_outcome
        state = add_ai_message(state, f"Multi-query verifier acionou fallback single: {state['single_fallback_reason']}")
        state = update_phase(state, ExecutionPhase.SQL_VALIDATION, time.time() - start_time)
        return state

    state["merged_rows"] = merged_rows
    state["merged_rows_source"] = merged_rows_source
    state["final_result_rows"] = merged_rows
    if len(query_plan.output_nodes) == 1:
        output_sql = result_map[query_plan.output_nodes[0]].get("validated_sql") or result_map[query_plan.output_nodes[0]].get("sql")
        state["final_sql_query"] = output_sql

    verifier_outcome["passed"] = True
    verifier_outcome["reason"] = "ok"
    state["verifier_outcome"] = verifier_outcome
    state["single_fallback_active"] = False
    state["single_fallback_reason"] = None
    state["execution_mode"] = "multi_verified"

    logger.info("Multi-query verifier passed", extra={
        "plan_type": query_plan.plan_type,
        "merge_strategy": query_plan.merge_strategy,
        "row_count": len(merged_rows),
    })

    state = add_ai_message(
        state,
        f"Multi-query verifier aprovado: {query_plan.plan_type} com merge {query_plan.merge_strategy}."
    )
    state = update_phase(state, ExecutionPhase.SQL_VALIDATION, time.time() - start_time)
    return state
