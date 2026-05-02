"""Deterministic guardrails for when multi-query is allowed."""

import re
import time
from typing import Tuple

from .state_models import ExecutionPhase, MessagesStateTXT2SQL, QueryPlan, SubQuery
from .state_helpers import add_ai_message, update_phase
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()

MULTI_ELIGIBLE_PLAN_TYPES = {
    "fanout_concat",
    "bind_then_query",
    "verification_side_query",
}

_RANKING_PATTERN = re.compile(
    r"(top\s*\d+|ranking|maior(?:es)?|menor(?:es)?|mais\s+(?:comum|frequente|realizad[oa]s?|alto|alta)|principais?)",
    re.I,
)
_SINGLE_WINDOW_GROUP_PATTERN = re.compile(
    r"(por|em cada|de cada)\s+(estado|munic[ií]pio|hospital|especialidade|cidade|uf|regi[aã]o)",
    re.I,
)
_SINGLE_CTE_PATTERN = re.compile(
    r"(crescimento|queda|varia[cç][aã]o|delta|evolu[cç][aã]o|compar[ae]|entre\s+\d{4}.*\d{4}|per[ií]odo|ao longo do tempo|s[ée]rie temporal)",
    re.I,
)
_SET_INTERSECTION_PATTERN = re.compile(
    r"(interse[cç][aã]o|ao mesmo tempo|simultaneamente|top\s*\d+.*top\s*\d+|est[aã]o entre.*e entre)",
    re.I,
)
_GLOBAL_LOCAL_AVG_PATTERN = re.compile(
    r"(acima da m[eé]dia|abaixo da m[eé]dia|m[eé]dia estadual|m[eé]dia nacional|m[eé]dia do estado|m[eé]dia do brasil|2x a m[eé]dia|duas vezes a m[eé]dia)",
    re.I,
)
_PIVOT_COMPARE_PATTERN = re.compile(
    r"(lado a lado|versus|\bvs\b|compare|compara[cç][aã]o|em rela[cç][aã]o a)",
    re.I,
)
_BIND_PATTERN = re.compile(
    r"(depois|em seguida|a partir desse|a partir deste|desse hospital|deste hospital|desse munic[ií]pio|deste munic[ií]pio|s[ée]rie temporal)",
    re.I,
)
_ENTITY_DISCOVERY_PATTERN = re.compile(
    r"(qual|encontre|descubra).*(hospital|munic[ií]pio|cidade|procedimento|diagn[oó]stico)",
    re.I,
)
_VERIFICATION_PATTERN = re.compile(
    r"(verifique|valide|confira|checagem|cheque)",
    re.I,
)
_FANOUT_PATTERN = re.compile(
    r"(por sexo|sexo masculino|sexo feminino|entre homens e mulheres|faixa et[aá]ria|faixa de idade|grupo et[aá]rio)",
    re.I,
)


def _build_single_plan(user_query: str, plan_type: str, reasoning: str) -> QueryPlan:
    return QueryPlan(
        strategy="single",
        plan_type=plan_type,
        reasoning=reasoning,
        merge_strategy="none",
        output_nodes=["sq1"],
        expected_output_shape={},
        verifier_checks=[],
        fallback_policy={},
        sub_queries=[
            SubQuery(
                id="sq1",
                description=user_query,
                purpose="final_output",
                output_role="output",
            )
        ],
    )


def classify_plan_type(user_query: str) -> Tuple[str, str]:
    """Classify the query into a routing bucket using deterministic heuristics."""
    query = (user_query or "").strip()

    if not query:
        return "single_default", "Query vazia; usar SQL único por segurança."

    if _GLOBAL_LOCAL_AVG_PATTERN.search(query):
        return "global_local_avg", "Comparações contra média global/estadual devem permanecer em uma SQL."

    if _SET_INTERSECTION_PATTERN.search(query):
        return "set_intersection", "Interseções de rankings exigem semântica relacional única."

    if _PIVOT_COMPARE_PATTERN.search(query):
        return "pivot_compare", "Comparações lado a lado são mais seguras em uma única SQL."

    if _SINGLE_WINDOW_GROUP_PATTERN.search(query) and _RANKING_PATTERN.search(query):
        return "single_window", "Ranking por grupo com partição deve permanecer em uma única SQL."

    if _ENTITY_DISCOVERY_PATTERN.search(query) and _BIND_PATTERN.search(query):
        return "bind_then_query", "A pergunta pede descobrir uma entidade e depois detalhá-la."

    # Two named states + ranking ("3 X no estado A e no estado B") → per-group top-N
    _two_state_re = re.compile(
        r"no\s+estado\s+(?:de\s+|do\s+|da\s+)?[A-Z]{2}\b.*?\bno\s+estado\s+(?:de\s+|do\s+|da\s+)?[A-Z]{2}\b",
    )
    if _two_state_re.search(query) and _RANKING_PATTERN.search(query):
        return "single_window", "Top-N por estado nomeado deve usar ROW_NUMBER OVER PARTITION BY em SQL única."

    if _SINGLE_CTE_PATTERN.search(query):
        return "single_cte", "Comparações temporais e lógica global devem permanecer em uma única SQL."

    if _VERIFICATION_PATTERN.search(query):
        return "verification_side_query", "A pergunta sugere uma checagem auxiliar separada."

    if _FANOUT_PATTERN.search(query):
        return "fanout_concat", "A pergunta pode ser particionada em grupos independentes com merge por concatenação."

    return "single_default", "Sem padrão de multi-query seguro; usar SQL único."


def plan_gate_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Apply deterministic routing guardrails before invoking the LLM planner."""
    start_time = time.time()

    user_query = state.get("user_query", "")

    if state.get("force_single_query"):
        plan_type = "single_default"
        reasoning = "force_single_query está ativo; planner multi desabilitado para esta execução."
    else:
        plan_type, reasoning = classify_plan_type(user_query)

    multi_query_allowed = plan_type in MULTI_ELIGIBLE_PLAN_TYPES

    state["plan_type"] = plan_type
    state["multi_query_allowed"] = multi_query_allowed
    state["allowed_multi_plan_types"] = sorted(MULTI_ELIGIBLE_PLAN_TYPES)
    state["execution_mode"] = "multi_candidate" if multi_query_allowed else "single"

    if not multi_query_allowed:
        state["query_plan"] = _build_single_plan(user_query, plan_type, reasoning)
        state["is_multi_query"] = False
    else:
        state["query_plan"] = None
        state["is_multi_query"] = False

    logger.info("Plan gate classified query", extra={
        "plan_type": plan_type,
        "multi_query_allowed": multi_query_allowed,
    })

    state = add_ai_message(
        state,
        f"Plan gate: {plan_type} ({'multi elegível' if multi_query_allowed else 'single obrigatório'}). {reasoning}"
    )
    state = update_phase(state, ExecutionPhase.REASONING, time.time() - start_time)
    return state
