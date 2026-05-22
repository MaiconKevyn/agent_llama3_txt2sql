"""Response generation node and formatting helpers."""

import time
from typing import Any

from ..utils.logging_config import get_nodes_logger
from ..visualization.data import normalize_result_rows
from .llm_manager import get_llm_manager
from .state_helpers import add_ai_message, add_error, clean_conversation_messages, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL, QueryRoute

logger = get_nodes_logger()


def build_domain_caveats(*, user_query: str, semantic_plan: dict[str, Any] | None) -> list[str]:
    """Return user-facing caveats for implicit domain policies."""

    filters = (semantic_plan or {}).get("filters", [])
    caveats: list[str] = []
    normalized = (user_query or "").lower()
    if (
        any(token in normalized for token in ["crianca", "criança", "criancas", "crianças", "pediatric"])
        and any(
            item.get("field") == "idade"
            and item.get("operator") == "<"
            and item.get("values") == ["18"]
            for item in filters
        )
    ):
        caveats.append("Crianca foi operacionalizado como idade menor que 18 anos.")
    if ("respirat" in normalized or "cid j" in normalized) and any(
        item.get("field") == "diagnostico_principal_prefix"
        and item.get("values") == ["J%"]
        for item in filters
    ):
        caveats.append("Causas respiratorias foram operacionalizadas como CID J00-J99.")
    if (
        "quais cid" in normalized or "quais cids" in normalized
    ) and "analisar" in normalized and any(
        item.get("field") == "diagnostico_principal_prefix" for item in filters
    ):
        caveats.append(
            "Lista candidata de CIDs; confirme o escopo clinico antes de usar em contagens."
        )
    if "cronica" in normalized or "cronicas" in normalized or "crônica" in normalized:
        caveats.append(
            "Doencas cronicas nao sao um unico bloco CID; confirme a lista de condicoes ou o escopo clinico."
        )
    if any(item.get("field") == "desfecho" for item in filters):
        caveats.append("Mortes hospitalares foram filtradas com MORTE=true.")
    return caveats


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

        domain_caveats = build_domain_caveats(
            user_query=user_query,
            semantic_plan=state.get("semantic_plan"),
        )
        state["domain_caveats"] = domain_caveats
        if domain_caveats and not state.get("current_error"):
            caveat_text = "Observacoes de escopo: " + " ".join(domain_caveats)
            if caveat_text not in final_response:
                final_response = f"{final_response}\n\n{caveat_text}"

        state["final_response"] = final_response
        state["success"] = not bool(state.get("current_error"))
        state["completed"] = True

        state = add_ai_message(state, final_response)

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.COMPLETED, execution_time)

        return state

    except Exception as e:
        error_message = f"Response generation failed: {str(e)}"
        state = add_error(
            state, error_message, "response_generation_error", ExecutionPhase.RESPONSE_FORMATTING
        )

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
    results: list[dict[str, Any]],
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

        MAX_RESULTS_TO_SHOW = 50
        MAX_RESULT_STRING_LENGTH = 1000
        MAX_TOTAL_RESULTS_LENGTH = 5000

        results_text = ""
        normalized_rows, _columns = normalize_result_rows(results, sql_query)
        analytic_response = _format_analytic_response_if_available(user_query, normalized_rows)
        if analytic_response:
            return analytic_response

        if row_count == 1 and len(results) == 1:
            result_value = normalized_rows[0] if normalized_rows else results[0].get("result", "")
            result_str = str(result_value)
            if len(result_str) > MAX_RESULT_STRING_LENGTH:
                results_text = (
                    result_str[:MAX_RESULT_STRING_LENGTH]
                    + f"... (resultado truncado, {len(result_str)} caracteres total)"
                )
            else:
                results_text = result_str
        else:
            results_to_show = min(len(results), MAX_RESULTS_TO_SHOW)
            is_partial_result = row_count > results_to_show
            display_rows = normalized_rows if normalized_rows else results
            for i, result in enumerate(display_rows[:results_to_show], 1):
                result_value = result if normalized_rows else result.get("result", "")
                result_str = str(result_value)
                if len(result_str) > MAX_RESULT_STRING_LENGTH:
                    result_str = result_str[:MAX_RESULT_STRING_LENGTH] + "..."
                line = f"{i}. {result_str}\n"
                if len(results_text) + len(line) > MAX_TOTAL_RESULTS_LENGTH:
                    results_text += (
                        "... (saída truncada para evitar resposta excessivamente longa)\n"
                    )
                    break
                results_text += line
            if is_partial_result:
                results_text += (
                    f"... (AMOSTRA PARCIAL: mostrando {results_to_show} de {row_count} resultados; "
                    "nao apresente como lista completa)"
                )
        result_scope_note = (
            f"Resultado parcial: foram enviados {min(row_count, MAX_RESULTS_TO_SHOW)} de {row_count} registros."
            if row_count > MAX_RESULTS_TO_SHOW
            else f"Resultado completo: foram enviados todos os {row_count} registros."
        )

        if len(results_text) > MAX_TOTAL_RESULTS_LENGTH:
            results_text = (
                results_text[:MAX_TOTAL_RESULTS_LENGTH] + "... (resposta truncada por segurança)"
            )

        formatting_prompt = f"""Transforme o resultado técnico em uma resposta natural e concisa em português.

        Pergunta: "{user_query}"
        Escopo do resultado: {result_scope_note}
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
        8. Se o resultado estiver truncado, diga explicitamente que é uma amostra parcial e não invente totalizações
        9. Para listas completas pequenas, preserve todos os grupos presentes no resultado
        10. Se o escopo disser "Resultado completo", NÃO diga que é amostra parcial

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
                formatted_response = (
                    formatted_response[:MAX_FINAL_RESPONSE_LENGTH]
                    + "... (resposta limitada por segurança)"
                )

            if len(formatted_response) < 10 or "erro" in formatted_response.lower():
                return _generate_fallback_response(user_query, results_text, row_count)

            return formatted_response
        else:
            return _generate_fallback_response(user_query, results_text, row_count)

    except Exception as e:
        logger.error("Response formatting failed", extra={"error": str(e)})
        return _generate_fallback_response(
            user_query, results_text if "results_text" in dir() else str(results), row_count
        )


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


def _format_analytic_response_if_available(
    user_query: str,
    rows: list[dict[str, Any]],
) -> str | None:
    if not rows:
        return None
    first_row = _analytic_package_from_row(rows[0])
    if first_row and first_row.get("analysis_type") in {
        "age_diagnosis_association",
        "categorical_outcome_association",
        "geographic_condition_rate",
        "temporal_condition_trend",
    }:
        return _format_analytic_response_from_package(user_query, first_row)
    return None


_ANALYTIC_PACKAGE_COLUMNS = {
    "age_diagnosis_association": [
        "analysis_type",
        "resolved_concept",
        "total_internacoes",
        "total_mortes",
        "idade_media",
        "idade_mediana",
        "denominador",
        "faixas_etarias",
        "top_idades",
        "rate_ratio_maior_igual_50_vs_menor_50",
        "rate_ratio_maior_igual_60_vs_menor_60",
        "idade_zero_total",
        "idade_zero_inconsistente_nasc",
        "idade_zero_compativel_menor_1_ano",
        "warnings",
    ],
    "categorical_outcome_association": [
        "analysis_type",
        "factor_name",
        "outcome",
        "total_internacoes",
        "total_mortes",
        "denominador",
        "group_distribution",
        "highest_group",
        "highest_rate",
        "lowest_group",
        "lowest_rate",
        "rate_ratio_highest_vs_lowest",
        "warnings",
    ],
    "geographic_condition_rate": [
        "analysis_type",
        "resolved_concept",
        "factor_name",
        "total_internacoes",
        "denominador",
        "group_distribution",
        "highest_group",
        "highest_rate",
        "lowest_group",
        "lowest_rate",
        "rate_ratio_highest_vs_lowest",
        "warnings",
    ],
    "temporal_condition_trend": [
        "analysis_type",
        "resolved_concept",
        "factor_name",
        "total_internacoes",
        "denominador",
        "time_series",
        "first_period",
        "first_total",
        "last_period",
        "last_total",
        "delta_absolute",
        "delta_percent",
        "peak_period",
        "peak_total",
        "warnings",
    ],
}


def _analytic_package_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    analysis_type = row.get("analysis_type")
    if analysis_type:
        return row

    first_value = row.get("col_1")
    if first_value not in _ANALYTIC_PACKAGE_COLUMNS:
        return None
    columns = _ANALYTIC_PACKAGE_COLUMNS[str(first_value)]
    values = [row.get(f"col_{index}") for index in range(1, len(columns) + 1)]
    return dict(zip(columns, values, strict=False))


def _format_analytic_response_from_package(user_query: str, package: dict[str, Any]) -> str:
    analysis_type = package.get("analysis_type")
    if analysis_type == "age_diagnosis_association":
        return _format_age_diagnosis_response_from_package(user_query, package)
    if analysis_type == "categorical_outcome_association":
        return _format_categorical_outcome_response_from_package(package)
    if analysis_type == "geographic_condition_rate":
        return _format_geographic_condition_response_from_package(package)
    if analysis_type == "temporal_condition_trend":
        return _format_temporal_condition_response_from_package(package)
    return ""


def _format_age_diagnosis_response_from_package(
    user_query: str, package: dict[str, Any]
) -> str:
    """Format a deterministic analytic package without asking the LLM to infer calculations."""
    concept = _humanize_clinical_label_for_response(
        str(package.get("resolved_concept") or "diagnostico informado")
    )
    total = _format_int(package.get("total_internacoes"))
    deaths = _format_int(package.get("total_mortes"))
    avg_age = _format_number(package.get("idade_media"))
    median_age = _format_number(package.get("idade_mediana"), decimals=0)
    denominator = _humanize_denominator(
        str(package.get("denominador") or "internacoes no mesmo escopo")
    )
    ratio_50 = _format_number(package.get("rate_ratio_maior_igual_50_vs_menor_50"))
    ratio_60 = _format_number(package.get("rate_ratio_maior_igual_60_vs_menor_60"))
    bands = _parse_age_band_distribution(str(package.get("faixas_etarias") or ""))
    top_ages = _parse_top_ages(str(package.get("top_idades") or ""))
    warnings = _humanize_warning(str(package.get("warnings") or ""))

    lines = [
        "Sim. Há uma associação observada entre idade e o diagnóstico resolvido nos dados.",
        "",
        f"Escopo usado: {concept}; denominador: {denominator}.",
        f"Resumo: {total} internações, {deaths} mortes nessas internações, idade média {avg_age} e mediana {median_age}.",
    ]

    if bands:
        lines.extend(
            [
                "",
                "| Faixa etária | Internações | Taxa por 100 mil denominador | % dos casos |",
                "|---|---:|---:|---:|",
            ]
        )
        for band in bands:
            lines.append(
                f"| {band['faixa']} | {band['total']} | {band['taxa']} | {band['percentual']} |"
            )

    objective_lines = []
    if ratio_50 != "-":
        objective_lines.append(f"a taxa em >=50 anos foi {ratio_50}x a taxa em <50 anos")
    if ratio_60 != "-":
        objective_lines.append(f"a taxa em >=60 anos foi {ratio_60}x a taxa em <60 anos")
    if top_ages:
        objective_lines.append("as idades com maior volume foram " + ", ".join(top_ages))

    if objective_lines:
        lines.extend(["", "Leitura objetiva: " + "; ".join(objective_lines) + "."])

    if warnings:
        lines.extend(["", f"Atenção sobre qualidade dos dados: {warnings}."])

    lines.append(
        "Limite: isto descreve associação observada nas internações, não causalidade individual."
    )
    return "\n".join(lines)


def _format_categorical_outcome_response_from_package(package: dict[str, Any]) -> str:
    factor = _humanize_factor(str(package.get("factor_name") or "categoria"))
    outcome = str(package.get("outcome") or "desfecho observado")
    total = _format_int(package.get("total_internacoes"))
    deaths = _format_int(package.get("total_mortes"))
    denominator = _humanize_denominator(str(package.get("denominador") or "internacoes"))
    groups = _parse_categorical_distribution(str(package.get("group_distribution") or ""))
    highest_group = str(package.get("highest_group") or "-")
    highest_rate = _format_number(package.get("highest_rate"))
    lowest_group = str(package.get("lowest_group") or "-")
    lowest_rate = _format_number(package.get("lowest_rate"))
    ratio = _format_number(package.get("rate_ratio_highest_vs_lowest"))
    warnings = _humanize_warning(str(package.get("warnings") or ""))

    lines = [
        f"Sim. Há diferença observada em {outcome} quando as internações são agrupadas por {factor}.",
        "",
        f"Escopo usado: {denominator}; denominador por grupo: internações do próprio grupo.",
        f"Resumo: {total} internações no denominador analisado e {deaths} mortes hospitalares.",
    ]
    if groups:
        lines.extend(
            [
                "",
                "| Grupo | Internações | Mortes | Taxa de mortalidade |",
                "|---|---:|---:|---:|",
            ]
        )
        for group in groups:
            lines.append(
                f"| {group['grupo']} | {group['total']} | {group['mortes']} | {group['taxa']}% |"
            )
    lines.extend(
        [
            "",
            (
                f"Leitura objetiva: maior taxa em {highest_group} ({highest_rate}%) e menor "
                f"em {lowest_group} ({lowest_rate}%); razão entre maior e menor taxa: {ratio}x."
            ),
        ]
    )
    if warnings:
        lines.extend(["", f"Atenção sobre escopo dos dados: {warnings}."])
    lines.append(
        "Limite: isto descreve associação observada nas internações, não causalidade individual."
    )
    return "\n".join(lines)


def _format_geographic_condition_response_from_package(package: dict[str, Any]) -> str:
    concept = _humanize_clinical_label(str(package.get("resolved_concept") or "diagnóstico informado"))
    total = _format_int(package.get("total_internacoes"))
    denominator = _humanize_denominator(str(package.get("denominador") or "internacoes"))
    groups = _parse_rate_distribution(str(package.get("group_distribution") or ""))
    highest_group = str(package.get("highest_group") or "-")
    highest_rate = _format_number(package.get("highest_rate"))
    lowest_group = str(package.get("lowest_group") or "-")
    lowest_rate = _format_number(package.get("lowest_rate"))
    ratio = _format_number(package.get("rate_ratio_highest_vs_lowest"))
    warnings = _humanize_warning(str(package.get("warnings") or ""))

    lines = [
        "Há variação observada entre UFs no recorte solicitado.",
        "",
        f"Escopo usado: {concept}; denominador: {denominator}.",
        f"Resumo: {total} internações no diagnóstico resolvido.",
    ]
    if groups:
        lines.extend(
            [
                "",
                "| UF | Internações | Denominador | Taxa por 100 mil | % dos casos |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for group in groups[:10]:
            lines.append(
                f"| {group['grupo']} | {group['total']} | {group['denominador']} | "
                f"{group['taxa']} | {group['percentual']}% |"
            )
    lines.extend(
        [
            "",
            (
                f"Leitura objetiva: maior taxa em {highest_group} ({highest_rate} por 100 mil) "
                f"e menor taxa não zero em {lowest_group} ({lowest_rate} por 100 mil); razão: {ratio}x."
            ),
        ]
    )
    if warnings:
        lines.extend(["", f"Atenção sobre escopo dos dados: {warnings}."])
    lines.append(
        "Limite: isto descreve distribuição observada nos registros, não risco populacional individual."
    )
    return "\n".join(lines)


def _format_temporal_condition_response_from_package(package: dict[str, Any]) -> str:
    concept = _humanize_clinical_label(str(package.get("resolved_concept") or "diagnóstico informado"))
    total = _format_int(package.get("total_internacoes"))
    denominator = _humanize_denominator(str(package.get("denominador") or "internacoes"))
    series = _parse_time_series(str(package.get("time_series") or ""))
    first_period = _format_period(package.get("first_period"))
    first_total = _format_int(package.get("first_total"))
    last_period = _format_period(package.get("last_period"))
    last_total = _format_int(package.get("last_total"))
    delta_absolute = _format_int(package.get("delta_absolute"))
    delta_percent = _format_number(package.get("delta_percent"))
    peak_period = _format_period(package.get("peak_period"))
    peak_total = _format_int(package.get("peak_total"))
    warnings = _humanize_warning(str(package.get("warnings") or ""))

    lines = [
        "Há uma tendência temporal observada no recorte solicitado.",
        "",
        f"Escopo usado: {concept}; denominador: {denominator}.",
        f"Resumo: {total} internações no diagnóstico resolvido ao longo da série.",
    ]
    if series:
        lines.extend(
            [
                "",
                "| Ano | Internações | Denominador | Taxa por 100 mil |",
                "|---|---:|---:|---:|",
            ]
        )
        for item in series:
            lines.append(
                f"| {item['periodo']} | {item['total']} | {item['denominador']} | {item['taxa']} |"
            )
    lines.extend(
        [
            "",
            (
                f"Leitura objetiva: de {first_period} ({first_total}) a {last_period} "
                f"({last_total}), a variação absoluta foi {delta_absolute} internações "
                f"({delta_percent}%). O pico foi em {peak_period}, com {peak_total} internações."
            ),
        ]
    )
    if warnings:
        lines.extend(["", f"Atenção sobre escopo dos dados: {warnings}."])
    lines.append(
        "Limite: isto descreve evolução observada nos registros, não causalidade."
    )
    return "\n".join(lines)


def _parse_age_band_distribution(value: str) -> list[dict[str, str]]:
    bands: list[dict[str, str]] = []
    for item in value.split(" | "):
        parts = item.split(":")
        if len(parts) != 5:
            continue
        faixa, total, _denominator, rate, pct = parts
        bands.append(
            {
                "faixa": faixa,
                "total": _format_int(total),
                "taxa": _format_number(rate),
                "percentual": f"{_format_number(pct)}%",
            }
        )
    return bands


def _parse_categorical_distribution(value: str) -> list[dict[str, str]]:
    groups: list[dict[str, str]] = []
    for item in value.split(" | "):
        parts = item.split(":")
        if len(parts) != 4:
            continue
        group, total, deaths, rate = parts
        groups.append(
            {
                "grupo": group,
                "total": _format_int(total),
                "mortes": _format_int(deaths),
                "taxa": _format_number(rate),
            }
        )
    return groups


def _parse_rate_distribution(value: str) -> list[dict[str, str]]:
    groups: list[dict[str, str]] = []
    for item in value.split(" | "):
        parts = item.split(":")
        if len(parts) != 5:
            continue
        group, total, denominator, rate, pct = parts
        groups.append(
            {
                "grupo": group,
                "total": _format_int(total),
                "denominador": _format_int(denominator),
                "taxa": _format_number(rate),
                "percentual": _format_number(pct),
            }
        )
    return groups


def _parse_time_series(value: str) -> list[dict[str, str]]:
    series: list[dict[str, str]] = []
    for item in value.split(" | "):
        parts = item.split(":")
        if len(parts) != 4:
            continue
        period, total, denominator, rate = parts
        series.append(
            {
                "periodo": _format_period(period),
                "total": _format_int(total),
                "denominador": _format_int(denominator),
                "taxa": _format_number(rate),
            }
        )
    return series


def _parse_top_ages(value: str) -> list[str]:
    ages: list[str] = []
    for item in value.split(" | "):
        parts = item.split(":")
        if len(parts) != 2:
            continue
        age, total = parts
        ages.append(f"{age} anos ({_format_int(total)})")
    return ages


def _humanize_denominator(value: str) -> str:
    return value.replace("internacoes", "internações").replace("raca", "raça")


def _humanize_factor(value: str) -> str:
    return (
        value.replace("raca_cor", "raça/cor")
        .replace("instrucao", "instrução")
        .replace("sexo", "sexo")
    )


def _humanize_warning(value: str) -> str:
    if not value or value == "None":
        return ""
    warning = (
        value.replace("data_quality: ", "")
        .replace("contem", "contém")
        .replace("registros", "registros")
    )
    return _format_integer_tokens(warning)


def _humanize_clinical_label(value: str) -> str:
    return (
        value.replace("diagnostico", "diagnóstico")
        .replace("Doencas", "Doenças")
        .replace("doencas", "doenças")
        .replace("respiratorio", "respiratório")
        .replace("respiratorias", "respiratórias")
    )


def _humanize_clinical_label_for_response(value: str) -> str:
    label = _humanize_clinical_label(value)
    if label.count(" | ") >= 3 or len(label) > 240:
        return "diagnóstico resolvido por consulta ao catálogo CID"
    return label


def _format_integer_tokens(value: str) -> str:
    import re

    return re.sub(
        r"\b\d{4,}\b",
        lambda match: _format_int(match.group(0)),
        value,
    )


def _format_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def _format_period(value: Any) -> str:
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "-"


def _format_number(value: Any, *, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    formatted = f"{number:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if decimals > 0:
        formatted = formatted.rstrip("0").rstrip(",")
    return formatted


def clarification_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Fallback clarification response when intent cannot be determined."""
    prompt = state.get("clarification_question") or (
        "Não consegui entender totalmente sua pergunta. "
        "Por favor, reformule adicionando contexto (tabelas, filtros, período)."
    )
    state = add_ai_message(state, prompt)
    state["final_response"] = prompt
    state["completed"] = True
    state = update_phase(state, ExecutionPhase.RESPONSE_FORMATTING, 0.0)
    return state
