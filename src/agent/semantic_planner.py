"""LLM-assisted semantic planner node with deterministic reconciliation."""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..semantic.catalog import render_catalog_context_for_plan
from ..semantic.plan_reconciler import reconcile_semantic_plans
from ..semantic.plan_schema import SemanticPlan
from ..utils.logging_config import get_nodes_logger
from .llm_manager import get_llm_manager
from .state_helpers import add_ai_message, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL

logger = get_nodes_logger()


class SemanticPlannerOutput(BaseModel):
    semantic_plan: SemanticPlan = Field(
        description="Structured semantic plan for the user question"
    )
    reasoning: str = Field(
        description="Brief reason for metric, dimension, filter and grain choices"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the semantic interpretation"
    )


_SEMANTIC_PLANNER_SYSTEM = """\
Você é um planejador semântico Text-to-SQL. Produza um SemanticPlan estruturado
para uma pergunta sobre a base SUS sem usar exemplos de benchmark, respostas
esperadas ou IDs de avaliação.

Regras:
- Preserve a intenção da pergunta, shape esperado, granularidade, métricas e filtros.
- Use apenas métricas/dimensões compatíveis com o catálogo semântico fornecido.
- Para taxas, preserve denominador e use condição de desfecho no numerador.
- Para top-N por grupo, marque top_n_scope=per_group.
- Para ausência/nunca/sem registro, inclua a constraint de anti-condição.
- Se houver ambiguidade real, registre em ambiguities em vez de inventar regra.
"""


def semantic_planner_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Confirm or enrich the heuristic semantic plan with structured LLM output."""
    start_time = time.time()
    heuristic_plan_raw = state.get("semantic_plan")
    if not heuristic_plan_raw:
        return state

    try:
        heuristic_plan = SemanticPlan.model_validate(heuristic_plan_raw)
        llm_manager = get_llm_manager()
        catalog_context = render_catalog_context_for_plan(heuristic_plan)
        selected_tables = state.get("selected_tables", [])
        prompt = (
            f"Pergunta: {state.get('user_query', '')}\n\n"
            f"Tabelas selecionadas: {selected_tables}\n\n"
            f"Plano heurístico atual:\n{heuristic_plan.to_prompt_block()}\n\n"
            f"{catalog_context}\n\n"
            "Retorne um SemanticPlan estruturado. Não inclua SQL."
        )

        output = llm_manager.invoke_chat_structured(
            [
                SystemMessage(content=_SEMANTIC_PLANNER_SYSTEM),
                HumanMessage(content=prompt),
            ],
            SemanticPlannerOutput,
        )
        reconciliation = reconcile_semantic_plans(heuristic_plan, output.semantic_plan)
        state["semantic_plan"] = reconciliation.reconciled_plan.model_dump(exclude_none=True)
        meta = state.get("response_metadata", {}) or {}
        meta["semantic_planner"] = {
            "mode": "llm_reconciled",
            "confidence": output.confidence,
            "reasoning": output.reasoning,
            "conflicts": reconciliation.conflicts,
            "accepted_llm_fields": reconciliation.accepted_llm_fields,
            "rejected_llm_fields": reconciliation.rejected_llm_fields,
        }
        meta["semantic_plan"] = state["semantic_plan"]
        meta["semantic_constraints"] = reconciliation.reconciled_plan.constraints
        meta["semantic_null_policy"] = reconciliation.reconciled_plan.null_policy
        state["response_metadata"] = meta
        state = add_ai_message(
            state,
            f"Semantic planner reconciled plan with {len(reconciliation.conflicts)} conflict(s).",
        )
        logger.info(
            "Semantic planner reconciled plan",
            extra={
                "confidence": output.confidence,
                "conflict_count": len(reconciliation.conflicts),
            },
        )
    except Exception as exc:
        meta = state.get("response_metadata", {}) or {}
        meta["semantic_planner"] = {
            "mode": "heuristic_fallback",
            "error": str(exc),
        }
        state["response_metadata"] = meta
        logger.warning("Semantic planner fallback to heuristic plan", extra={"error": str(exc)})

    state = update_phase(state, ExecutionPhase.REASONING, time.time() - start_time)
    return state
