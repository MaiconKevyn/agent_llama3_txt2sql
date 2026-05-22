"""Intent-planning workflow node."""

from __future__ import annotations

import time

from .intent_plan import build_intent_plan
from .state_models import ExecutionPhase, MessagesStateTXT2SQL
from .tool_planner import plan_tools


def intent_planning_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Populate structured intent and logical tool plan in workflow state."""

    start = time.time()
    intent_plan = build_intent_plan(state.get("user_query", ""))
    tool_plan = plan_tools(intent_plan)

    state["intent_plan"] = intent_plan.model_dump()
    state["tool_plan"] = [tool.model_dump() for tool in tool_plan]
    metadata = state.get("response_metadata", {}) or {}
    metadata["intent_planning"] = {
        "duration_seconds": round(time.time() - start, 4),
        "primary_task": intent_plan.primary_task,
        "presentation": intent_plan.presentation,
        "tools": [tool.name for tool in tool_plan],
    }
    state["response_metadata"] = metadata
    state["current_phase"] = ExecutionPhase.REASONING
    return state
