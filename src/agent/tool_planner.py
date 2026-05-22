"""Tool planning from structured intent contracts."""

from __future__ import annotations

from .intent_plan import IntentPlan, ToolRequest


def plan_tools(intent_plan: IntentPlan) -> list[ToolRequest]:
    """Select logical tools needed to satisfy an intent plan."""

    tools: list[ToolRequest] = []

    def add(name: str, reason: str) -> None:
        if name not in {tool.name for tool in tools}:
            tools.append(ToolRequest(name=name, reason=reason))

    if intent_plan.primary_task == "out_of_scope" or intent_plan.requires_clarification:
        add("clarify_or_refuse", "question is outside the supported schema or needs clarification")
        return tools

    add("inspect_schema", "confirm available tables and columns before SQL compilation")
    if intent_plan.concept_slots or intent_plan.cohort_slots:
        add("resolve_concepts", "normalize clinical, population, or operational concepts")
    if intent_plan.temporal_scope is not None and intent_plan.temporal_scope.type != "none":
        add("resolve_temporal_scope", "normalize requested time window")
    if len(intent_plan.concept_slots) > 0 or len(intent_plan.grouping_slots) > 0:
        add("resolve_join_policy", "validate joins required by dimensions and concepts")
    add("compile_sql", "compile the resolved domain plan to SQL")
    add("execute_sql", "execute validated SQL against the database")
    add("validate_result_contract", "check result shape and metric semantics")
    if intent_plan.presentation in {"chart", "mixed"}:
        add("build_chart", "render a chart-compatible result")
    return tools
