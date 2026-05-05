"""Response generation node and formatting helpers."""

import time
from typing import Any, Dict, List

from .llm_manager import get_llm_manager
from .state_models import MessagesStateTXT2SQL, QueryRoute, ExecutionPhase
from .state_helpers import add_ai_message, update_phase, add_error, clean_conversation_messages
from ..utils.logging_config import get_nodes_logger

logger = get_nodes_logger()


def generate_response_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Generate Response Node - Format final response

    Generates natural language response based on query results or provides conversational response
    Following official LangGraph SQL agent patterns
    """
    start_time = time.time()

    try:
        llm_manager = get_llm_manager()
        user_query = state["user_query"]
        query_route = state.get("query_route", QueryRoute.DATABASE)

        if query_route == QueryRoute.CONVERSATIONAL:
            result = llm_manager.generate_conversational_response(
                user_query=user_query,
                conversation_history=clean_conversation_messages(state["messages"]),
            )

            if result["success"]:
                final_response = result["response"]
            else:
                final_response = f"Desculpe, não consegui processar sua pergunta: {result.get('error', 'Erro desconhecido')}"

        else:
            sql_execution_result = state.get("sql_execution_result")

            if sql_execution_result and sql_execution_result.success:
                final_response = _generate_formatted_response(
                    llm_manager=llm_manager,
                    user_query=user_query,
                    sql_query=sql_execution_result.sql_query,
                    results=sql_execution_result.results,
                    row_count=sql_execution_result.row_count,
                )
            else:
                error_message = state.get("current_error", "Erro desconhecido")
                final_response = f"Não foi possível processar sua consulta: {error_message}"

        state["final_response"] = final_response
        state["success"] = not bool(state.get("current_error"))
        state["completed"] = True

        state = add_ai_message(state, final_response)

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.COMPLETED, execution_time)

        return state

    except Exception as e:
        error_message = f"Response generation failed: {str(e)}"
        state = add_error(state, error_message, "response_generation_error", ExecutionPhase.RESPONSE_FORMATTING)

        state["final_response"] = f"Erro interno: {error_message}"
        state["success"] = False
        state["completed"] = True

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.COMPLETED, execution_time)

        return state


def _generate_formatted_response(
    llm_manager,
    user_query: str,
    sql_query: str,
    results: List[Dict[str, Any]],
    row_count: int,
) -> str:
    """
    Generate user-friendly formatted response using LLM.

    Uses the LLM to interpret SQL results and create natural language responses
    that are more readable and informative for end users.
    """
    try:
        if row_count == 0:
            return "Nenhum resultado encontrado para sua consulta."

        MAX_RESULTS_TO_SHOW = 10
        MAX_RESULT_STRING_LENGTH = 1000
        MAX_TOTAL_RESULTS_LENGTH = 5000

        results_text = ""
        if row_count == 1 and len(results) == 1:
            result_value = results[0].get("result", "")
            result_str = str(result_value)
            if len(result_str) > MAX_RESULT_STRING_LENGTH:
                results_text = result_str[:MAX_RESULT_STRING_LENGTH] + f"... (resultado truncado, {len(result_str)} caracteres total)"
            else:
                results_text = result_str
        else:
            results_to_show = min(len(results), MAX_RESULTS_TO_SHOW)
            for i, result in enumerate(results[:results_to_show], 1):
                result_value = result.get('result', '')
                result_str = str(result_value)
                if len(result_str) > MAX_RESULT_STRING_LENGTH:
                    result_str = result_str[:MAX_RESULT_STRING_LENGTH] + "..."
                line = f"{i}. {result_str}\n"
                if len(results_text) + len(line) > MAX_TOTAL_RESULTS_LENGTH:
                    results_text += "... (saída truncada para evitar resposta excessivamente longa)\n"
                    break
                results_text += line
            if row_count > results_to_show:
                results_text += f"... (mostrando {results_to_show} de {row_count} resultados)"

        if len(results_text) > MAX_TOTAL_RESULTS_LENGTH:
            results_text = results_text[:MAX_TOTAL_RESULTS_LENGTH] + "... (resposta truncada por segurança)"

        formatting_prompt = f"""Transforme o resultado técnico em uma resposta natural e concisa em português.

        Pergunta: "{user_query}"
        Resultado: {results_text}

        REGRAS IMPORTANTES:
        1. Seja CONCISO
        2. Responda APENAS o que foi perguntado
        3. Use linguagem natural em português brasileiro
        4. Formate números adequadamente (1.234 não 1234)
        5. NÃO adicione explicações extras, disclaimers ou ofertas de ajuda
        6. NÃO mencione SQL, tabelas ou detalhes técnicos
        7. Preserve identificadores exatamente como aparecem no resultado (ex.: CNES 2772299);
           não troque códigos por rótulos inventados como "Hospital 1"
        8. Se o resultado estiver truncado, resuma apenas os valores visíveis e não invente totalizações
        9. Para listas longas, mostre no máximo 10 itens e mantenha a ordenação do resultado

        EXEMPLOS:
        Pergunta: "Quantos pacientes existem?" → "Existem 24.485 pacientes cadastrados."
        Pergunta: "Qual cidade com mais mortes de homens?" → "A cidade onde morreram mais homens foi Ijuí, com 212 mortes."
        Pergunta: "Quantas mulheres?" → "Existem 15.234 pacientes do sexo feminino."
        Pergunta: "Quais hospitais têm mais internações?" e resultado [(2772299, 109261)] → "O CNES 2772299 tem 109.261 internações."

        Resposta concisa:"""

        format_result = llm_manager.generate_conversational_response(
            user_query=formatting_prompt,
            context=None,
            conversation_history=[],
        )

        if format_result["success"]:
            formatted_response = format_result["response"].strip()

            MAX_FINAL_RESPONSE_LENGTH = 2000
            if len(formatted_response) > MAX_FINAL_RESPONSE_LENGTH:
                formatted_response = formatted_response[:MAX_FINAL_RESPONSE_LENGTH] + "... (resposta limitada por segurança)"

            if len(formatted_response) < 10 or "erro" in formatted_response.lower():
                return _generate_fallback_response(user_query, results_text, row_count)

            return formatted_response
        else:
            return _generate_fallback_response(user_query, results_text, row_count)

    except Exception as e:
        logger.error("Response formatting failed", extra={"error": str(e)})
        return _generate_fallback_response(user_query, results_text if 'results_text' in dir() else str(results), row_count)


def _generate_fallback_response(user_query: str, results_text: str, row_count: int) -> str:
    """Generate basic fallback response when LLM formatting fails."""
    MAX_FALLBACK_LENGTH = 1000

    if len(results_text) > MAX_FALLBACK_LENGTH:
        results_text = results_text[:MAX_FALLBACK_LENGTH] + "... (resposta truncada)"

    if row_count == 0:
        return "Nenhum resultado encontrado para sua consulta."
    elif row_count == 1:
        if results_text.strip().startswith("[('") and results_text.strip().endswith("')]"):
            try:
                import ast
                parsed = ast.literal_eval(results_text.strip())
                if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], tuple):
                    if len(parsed[0]) == 2:
                        city, count = parsed[0]
                        return f"Resultado: {city} com {count:,} registros."
                    elif len(parsed[0]) == 1:
                        value = parsed[0][0]
                        if isinstance(value, (int, float)):
                            return f"Resultado: {value:,}"
                        else:
                            return f"Resultado: {value}"
            except Exception:
                pass
        return f"Resultado: {results_text}"
    else:
        return f"Encontrados {row_count} resultados:\n{results_text}"


def clarification_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Fallback clarification response when intent cannot be determined."""
    prompt = (
        "Não consegui entender totalmente sua pergunta. "
        "Por favor, reformule adicionando contexto (tabelas, filtros, período)."
    )
    state = add_ai_message(state, prompt)
    state["final_response"] = prompt
    state["completed"] = True
    state = update_phase(state, ExecutionPhase.RESPONSE_FORMATTING, 0.0)
    return state
