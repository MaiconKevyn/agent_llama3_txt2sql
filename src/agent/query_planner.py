"""Query planner node — emits structured multi-query plans for eligible cases only."""

import json
import time
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from .llm_manager import get_llm_manager
from .plan_gate import MULTI_ELIGIBLE_PLAN_TYPES, _build_single_plan
from .state_models import ExecutionPhase, MessagesStateTXT2SQL, QueryPlan, SubQuery
from .state_helpers import add_ai_message, update_phase
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()

_SUPPORTED_MERGE_STRATEGIES = {
    "fanout_concat": {"concat"},
    "bind_then_query": {"final_sql", "scalar_bind"},
    "verification_side_query": {"verifier_only", "final_sql"},
}

_DEFAULT_MERGE_STRATEGY = {
    "fanout_concat": "concat",
    "bind_then_query": "final_sql",
    "verification_side_query": "verifier_only",
}

_DEFAULT_VERIFIER_CHECKS = [
    "row_count",
    "column_count",
    "required_groups",
    "no_intermediate_rows",
    "constraints_preserved",
]

_SYSTEM_PROMPT = """\
You are the multi-query planner for a Brazilian healthcare SQL agent (DATASUS/SIH-RS).

You only receive requests that were already classified as SAFE for multi-query.
Return a plan that the runtime can execute deterministically.

Supported plan types:
- fanout_concat: independent partitions, same output columns, merge by concat only
- bind_then_query: one sub-query finds a small binding value, final dependent sub-query returns the final answer
- verification_side_query: one sub-query checks an invariant, one output sub-query returns the final answer

Hard constraints:
- max 4 sub_queries
- no circular depends_on
- every plan MUST define output_nodes
- every sub_query MUST define output_role in {output, intermediate, verifier}
- for bind_then_query and verification_side_query, exactly one output sub-query should carry the final answer
- NEVER emit set_intersection
- NEVER ask the synthesizer to compute rankings, deltas, averages, thresholds, intersections, or joins
- if unsure, return strategy=single

Return JSON only:
{
  "strategy": "multi" | "single",
  "plan_type": "...",
  "reasoning": "...",
  "merge_strategy": "concat | final_sql | scalar_bind | verifier_only",
  "output_nodes": ["sq2"],
  "required_constraints": [{"type": "...", "value": "..."}],
  "expected_output_shape": {
    "row_mode": "unknown | exact | at_most",
    "row_count": null,
    "column_count": 2,
    "column_aliases": ["col1", "col2"],
    "group_labels": []
  },
  "verifier_checks": ["row_count", "column_count", "no_intermediate_rows"],
  "fallback_policy": {
    "on_shape_mismatch": "rerun_single",
    "on_unsupported_merge": "rerun_single",
    "on_missing_output_nodes": "rerun_single"
  },
  "sub_queries": [
    {
      "id": "sq1",
      "description": "...",
      "purpose": "partition | binding | verification | final_output",
      "output_role": "output | intermediate | verifier",
      "depends_on": [],
      "expected_result_kind": "rowset | scalar | id_list",
      "expected_max_rows": 5,
      "required_constraints": ["..."],
      "bind_keys": ["..."]
    }
  ]
}
"""


def _strip_json_fences(response_text: str) -> str:
    if "```json" in response_text:
        return response_text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in response_text:
        return response_text.split("```", 1)[1].split("```", 1)[0].strip()
    return response_text.strip()


def _build_subqueries(sqs_data: List[Dict], user_query: str) -> List[SubQuery]:
    sub_queries: List[SubQuery] = []
    for i, sq in enumerate(sqs_data[:4]):
        sub_queries.append(
            SubQuery(
                id=sq.get("id", f"sq{i + 1}"),
                description=sq.get("description") or sq.get("question") or user_query,
                purpose=sq.get("purpose", "final_output"),
                output_role=sq.get("output_role", "output"),
                expected_result_kind=sq.get("expected_result_kind", "rowset"),
                expected_max_rows=sq.get("expected_max_rows"),
                required_constraints=sq.get("required_constraints", []) or [],
                bind_keys=sq.get("bind_keys", []) or [],
                depends_on=sq.get("depends_on", []) or [],
            )
        )
    return sub_queries


def _normalize_query_plan(plan_data: Dict, user_query: str, gate_plan_type: str) -> QueryPlan:
    strategy = plan_data.get("strategy", "single")
    if strategy != "multi" or gate_plan_type not in MULTI_ELIGIBLE_PLAN_TYPES:
        return _build_single_plan(
            user_query,
            "single_default",
            "Planner returned single or unsupported plan; using single-query fallback.",
        )

    sub_queries = _build_subqueries(plan_data.get("sub_queries", []), user_query)
    if len(sub_queries) < 2:
        return _build_single_plan(
            user_query,
            "single_default",
            "Planner did not provide enough sub-queries for a safe multi plan.",
        )

    valid_ids = {sq.id for sq in sub_queries}
    for sq in sub_queries:
        sq.depends_on = [dep for dep in sq.depends_on if dep in valid_ids and dep != sq.id]

    plan_type = plan_data.get("plan_type", gate_plan_type)
    if plan_type != gate_plan_type:
        plan_type = gate_plan_type

    merge_strategy = plan_data.get("merge_strategy") or _DEFAULT_MERGE_STRATEGY[plan_type]
    if merge_strategy not in _SUPPORTED_MERGE_STRATEGIES.get(plan_type, set()):
        return _build_single_plan(
            user_query,
            "single_default",
            f"Planner emitted unsupported merge strategy '{merge_strategy}'.",
        )

    output_nodes = plan_data.get("output_nodes") or [
        sq.id for sq in sub_queries if sq.output_role == "output"
    ]
    output_nodes = [sq_id for sq_id in output_nodes if sq_id in valid_ids]
    if not output_nodes:
        return _build_single_plan(
            user_query,
            "single_default",
            "Planner omitted output_nodes for multi-query plan.",
        )

    expected_output_shape = plan_data.get("expected_output_shape", {}) or {}
    if "column_count" not in expected_output_shape and plan_type == "fanout_concat":
        expected_output_shape["column_count"] = None

    return QueryPlan(
        strategy="multi",
        reasoning=plan_data.get("reasoning", ""),
        plan_type=plan_type,
        merge_strategy=merge_strategy,
        output_nodes=output_nodes,
        required_constraints=plan_data.get("required_constraints", []) or [],
        expected_output_shape=expected_output_shape,
        verifier_checks=plan_data.get("verifier_checks", []) or list(_DEFAULT_VERIFIER_CHECKS),
        fallback_policy=plan_data.get("fallback_policy", {}) or {
            "on_shape_mismatch": "rerun_single",
            "on_unsupported_merge": "rerun_single",
            "on_missing_output_nodes": "rerun_single",
        },
        sub_queries=sub_queries,
    )


def query_planner_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Generate a structured plan for multi-eligible queries."""
    start_time = time.time()

    try:
        gate_plan_type = state.get("plan_type") or "single_default"
        user_query = state.get("user_query", "")

        if gate_plan_type not in MULTI_ELIGIBLE_PLAN_TYPES or not state.get("multi_query_allowed"):
            query_plan = state.get("query_plan") or _build_single_plan(
                user_query,
                gate_plan_type,
                "Plan gate deterministically selected the single-query route.",
            )
            state["query_plan"] = query_plan
            state["is_multi_query"] = False
            state["execution_mode"] = "single"
            state = update_phase(state, ExecutionPhase.REASONING, time.time() - start_time)
            return state

        llm_manager = get_llm_manager()
        schema_context = state.get("schema_context", "")
        selected_tables = state.get("selected_tables", [])

        allowed_merges = ", ".join(sorted(_SUPPORTED_MERGE_STRATEGIES[gate_plan_type]))
        human_prompt = (
            f"User question: {user_query}\n\n"
            f"Gate-selected plan_type: {gate_plan_type}\n"
            f"Allowed merge strategies: {allowed_merges}\n\n"
            f"Selected tables: {', '.join(selected_tables) if selected_tables else 'unknown'}\n\n"
            f"Schema context (excerpt):\n{schema_context[:1800]}\n\n"
            "Produce a structured multi-query plan for this allowed plan_type only."
        )

        response = llm_manager.invoke_chat([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ])
        response_text = response.content if hasattr(response, "content") else str(response)
        plan_data = json.loads(_strip_json_fences(response_text))

        query_plan = _normalize_query_plan(plan_data, user_query, gate_plan_type)

        state["query_plan"] = query_plan
        state["plan_type"] = query_plan.plan_type
        state["is_multi_query"] = query_plan.strategy == "multi"
        state["execution_mode"] = "multi" if state["is_multi_query"] else "single"

        logger.info("Query planner decided", extra={
            "strategy": query_plan.strategy,
            "plan_type": query_plan.plan_type,
            "merge_strategy": query_plan.merge_strategy,
            "n_sub_queries": len(query_plan.sub_queries),
        })

        state = add_ai_message(
            state,
            f"Query plan: {query_plan.strategy}/{query_plan.plan_type} com "
            f"{len(query_plan.sub_queries)} sub-consultas e merge {query_plan.merge_strategy}."
        )
        state = update_phase(state, ExecutionPhase.REASONING, time.time() - start_time)
        return state

    except Exception as e:
        logger.warning("Query planner failed — defaulting to single", extra={"error": str(e)})
        user_query = state.get("user_query", "")
        gate_plan_type = state.get("plan_type") or "single_default"
        state["query_plan"] = _build_single_plan(
            user_query,
            gate_plan_type if gate_plan_type not in MULTI_ELIGIBLE_PLAN_TYPES else "single_default",
            f"Planner error: {str(e)[:120]}",
        )
        state["is_multi_query"] = False
        state["execution_mode"] = "single"
        state = update_phase(state, ExecutionPhase.REASONING, time.time() - start_time)
        return state
