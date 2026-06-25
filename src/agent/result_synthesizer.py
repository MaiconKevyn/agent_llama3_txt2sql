"""Result synthesizer — formats verified multi-query outputs into a final answer."""

import time
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from .llm_manager import get_llm_manager
from .state_models import ExecutionPhase, MessagesStateTXT2SQL
from .state_helpers import add_ai_message, add_error, update_phase
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()

_SYSTEM_PROMPT = """\
Você é um assistente especializado em dados de saúde pública brasileira (DATASUS/SIH-RS).
Sua tarefa: sintetizar um resultado tabular já verificado em uma resposta curta, clara e direta em português.

Diretrizes:
- Use apenas os dados fornecidos.
- Não mencione SQL, planner, subconsultas, merge ou validação.
- Se houver múltiplas linhas, organize a resposta de forma objetiva.
"""


def _format_rows_for_prompt(rows: List[Any], max_rows: int = 25) -> str:
    if not rows:
        return "[sem linhas]"
    display_rows = rows[:max_rows]
    lines = [f"Linha {idx}: {list(row)}" for idx, row in enumerate(display_rows, 1)]
    if len(rows) > max_rows:
        lines.append(f"... ({len(rows) - max_rows} linhas adicionais omitidas)")
    return "\n".join(lines)


def result_synthesizer_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Generate the final natural-language answer from verified merged rows."""
    start_time = time.time()

    try:
        merged_rows = state.get("merged_rows")
        user_query = state.get("user_query", "")
        query_plan = state.get("query_plan")
        verifier_outcome = state.get("verifier_outcome") or {}

        if not verifier_outcome.get("passed") or merged_rows is None:
            error_msg = "Result synthesizer recebeu multi-query sem rows verificadas."
            state = add_error(state, error_msg, "sql_execution_error", ExecutionPhase.RESPONSE_FORMATTING)
            state["final_response"] = (
                "Não foi possível consolidar a resposta automaticamente. Tente reformular a pergunta."
            )
            state["success"] = False
            state["completed"] = True
            state = update_phase(state, ExecutionPhase.RESPONSE_FORMATTING, time.time() - start_time)
            return state

        llm_manager = get_llm_manager()
        human_prompt = (
            f"Pergunta original do usuário: {user_query}\n\n"
            f"Tipo de plano: {query_plan.plan_type if query_plan else 'multi'}\n"
            f"Estratégia de merge: {query_plan.merge_strategy if query_plan else 'unknown'}\n\n"
            f"Linhas finais verificadas:\n{_format_rows_for_prompt(merged_rows)}\n\n"
            "Responda ao usuário de forma clara e objetiva:"
        )

        response = llm_manager.invoke_chat([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ])

        final_response = response.content.strip() if hasattr(response, "content") else str(response)

        state["final_response"] = final_response
        state["success"] = True
        state["completed"] = True
        state["final_result_rows"] = merged_rows

        if state.get("final_sql_query"):
            state["generated_sql"] = state["final_sql_query"]
            state["validated_sql"] = state["final_sql_query"]
        else:
            state["generated_sql"] = ""
            state["validated_sql"] = ""

        state = add_ai_message(state, final_response)

        logger.info("Result synthesizer complete", extra={
            "plan_type": query_plan.plan_type if query_plan else None,
            "row_count": len(merged_rows),
        })

        state = update_phase(state, ExecutionPhase.RESPONSE_FORMATTING, time.time() - start_time)
        return state

    except Exception as e:
        error_msg = f"Result synthesizer failed: {str(e)}"
        logger.error("result_synthesizer_node error", extra={"error": str(e)})
        state = add_error(state, error_msg, "sql_execution_error", ExecutionPhase.RESPONSE_FORMATTING)
        state["completed"] = True
        state["success"] = False
        state = update_phase(state, ExecutionPhase.RESPONSE_FORMATTING, time.time() - start_time)
        return state
