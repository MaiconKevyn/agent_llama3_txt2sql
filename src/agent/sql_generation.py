"""SQL generation pipeline: schema, CoT planning, and structured output."""

import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..semantic.analytic_templates import analytic_metadata_for_plan
from ..semantic.plan_schema import SemanticPlan
from ..utils.logging_config import get_nodes_logger
from .analytic_sql import build_analytic_sql_package
from .llamaindex_context import should_use_llamaindex_sql_draft
from .llm_manager import get_llm_manager
from .plan_auditor import audit_pre_sql_plan
from .prompt_builder import build_pregeneration_hints, build_sql_generation_messages
from .state_helpers import add_ai_message, add_error, update_phase
from .state_models import ExecutionPhase, MessagesStateTXT2SQL

logger = get_nodes_logger()


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class SQLOutput(BaseModel):
    """Structured output for SQL generation."""

    sql: str = Field(description="Valid DuckDB SELECT query answering the user question")
    reasoning: str = Field(description="Brief explanation of table/filter choices (1-2 sentences)")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1; use <0.6 for uncertain queries",
    )


# ---------------------------------------------------------------------------
# CoT planning node (runs before generate_sql_node)
# ---------------------------------------------------------------------------

_COT_SYSTEM_PROMPT = """\
Você é um especialista em SQL DuckDB para dados de saúde pública do DATASUS (SIH-RS).

Analise a pergunta do usuário e produza um PLANO SQL ESTRUTURADO em até 8 linhas para guiar a geração.
Indique:
1. Tabelas e colunas principais necessárias
2. Padrão SQL obrigatório (escolha um): CTE com média global → filtro local | ROW_NUMBER OVER PARTITION BY | CASE WHEN pivot colunas | NOT EXISTS anti-join | dois períodos em CTEs separadas + delta absoluto | subquery simples
3. Filtros e condições de escopo (HAVING, WHERE com threshold, filtros de valor)
4. Uma armadilha específica a evitar para esta pergunta

Seja direto e técnico. NÃO escreva SQL — apenas o plano textual.
"""


def reasoning_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """CoT SQL planning: generate a structured SQL sketch before generation."""
    start = time.time()

    user_query = state.get("user_query", "")
    plan_type = state.get("plan_type", "single_default")
    selected_tables = state.get("selected_tables", [])

    try:
        llm_manager = get_llm_manager()
        human_prompt = (
            f"Pergunta: {user_query}\n\n"
            f"Tipo de consulta detectado: {plan_type}\n"
            f"Tabelas selecionadas: {', '.join(selected_tables) if selected_tables else 'a determinar'}\n\n"
            "Produza o plano SQL estruturado:"
        )
        response = llm_manager.invoke_chat(
            [
                SystemMessage(content=_COT_SYSTEM_PROMPT),
                HumanMessage(content=human_prompt),
            ]
        )
        reasoning_plan = response.content.strip() if hasattr(response, "content") else str(response)
        state["reasoning_plan"] = reasoning_plan
        logger.info(
            "CoT reasoning plan generated",
            extra={
                "plan_type": plan_type,
                "plan_length": len(reasoning_plan),
            },
        )
    except Exception as e:
        logger.warning(
            "reasoning_node CoT failed — continuing without plan", extra={"error": str(e)}
        )
        state["reasoning_plan"] = None

    state = update_phase(state, ExecutionPhase.SQL_GENERATION, time.time() - start)
    return state


# ---------------------------------------------------------------------------
# Main generation node
# ---------------------------------------------------------------------------


def _build_pregeneration_hints(selected_tables, user_query):
    """Backward-compatible alias."""
    return build_pregeneration_hints(selected_tables, user_query)


def _analytic_response_templates_enabled(flags: dict | None) -> bool:
    return bool((flags or {}).get("enable_analytic_response_templates", True))


def _build_deterministic_analytic_sql(semantic_plan, flags: dict | None = None) -> str | None:
    if not _analytic_response_templates_enabled(flags):
        return None
    return build_analytic_sql_package(semantic_plan)


def _sql_string_literal(value: str) -> str:
    return "'" + str(value).strip().replace("'", "''") + "'"


def _build_deterministic_diagnosis_count_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name in {"total", "total_internacoes"} for metric in plan.metrics):
        return None

    where_conditions: list[str] = []
    has_diagnosis_target = False
    for semantic_filter in plan.filters:
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if semantic_filter.field == "diagnostico_principal_codigo" and values:
            has_diagnosis_target = True
            quoted = ", ".join(_sql_string_literal(value.upper()) for value in values)
            where_conditions.append(f'"DIAG_PRINC" IN ({quoted})')
        elif semantic_filter.field == "diagnostico_principal_prefix" and values:
            has_diagnosis_target = True
            prefix_conditions = " OR ".join(
                f'"CID" LIKE {_sql_string_literal(value.upper())}'
                for value in values
            )
            where_conditions.append(
                f'"DIAG_PRINC" IN (SELECT "CID" FROM cid WHERE {prefix_conditions})'
            )
        elif semantic_filter.field == "diagnostico_principal_descricao" and values:
            has_diagnosis_target = True
            description_conditions = " OR ".join(
                f'c."DESCRICAO" ILIKE {_sql_string_literal(f"%{value}%")}'
                for value in values
            )
            where_conditions.append(
                f'"DIAG_PRINC" IN (SELECT c."CID" FROM cid c WHERE {description_conditions})'
            )
        elif semantic_filter.field == "ano" and values:
            if len(values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM "DT_INTER") = {values[0]}')
            else:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM "DT_INTER") IN ({", ".join(values)})'
                )
        elif semantic_filter.field == "sexo" and values:
            where_conditions.append(f'"SEXO" IN ({", ".join(values)})')
        elif semantic_filter.field == "diagnostico_conceito_label":
            continue
        else:
            return None

    if not has_diagnosis_target:
        return None
    where_clause = f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
    return f"SELECT COUNT(*) AS total_internacoes FROM internacoes{where_clause};"


def _build_deterministic_diagnosis_average_cost_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(
        metric.name in {"media", "custo_medio", "requested_metric"}
        and metric.expression_type in {"avg", "average"}
        for metric in plan.metrics
    ):
        return None

    diagnosis_condition = _diagnosis_join_cohort_condition(plan)
    if not diagnosis_condition:
        return None

    where_conditions = [
        *_internacoes_semantic_filter_conditions(plan),
        diagnosis_condition,
    ]
    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    return (
        "SELECT COUNT(*) AS total_internacoes,"
        ' ROUND(AVG(i."VAL_TOT"), 2) AS custo_medio'
        " FROM internacoes i"
        ' JOIN cid c ON i."DIAG_PRINC" = c."CID"'
        f" WHERE {where_clause};"
    )


def _build_deterministic_diagnosis_average_age_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(
        metric.name == "idade_media" and metric.expression_type in {"avg", "average"}
        for metric in plan.metrics
    ):
        return None

    diagnosis_condition = _diagnosis_join_cohort_condition(plan)
    if not diagnosis_condition:
        return None

    where_conditions = [
        'i."IDADE" IS NOT NULL',
        *_internacoes_semantic_filter_conditions(plan),
        diagnosis_condition,
    ]
    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    return (
        "SELECT COUNT(*) AS total_internacoes,"
        ' ROUND(AVG(i."IDADE"), 2) AS idade_media'
        " FROM internacoes i"
        ' JOIN cid c ON i."DIAG_PRINC" = c."CID"'
        f" WHERE {where_clause};"
    )


def _build_deterministic_instruction_coverage_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name == "instrucao_cobertura_mapeada" for metric in plan.metrics):
        return None

    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        elif field == "instrucao_valid":
            continue
        else:
            return None

    where_clause = (
        f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}"
        if where_conditions
        else ""
    )
    return (
        "SELECT COUNT(*) AS total_internacoes,"
        ' COUNT(ins."INSTRU") AS com_instrucao_mapeada,'
        ' ROUND(COUNT(ins."INSTRU") * 100.0 / NULLIF(COUNT(*), 0), 2) AS percentual_mapeado'
        " FROM internacoes i"
        ' LEFT JOIN instrucao ins ON i."INSTRU" = ins."INSTRU"'
        f"{where_clause};"
    )


def _build_deterministic_missing_primary_diagnosis_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name == "internacoes_sem_diag_princ" for metric in plan.metrics):
        return None

    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        else:
            return None

    where_conditions.append('(i."DIAG_PRINC" IS NULL OR TRIM(i."DIAG_PRINC") = \'\')')
    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    return (
        "SELECT COUNT(*) AS internacoes_sem_diag_princ"
        " FROM internacoes i"
        f" WHERE {where_clause};"
    )


def _build_deterministic_missing_cid_lookup_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name == "diagnosticos_sem_lookup" for metric in plan.metrics):
        return None

    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        else:
            return None

    where_conditions.extend(['i."DIAG_PRINC" IS NOT NULL', 'c."CID" IS NULL'])
    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    return (
        "SELECT COUNT(*) AS diagnosticos_sem_lookup"
        " FROM internacoes i"
        ' LEFT JOIN cid c ON i."DIAG_PRINC" = c."CID"'
        f" WHERE {where_clause};"
    )


def _build_deterministic_missing_municipio_lookup_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name == "municipios_residencia_sem_lookup" for metric in plan.metrics):
        return None

    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        elif field in {"municipio_residencia", "municipio", "cadastro_territorial"}:
            continue
        else:
            return None

    where_conditions.extend(['i."MUNIC_RES" IS NOT NULL', 'mu."CO_MUNICIPIO_6D" IS NULL'])
    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    return (
        "SELECT COUNT(*) AS municipios_residencia_sem_lookup"
        " FROM internacoes i"
        ' LEFT JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
        f" WHERE {where_clause};"
    )


def _build_deterministic_missing_race_color_death_rate_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name == "percentual_obitos_sem_raca_cor" for metric in plan.metrics):
        return None

    where_conditions: list[str] = ['i."MORTE" = true']
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        elif field in {"raca_cor", "raca_cor_identificada", "desfecho"}:
            continue
        else:
            return None

    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    missing_expr = 'SUM(CASE WHEN r."RACA_COR" IS NULL THEN 1 ELSE 0 END)'
    return (
        "SELECT COUNT(*) AS total_obitos,"
        f" {missing_expr} AS obitos_sem_raca_cor_mapeada,"
        f" ROUND({missing_expr} * 100.0 / NULLIF(COUNT(*), 0), 2) AS percentual_sem_raca_cor"
        " FROM internacoes i"
        ' LEFT JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"'
        f" WHERE {where_clause};"
    )


def _build_deterministic_invalid_discharge_dates_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name == "altas_antes_da_internacao" for metric in plan.metrics):
        return None

    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        elif field in {"data_saida", "data_entrada", "dt_saida", "dt_inter"}:
            continue
        else:
            return None

    where_conditions.append('i."DT_SAIDA" < i."DT_INTER"')
    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    return (
        "SELECT COUNT(*) AS altas_antes_da_internacao"
        " FROM internacoes i"
        f" WHERE {where_clause};"
    )


def _build_deterministic_uti_usage_count_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(metric.name in {"total", "total_internacoes"} for metric in plan.metrics):
        return None
    if not any(semantic_filter.field.lower() == "uti" for semantic_filter in plan.filters):
        return None

    where_conditions = _without_uti_value_conditions(
        _internacoes_semantic_filter_conditions(plan)
    )
    where_conditions.append('(i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0)')
    where_clause = " AND ".join(dict.fromkeys(where_conditions))
    return f"SELECT COUNT(*) AS internacoes_com_uti FROM internacoes i WHERE {where_clause};"


def _build_deterministic_uti_total_spending_sql(plan: SemanticPlan) -> str | None:
    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None
    if not any(
        metric.name == "valor_total_uti" and metric.expression_type == "sum"
        for metric in plan.metrics
    ):
        return None

    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                where_conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                where_conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        elif field in {"uti", "gasto_uti", "tipo_internacao", "val_uti"}:
            continue
        else:
            return None

    where_clause = (
        f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}"
        if where_conditions
        else ""
    )
    return (
        'SELECT ROUND(SUM(i."VAL_UTI"), 2) AS valor_uti_total'
        " FROM internacoes i"
        f"{where_clause};"
    )


def _build_deterministic_scalar_sql(semantic_plan) -> str | None:
    if not semantic_plan:
        return None
    try:
        plan = (
            semantic_plan
            if isinstance(semantic_plan, SemanticPlan)
            else SemanticPlan.model_validate(semantic_plan)
        )
    except Exception:
        return None

    if plan.base_grain != "internacao" or plan.answer_shape.row_grain != "single_scalar":
        return None

    instruction_coverage_sql = _build_deterministic_instruction_coverage_sql(plan)
    if instruction_coverage_sql:
        return instruction_coverage_sql

    missing_primary_diagnosis_sql = _build_deterministic_missing_primary_diagnosis_sql(plan)
    if missing_primary_diagnosis_sql:
        return missing_primary_diagnosis_sql

    missing_cid_lookup_sql = _build_deterministic_missing_cid_lookup_sql(plan)
    if missing_cid_lookup_sql:
        return missing_cid_lookup_sql

    missing_municipio_lookup_sql = _build_deterministic_missing_municipio_lookup_sql(plan)
    if missing_municipio_lookup_sql:
        return missing_municipio_lookup_sql

    missing_race_color_death_rate_sql = _build_deterministic_missing_race_color_death_rate_sql(plan)
    if missing_race_color_death_rate_sql:
        return missing_race_color_death_rate_sql

    invalid_discharge_dates_sql = _build_deterministic_invalid_discharge_dates_sql(plan)
    if invalid_discharge_dates_sql:
        return invalid_discharge_dates_sql

    diagnosis_count_sql = _build_deterministic_diagnosis_count_sql(plan)
    if diagnosis_count_sql:
        return diagnosis_count_sql

    diagnosis_avg_age_sql = _build_deterministic_diagnosis_average_age_sql(plan)
    if diagnosis_avg_age_sql:
        return diagnosis_avg_age_sql

    diagnosis_avg_cost_sql = _build_deterministic_diagnosis_average_cost_sql(plan)
    if diagnosis_avg_cost_sql:
        return diagnosis_avg_cost_sql

    uti_total_spending_sql = _build_deterministic_uti_total_spending_sql(plan)
    if uti_total_spending_sql:
        return uti_total_spending_sql

    uti_usage_sql = _build_deterministic_uti_usage_count_sql(plan)
    if uti_usage_sql:
        return uti_usage_sql

    if "hospital_location_differs_from_residence_uf_required" in plan.constraints and any(
        metric.name in {"total", "total_internacoes"} and metric.expression_type == "count"
        for metric in plan.metrics
    ):
        where_conditions = _internacoes_semantic_filter_conditions(plan)
        where_conditions.append('mr."SG_UF" <> mh."SG_UF"')
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            "SELECT COUNT(*) AS internacoes_fora_uf_residencia FROM internacoes i"
            ' JOIN municipios mr ON i."MUNIC_RES" = mr."CO_MUNICIPIO_6D"'
            ' JOIN hospital h ON i."CNES" = h."CNES"'
            ' JOIN municipios mh ON h."MUNIC_MOV" = mh."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause};"
        )

    race_color_code_map = {
        "branca": "1",
        "preta": "2",
        "parda": "3",
        "amarela": "4",
        "indigena": "5",
        "indígena": "5",
    }
    age_filter_conditions: list[tuple[str, int]] = []
    where_conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        if field == "raca_cor_identificada":
            where_conditions.append('"RACA_COR" IN (1, 2, 3, 4, 5)')
            continue
        if field == "raca_cor" and semantic_filter.values:
            values = [str(value).strip().lower() for value in semantic_filter.values]
            codes = [race_color_code_map.get(value, value) for value in values]
            if not codes or not all(re.fullmatch(r"[1-5]", code) for code in codes):
                return None
            where_conditions.append(f'"RACA_COR" IN ({", ".join(sorted(set(codes)))})')
            continue
        if field != "idade" or not semantic_filter.values:
            return None
        operator = semantic_filter.operator.strip()
        if operator not in {"=", "<", "<=", ">", ">="}:
            return None
        values = [str(value).strip() for value in semantic_filter.values]
        if not all(re.fullmatch(r"\d+", value) for value in values):
            return None
        numeric_values = [int(value) for value in values]
        if operator == "=":
            age_filter_conditions.append((operator, numeric_values[0]))
        elif operator in {"<", "<="}:
            age_filter_conditions.append((operator, max(numeric_values)))
        else:
            age_filter_conditions.append((operator, min(numeric_values)))

    if ("=", 0) in age_filter_conditions and any(
        operator in {"<", "<="} and value <= 1 for operator, value in age_filter_conditions
    ):
        age_filter_conditions = [("=", 0)]

    where_conditions.extend(
        f'"IDADE" {operator} {value}' for operator, value in age_filter_conditions
    )
    where_clause = f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
    metric_names = {metric.name for metric in plan.metrics}
    scalar_metric_sql = {
        "valor_servico_profissional": {
            "max": ('MAX("VAL_SP")', "maior_valor_servico_profissional"),
            "min": ('MIN("VAL_SP")', "menor_valor_servico_profissional"),
        },
        "permanencia_hospitalar": {
            "max": ('MAX("DIAS_PERM")', "maior_permanencia_hospitalar"),
            "min": ('MIN("DIAS_PERM")', "menor_permanencia_hospitalar"),
        },
        "valor_servico_hospitalar": {
            "max": ('MAX("VAL_SH")', "maior_valor_servico_hospitalar"),
            "min": ('MIN("VAL_SH")', "menor_valor_servico_hospitalar"),
        },
        "valor_internacao": {
            "max": ('MAX("VAL_TOT")', "maior_valor_internacao"),
            "min": ('MIN("VAL_TOT")', "menor_valor_internacao"),
        },
        "total_dias_permanencia": {
            "sum": ('SUM("DIAS_PERM")', "total_dias_permanencia"),
        },
        "total_servico_profissional": {
            "sum": ('SUM("VAL_SP")', "total_servico_profissional"),
        },
        "total_servico_hospitalar": {
            "sum": ('SUM("VAL_SH")', "total_servico_hospitalar"),
        },
        "valor_total_internacoes": {
            "sum": ('SUM("VAL_TOT")', "valor_total_internacoes"),
        },
        "receita_total": {
            "sum": ('SUM("VAL_TOT")', "receita_total"),
        },
    }
    for metric in plan.metrics:
        expression = scalar_metric_sql.get(metric.name, {}).get(metric.expression_type)
        if expression:
            aggregate_sql, alias = expression
            return f"SELECT {aggregate_sql} AS {alias} FROM internacoes{where_clause};"

    if "idade_minima" in metric_names:
        return f'SELECT MIN("IDADE") AS idade_minima FROM internacoes{where_clause};'
    if "idade_maxima" in metric_names:
        return f'SELECT MAX("IDADE") AS idade_maxima FROM internacoes{where_clause};'
    if (
        any(metric.name == "total" and metric.expression_type == "count" for metric in plan.metrics)
        and where_conditions
    ):
        return f"SELECT COUNT(*) AS total_internacoes FROM internacoes{where_clause};"
    return None


def _build_deterministic_grouped_sql(semantic_plan) -> str | None:
    plan = _parse_semantic_plan(semantic_plan)
    if plan is None:
        return None

    metric_names = {metric.name for metric in plan.metrics}
    dimensions = set(plan.answer_shape.required_dimensions)

    if (
        plan.base_grain == "municipio_ano"
        and dimensions == {"estado"}
        and "taxa_internacoes_populacao" in metric_names
    ):
        internacao_year_conditions: list[str] = []
        socioeconomic_year_conditions: list[str] = []
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field == "ano" and values:
                numeric_values = [
                    value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)
                ]
                if len(numeric_values) == 1:
                    internacao_year_conditions.append(
                        f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}'
                    )
                    socioeconomic_year_conditions.append(f's."NU_ANO" = {numeric_values[0]}')
                elif numeric_values:
                    joined_values = ", ".join(numeric_values)
                    internacao_year_conditions.append(
                        f'EXTRACT(YEAR FROM i."DT_INTER") IN ({joined_values})'
                    )
                    socioeconomic_year_conditions.append(f's."NU_ANO" IN ({joined_values})')
            elif field == "ano_intervalo" and len(values) >= 2:
                if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                    internacao_year_conditions.append(
                        f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                    )
                    socioeconomic_year_conditions.append(
                        f's."NU_ANO" BETWEEN {values[0]} AND {values[1]}'
                    )
            else:
                return None
        internacao_where = " AND ".join(dict.fromkeys(internacao_year_conditions))
        socioeconomic_where = " AND ".join(dict.fromkeys(socioeconomic_year_conditions))
        internacao_where_clause = f" WHERE {internacao_where}" if internacao_where else ""
        socioeconomic_where_clause = (
            f" WHERE {socioeconomic_where}" if socioeconomic_where else ""
        )
        return (
            "WITH internacoes_por_uf AS ("
            'SELECT mu."SG_UF" AS uf, COUNT(*) AS total_internacoes'
            " FROM internacoes i"
            ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
            f"{internacao_where_clause}"
            ' GROUP BY mu."SG_UF"'
            "), populacao_por_uf AS ("
            'SELECT m."SG_UF" AS uf, SUM(s."QT_POPULACAO") AS populacao'
            " FROM socioeconomico s"
            ' JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"'
            f"{socioeconomic_where_clause}"
            ' GROUP BY m."SG_UF"'
            ") SELECT i.uf, i.total_internacoes, p.populacao,"
            " ROUND(i.total_internacoes * 100000.0 / NULLIF(p.populacao, 0), 2)"
            " AS taxa_por_100k"
            " FROM internacoes_por_uf i"
            " JOIN populacao_por_uf p ON i.uf = p.uf"
            " ORDER BY taxa_por_100k DESC;"
        )

    if (
        plan.base_grain == "municipio_ano"
        and dimensions == {"estado"}
        and "populacao_total" in metric_names
    ):
        where_conditions: list[str] = ['s."QT_POPULACAO" IS NOT NULL']
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field == "ano" and values:
                numeric_values = [
                    value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)
                ]
                if len(numeric_values) == 1:
                    where_conditions.append(f's."NU_ANO" = {numeric_values[0]}')
                elif numeric_values:
                    where_conditions.append(f's."NU_ANO" IN ({", ".join(numeric_values)})')
            elif field == "ano_intervalo" and len(values) >= 2:
                if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                    where_conditions.append(f's."NU_ANO" BETWEEN {values[0]} AND {values[1]}')
            else:
                return None
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT m."SG_UF" AS uf,'
            ' SUM(s."QT_POPULACAO") AS populacao'
            " FROM socioeconomico s"
            ' JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY m."SG_UF"'
            " ORDER BY populacao DESC;"
        )

    socioeconomic_state_indicator_specs = {
        "leitos_sus_1000": 'AVG(s."VL_LEITOS_SUS_1000")',
        "medicos_1000": 'AVG(s."VL_MEDICOS_1000")',
        "leitos_sus_total": 'AVG(s."QT_LEITOS_SUS")',
        "medicos_total": 'AVG(s."QT_MEDICOS")',
    }
    socioeconomic_state_metric = next(
        (
            socioeconomic_state_indicator_specs[name]
            for name in socioeconomic_state_indicator_specs
            if name in metric_names
        ),
        None,
    )
    if (
        plan.base_grain == "municipio_ano"
        and dimensions == {"estado"}
        and socioeconomic_state_metric is not None
    ):
        expression = socioeconomic_state_metric
        where_conditions: list[str] = []
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field == "ano" and values:
                numeric_values = [
                    value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)
                ]
                if len(numeric_values) == 1:
                    where_conditions.append(f's."NU_ANO" = {numeric_values[0]}')
                elif numeric_values:
                    where_conditions.append(f's."NU_ANO" IN ({", ".join(numeric_values)})')
            elif field == "ano_intervalo" and len(values) >= 2:
                if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                    where_conditions.append(f's."NU_ANO" BETWEEN {values[0]} AND {values[1]}')
            else:
                return None
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT m."SG_UF" AS uf,'
            f" ROUND({expression}, 2) AS valor_indicador"
            " FROM socioeconomico s"
            ' JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY m."SG_UF"'
            " ORDER BY valor_indicador DESC NULLS LAST;"
        )

    if (
        plan.base_grain == "municipio_ano"
        and dimensions == {"municipio"}
        and "pib_per_capita" in metric_names
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
    ):
        where_conditions: list[str] = ['s."VL_PIB_PERCAPITA" IS NOT NULL']
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field == "ano" and values:
                numeric_values = [
                    value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)
                ]
                if len(numeric_values) == 1:
                    where_conditions.append(f's."NU_ANO" = {numeric_values[0]}')
                elif numeric_values:
                    where_conditions.append(f's."NU_ANO" IN ({", ".join(numeric_values)})')
            elif field == "ano_intervalo" and len(values) >= 2:
                if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                    where_conditions.append(f's."NU_ANO" BETWEEN {values[0]} AND {values[1]}')
            else:
                return None
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT m."NO_MUNICIPIO" AS municipio,'
            ' m."SG_UF" AS uf,'
            ' ROUND(s."VL_PIB_PERCAPITA", 2) AS pib_per_capita'
            " FROM socioeconomico s"
            ' JOIN municipios m ON s."CO_MUNICIPIO_6D" = m."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            " ORDER BY pib_per_capita DESC NULLS LAST"
            f" LIMIT {plan.answer_shape.top_n};"
        )

    if (
        dimensions == {"diagnostico"}
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
        and "total_mortes" in metric_names
    ):
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            'i."MORTE" = true',
            *_nonempty_label_conditions('c."DESCRICAO"'),
        ]
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT c."DESCRICAO" AS diagnostico,'
            " COUNT(*) AS total_obitos"
            " FROM internacoes i"
            ' JOIN cid c ON i."DIAG_PRINC" = c."CID"'
            f" WHERE {where_clause}"
            ' GROUP BY c."DESCRICAO"'
            " ORDER BY total_obitos DESC"
            f" LIMIT {plan.answer_shape.top_n};"
        )

    if (
        dimensions == {"cid_capitulo"}
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
        and (metric_names & {"total", "total_internacoes", "requested_metric"})
    ):
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            *_nonempty_label_conditions('c."DS_CAPITULO"'),
        ]
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT c."DS_CAPITULO" AS capitulo_cid,'
            " COUNT(*) AS total_internacoes"
            " FROM internacoes i"
            ' JOIN cid c ON i."DIAG_PRINC" = c."CID"'
            f" WHERE {where_clause}"
            ' GROUP BY c."DS_CAPITULO"'
            ' ORDER BY "total_internacoes" DESC'
            f" LIMIT {plan.answer_shape.top_n};"
        )

    if (
        dimensions == {"procedimento"}
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
        and (metric_names & {"total", "total_internacoes", "requested_metric"})
    ):
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            *_diagnosis_semantic_filter_conditions(plan, table_alias="i"),
            *_procedure_name_filter_conditions(plan),
            *_nonempty_label_conditions('p."NOME_PROC"'),
        ]
        joins = [
            'JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"',
            'JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"',
        ]
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip().upper()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field in {"estado", "uf"} and values:
                joins.append('JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"')
                if len(values) == 1:
                    where_conditions.append(f'mu."SG_UF" = {_sql_string_literal(values[0])}')
                else:
                    quoted = ", ".join(_sql_string_literal(value) for value in values)
                    where_conditions.append(f'mu."SG_UF" IN ({quoted})')
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT p."NOME_PROC" AS "procedimento",'
            ' COUNT(*) AS "total_procedimentos"'
            " FROM internacoes i"
            f" {' '.join(dict.fromkeys(joins))}"
            f" WHERE {where_clause}"
            ' GROUP BY p."NOME_PROC"'
            ' ORDER BY "total_procedimentos" DESC'
            f" LIMIT {plan.answer_shape.top_n};"
        )

    if (
        dimensions == {"estado"}
        and plan.answer_shape.row_grain == "one_row_per_group"
        and (metric_names & {"valor_total_internacoes", "receita_total", "requested_metric"})
    ):
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            'i."VAL_TOT" IS NOT NULL',
        ]
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT mu."SG_UF" AS "uf_residencia",'
            ' ROUND(SUM(i."VAL_TOT"), 2) AS "valor_total"'
            " FROM internacoes i"
            ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY mu."SG_UF"'
            ' ORDER BY "valor_total" DESC;'
        )

    if (
        dimensions == {"estado"}
        and plan.answer_shape.row_grain == "one_row_per_group"
        and (metric_names & {"valor_total_uti", "requested_metric"})
    ):
        where_conditions = _without_uti_value_conditions(
            _internacoes_semantic_filter_conditions(plan)
        )
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT mu."SG_UF" AS "uf_residencia",'
            ' ROUND(SUM(i."VAL_UTI"), 2) AS "valor_uti_total"'
            " FROM internacoes i"
            ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY mu."SG_UF"'
            ' ORDER BY "valor_uti_total" DESC;'
        )

    if (
        dimensions == {"especialidade"}
        and plan.answer_shape.row_grain == "one_row_per_group"
        and (metric_names & {"media_dias_permanencia", "permanencia_hospitalar", "requested_metric"})
    ):
        where_conditions = _internacoes_semantic_filter_conditions(plan)
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT e."DESCRICAO" AS especialidade,'
            ' ROUND(AVG(i."DIAS_PERM"), 2) AS permanencia_media'
            " FROM internacoes i"
            ' JOIN especialidade e ON i."ESPEC" = e."ESPEC"'
            f" WHERE {where_clause}"
            ' GROUP BY e."DESCRICAO"'
            " ORDER BY permanencia_media DESC NULLS LAST"
            " LIMIT 10;"
        )

    if (
        dimensions == {"marca_uti"}
        and plan.answer_shape.row_grain == "one_row_per_group"
        and (metric_names & {"total", "total_internacoes", "requested_metric"})
    ):
        where_conditions = _without_uti_value_conditions(
            _internacoes_semantic_filter_conditions(plan)
        )
        if _has_uti_semantic_filter(plan):
            where_conditions.append('(i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0)')
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT COALESCE(m."DESCRICAO", \'sem marca informada\') AS tipo_uti,'
            " COUNT(*) AS total_internacoes"
            " FROM internacoes i"
            ' LEFT JOIN marca_uti m ON i."MARCA_UTI" = m."MARCA_UTI"'
            f" WHERE {where_clause}"
            " GROUP BY tipo_uti"
            " ORDER BY total_internacoes DESC;"
        )

    if (
        dimensions == {"sexo"}
        and plan.answer_shape.row_grain == "one_row_per_group"
        and (metric_names & {"total", "total_internacoes", "requested_metric"})
    ):
        where_conditions = _internacoes_semantic_filter_conditions(plan)
        where_clause = (
            f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}"
            if where_conditions
            else ""
        )
        return (
            'SELECT s."DESCRICAO" AS sexo,'
            " COUNT(*) AS total_internacoes"
            " FROM internacoes i"
            ' JOIN sexo s ON i."SEXO" = s."SEXO"'
            f"{where_clause}"
            ' GROUP BY s."DESCRICAO"'
            " ORDER BY total_internacoes DESC;"
        )

    if (
        dimensions == {"raca_cor"}
        and plan.answer_shape.row_grain == "one_row_per_group"
        and "total_mortes" in metric_names
    ):
        where_conditions = ['i."MORTE" = true']
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field == "ano" and values:
                numeric_values = [
                    value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)
                ]
                if len(numeric_values) == 1:
                    where_conditions.append(
                        f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}'
                    )
                elif numeric_values:
                    where_conditions.append(
                        f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                    )
            elif field in {"raca_cor_identificada", "desfecho"}:
                continue
            else:
                return None
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        race_label = 'COALESCE(r."DESCRICAO", \'sem raca/cor mapeada\')'
        return (
            f"SELECT {race_label} AS raca_cor,"
            " COUNT(*) AS total_obitos"
            " FROM internacoes i"
            ' LEFT JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"'
            f" WHERE {where_clause}"
            f" GROUP BY {race_label}"
            " ORDER BY total_obitos DESC;"
        )

    if (
        dimensions == {"municipio"}
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
        and (metric_names & {"total", "total_internacoes", "requested_metric"})
    ):
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            *_nonempty_label_conditions('mu."NO_MUNICIPIO"'),
        ]
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip().upper()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field in {"estado", "uf"} and values:
                if len(values) == 1:
                    where_conditions.append(f'mu."SG_UF" = {_sql_string_literal(values[0])}')
                else:
                    quoted = ", ".join(_sql_string_literal(value) for value in values)
                    where_conditions.append(f'mu."SG_UF" IN ({quoted})')
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT mu."NO_MUNICIPIO" AS municipio_residencia,'
            " COUNT(*) AS total_internacoes"
            " FROM internacoes i"
            ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY mu."NO_MUNICIPIO"'
            ' ORDER BY "total_internacoes" DESC'
            f" LIMIT {plan.answer_shape.top_n};"
        )

    if (
        dimensions == {"estado"}
        and plan.answer_shape.row_grain == "one_row_per_group"
        and (metric_names & {"total", "total_internacoes", "requested_metric"})
        and _procedure_name_filter_conditions(plan)
    ):
        procedure_conditions = _procedure_name_filter_conditions(plan)
        cesarean_metric = any("CESAR" in condition.upper() for condition in procedure_conditions)
        metric_alias = (
            "total_procedimentos_cesarea" if cesarean_metric else "total_procedimentos"
        )
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            *procedure_conditions,
        ]
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT mu."SG_UF" AS "uf_residencia",'
            f' COUNT(*) AS "{metric_alias}"'
            " FROM internacoes i"
            ' JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"'
            ' JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"'
            ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY mu."SG_UF"'
            f' ORDER BY "{metric_alias}" DESC;'
        )

    if (
        dimensions == {"regiao_saude"}
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
        and (metric_names & {"total", "total_internacoes", "requested_metric"})
    ):
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            *_nonempty_label_conditions('mu."NO_REGIAO_SAUDE"'),
        ]
        for semantic_filter in plan.filters:
            field = semantic_filter.field.lower()
            values = [
                str(value).strip().upper()
                for value in semantic_filter.values
                if str(value).strip()
            ]
            if field in {"estado", "uf"} and values:
                if len(values) == 1:
                    where_conditions.append(f'mu."SG_UF" = {_sql_string_literal(values[0])}')
                else:
                    quoted = ", ".join(_sql_string_literal(value) for value in values)
                    where_conditions.append(f'mu."SG_UF" IN ({quoted})')
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT mu."NO_REGIAO_SAUDE" AS "regiao_saude",'
            ' COUNT(*) AS "total_internacoes"'
            " FROM internacoes i"
            ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY mu."NO_REGIAO_SAUDE"'
            ' ORDER BY "total_internacoes" DESC'
            f" LIMIT {plan.answer_shape.top_n};"
        )

    if (
        dimensions == {"hospital"}
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
        and "custo_por_dia" in metric_names
    ):
        where_conditions = [
            *_internacoes_semantic_filter_conditions(plan),
            'i."DIAS_PERM" > 0',
        ]
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        minimum_group_count = _minimum_group_count(plan) or 1000
        order_direction = (
            "ASC" if "cost_per_day_lowest_requested" in plan.constraints else "DESC"
        )
        return (
            'SELECT h."NO_HOSPITAL" AS hospital,'
            " COUNT(*) AS total_internacoes,"
            ' ROUND(SUM(i."VAL_TOT") / NULLIF(SUM(i."DIAS_PERM"), 0), 2)'
            " AS custo_medio_por_dia"
            " FROM internacoes i"
            ' JOIN hospital h ON i."CNES" = h."CNES"'
            f" WHERE {where_clause}"
            ' GROUP BY h."NO_HOSPITAL"'
            f" HAVING COUNT(*) >= {minimum_group_count}"
            f" ORDER BY custo_medio_por_dia {order_direction} NULLS LAST"
            f" LIMIT {plan.answer_shape.top_n};"
        )

    if "taxa_mortalidade" not in metric_names:
        return None

    if dimensions == {"estado"}:
        where_conditions = _internacoes_semantic_filter_conditions(plan)
        if _has_uti_semantic_filter(plan):
            where_conditions = _without_uti_value_conditions(where_conditions)
            where_conditions.append('(i."MARCA_UTI" IS NOT NULL OR i."UTI_INT_TO" > 0)')
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            'SELECT mu."SG_UF" AS "uf_residencia",'
            " COUNT(*) AS total_internacoes,"
            ' SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos,'
            ' ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 /'
            " NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual"
            " FROM internacoes i"
            ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
            f" WHERE {where_clause}"
            ' GROUP BY mu."SG_UF"'
            " ORDER BY taxa_mortalidade_percentual DESC;"
        )

    if dimensions == {"faixa_etaria"}:
        age_band = (
            'CASE WHEN i."IDADE" < 18 THEN \'00-17\' '
            'WHEN i."IDADE" BETWEEN 18 AND 39 THEN \'18-39\' '
            'WHEN i."IDADE" BETWEEN 40 AND 59 THEN \'40-59\' '
            'WHEN i."IDADE" BETWEEN 60 AND 79 THEN \'60-79\' '
            "ELSE '80+' END"
        )
        where_conditions = [
            'i."IDADE" IS NOT NULL',
            *_internacoes_semantic_filter_conditions(plan),
        ]
        where_clause = " AND ".join(dict.fromkeys(where_conditions))
        return (
            f"SELECT {age_band} AS faixa_etaria,"
            " COUNT(*) AS total_internacoes,"
            ' SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos,'
            ' ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 /'
            " NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual"
            " FROM internacoes i"
            f" WHERE {where_clause}"
            " GROUP BY faixa_etaria"
            " ORDER BY faixa_etaria;"
        )

    if (
        dimensions == {"hospital"}
        and plan.answer_shape.row_grain == "top_n_global"
        and plan.answer_shape.top_n
    ):
        where_conditions = _internacoes_semantic_filter_conditions(plan)
        where_clause = (
            f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}"
            if where_conditions
            else ""
        )
        minimum_group_count = _minimum_group_count(plan)
        having = (
            f" HAVING COUNT(*) >= {minimum_group_count}"
            if minimum_group_count is not None
            else ""
        )
        return (
            'SELECT h."NO_HOSPITAL" AS hospital,'
            " COUNT(*) AS total_internacoes,"
            ' SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) AS total_obitos,'
            ' ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 /'
            " NULLIF(COUNT(*), 0), 2) AS taxa_mortalidade_percentual"
            " FROM internacoes i"
            ' JOIN hospital h ON i."CNES" = h."CNES"'
            f"{where_clause}"
            ' GROUP BY h."NO_HOSPITAL"'
            f"{having}"
            " ORDER BY taxa_mortalidade_percentual DESC"
            f" LIMIT {plan.answer_shape.top_n};"
        )

    return None


def _chart_value(chart_plan, key: str, default=None):
    if not chart_plan:
        return default
    if isinstance(chart_plan, dict):
        return chart_plan.get(key, default)
    return getattr(chart_plan, key, default)


def _parse_semantic_plan(semantic_plan) -> SemanticPlan | None:
    if not semantic_plan:
        return None
    try:
        return (
            semantic_plan
            if isinstance(semantic_plan, SemanticPlan)
            else SemanticPlan.model_validate(semantic_plan)
        )
    except Exception:
        return None


def _semantic_filters(plan: SemanticPlan, field: str) -> list[str]:
    return [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field == field
        for value in semantic_filter.values
    ]


def _chart_dimensions(plan: SemanticPlan, chart_plan) -> list[str]:
    ordered: list[str] = []
    for value in [
        _chart_value(chart_plan, "x_dimension"),
        _chart_value(chart_plan, "series_dimension"),
        *list(plan.answer_shape.required_dimensions),
    ]:
        if value and value not in ordered:
            ordered.append(str(value))
    return ordered


def _latest_year_filter_sql(table: str, column: str, years: int) -> str:
    years = max(1, years)
    return (
        f'{table}."{column}" >= (SELECT MAX("{column}") FROM socioeconomico) - {years - 1}'
        if column == "NU_ANO"
        else f'EXTRACT(YEAR FROM {table}."{column}") >= '
        f'(SELECT MAX(EXTRACT(YEAR FROM "{column}")) FROM internacoes) - {years - 1}'
    )


def _recent_years(plan: SemanticPlan, chart_plan=None) -> int | None:
    values = _semantic_filters(plan, "recent_years_available")
    for value in values:
        if value.isdigit():
            return int(value)
    time_window = _chart_value(chart_plan, "time_window")
    if time_window:
        window_type = (
            time_window.get("type")
            if isinstance(time_window, dict)
            else getattr(time_window, "type", None)
        )
        window_n = time_window.get("n") if isinstance(time_window, dict) else getattr(time_window, "n", None)
        if window_type == "last_n_available_years" and window_n:
            return int(window_n)
    return None


def _minimum_group_count(plan: SemanticPlan) -> int | None:
    values = _semantic_filters(plan, "minimum_group_count")
    for value in values:
        if value.isdigit():
            return int(value)
    return None


def _socioeconomic_metric_specs() -> dict[str, tuple[str, str, str, set[str]]]:
    return {
        "mortalidade_infantil_1ano": (
            'AVG(s."VL_MORT_INFANTIL")',
            "mortalidade_infantil",
            's."VL_MORT_INFANTIL" IS NOT NULL',
            {"mortalidade_infantil_1ano", "mortalidade_infantil"},
        ),
        "pib_per_capita": (
            'AVG(s."VL_PIB_PERCAPITA")',
            "pib_per_capita",
            's."VL_PIB_PERCAPITA" IS NOT NULL',
            {"pib_per_capita"},
        ),
        "populacao_total": (
            'SUM(s."QT_POPULACAO")',
            "populacao",
            's."QT_POPULACAO" IS NOT NULL',
            {"populacao_total", "populacao"},
        ),
        "leitos_sus_total": (
            'SUM(s."QT_LEITOS_SUS")',
            "leitos_sus",
            's."QT_LEITOS_SUS" IS NOT NULL',
            {"leitos_sus_total", "leitos_sus"},
        ),
        "leitos_sus_1000": (
            'ROUND(SUM(s."QT_LEITOS_SUS") * 1000.0 / NULLIF(SUM(s."QT_POPULACAO"), 0), 4)',
            "leitos_sus_1000",
            's."QT_LEITOS_SUS" IS NOT NULL AND s."QT_POPULACAO" IS NOT NULL',
            {"leitos_sus_1000"},
        ),
        "medicos_total": (
            'SUM(s."QT_MEDICOS")',
            "medicos",
            's."QT_MEDICOS" IS NOT NULL',
            {"medicos_total", "medicos"},
        ),
        "medicos_1000": (
            'ROUND(SUM(s."QT_MEDICOS") * 1000.0 / NULLIF(SUM(s."QT_POPULACAO"), 0), 4)',
            "medicos_1000",
            's."QT_MEDICOS" IS NOT NULL AND s."QT_POPULACAO" IS NOT NULL',
            {"medicos_1000"},
        ),
    }


def _build_deterministic_chart_sql(semantic_plan, chart_plan) -> str | None:
    plan = _parse_semantic_plan(semantic_plan)
    if not plan or not _chart_value(chart_plan, "requested", False):
        return None
    dimensions = _chart_dimensions(plan, chart_plan)
    metric_names = {metric.name for metric in plan.metrics}
    y_column = str(_chart_value(chart_plan, "y_column") or "")
    chart_type = str(_chart_value(chart_plan, "chart_type") or "")

    socioeconomic_metrics = _socioeconomic_metric_specs()
    mixed_metric_sql = _build_mortality_socioeconomic_state_chart_sql(plan, chart_plan)
    if mixed_metric_sql:
        return mixed_metric_sql
    multi_metric_sql = _build_socioeconomic_multi_metric_chart_sql(plan, chart_plan)
    if multi_metric_sql:
        return multi_metric_sql
    internacoes_multi_metric_sql = _build_internacoes_multi_metric_chart_sql(plan, chart_plan)
    if internacoes_multi_metric_sql:
        return internacoes_multi_metric_sql
    internacoes_scalar_sql = _build_internacoes_scalar_chart_sql(
        plan,
        dimensions,
        y_column=y_column,
    )
    if internacoes_scalar_sql:
        return internacoes_scalar_sql
    procedure_time_series_sql = _build_procedure_time_series_chart_sql(
        plan,
        dimensions,
        y_column=y_column,
    )
    if procedure_time_series_sql:
        return procedure_time_series_sql
    for preferred in [y_column, *metric_names]:
        for expression, alias, where_condition, names in socioeconomic_metrics.values():
            if preferred in names or preferred == alias:
                return _build_socioeconomic_chart_sql(
                    plan,
                    dimensions,
                    expression=expression,
                    alias=alias,
                    where_condition=where_condition,
                    chart_type=chart_type,
                )

    if any(
        metric in metric_names
        for metric in {"total", "total_internacoes", "total_mortes", "taxa_mortalidade"}
    ) or y_column in {
        "total_internacoes",
        "total_mortes",
        "taxa_mortalidade",
        "idade_media",
        "media_dias_permanencia",
        "receita_total",
        "custo_medio",
        "valor_total_uti",
    }:
        return _build_internacoes_chart_sql(
            plan,
            dimensions,
            y_column=y_column,
            chart_type=chart_type,
            chart_plan=chart_plan,
        )
    return None


def _build_socioeconomic_multi_metric_chart_sql(plan: SemanticPlan, chart_plan) -> str | None:
    specs = _socioeconomic_metric_specs()
    metric_names = {metric.name for metric in plan.metrics}
    chart_columns = {
        str(_chart_value(chart_plan, "x_dimension") or ""),
        str(_chart_value(chart_plan, "y_column") or ""),
    }
    selected: list[tuple[str, str, str, str]] = []
    for metric_name, (expression, alias, where_condition, names) in specs.items():
        if metric_name in metric_names or alias in chart_columns or names & chart_columns:
            selected.append((metric_name, expression, alias, where_condition))
    if len(selected) < 2:
        return None

    required_dimensions = set(plan.answer_shape.required_dimensions)
    joins = ""
    limit = " LIMIT 100"
    if "ano" in required_dimensions:
        entity_select = 's."NU_ANO" AS ano'
        entity_group = 's."NU_ANO"'
        order_alias = "ano"
        direction = "ASC"
        limit = ""
    elif required_dimensions & {"estado", "SG_UF", "estado_socioeconomico"}:
        joins = ' JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"'
        entity_select = 'mu."SG_UF" AS estado'
        entity_group = 'mu."SG_UF"'
        order_alias = selected[0][2]
        direction = "DESC"
    else:
        joins = ' JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"'
        entity_select = 'mu."NO_MUNICIPIO" AS municipio'
        entity_group = 'mu."NO_MUNICIPIO"'
        order_alias = selected[0][2]
        direction = "DESC"

    metric_selects = [f"{expression} AS {alias}" for _name, expression, alias, _where in selected]
    where_conditions = list(dict.fromkeys(where for _name, _expr, _alias, where in selected))
    where_clause = " AND ".join(where_conditions)
    return (
        f"SELECT {entity_select}, "
        + ", ".join(metric_selects)
        + " FROM socioeconomico s"
        + joins
        + f" WHERE {where_clause}"
        + f" GROUP BY {entity_group}"
        + f" ORDER BY {order_alias} {direction}"
        + limit
        + ";"
    )


def _build_mortality_socioeconomic_state_chart_sql(
    plan: SemanticPlan,
    chart_plan,
) -> str | None:
    metric_names = {metric.name for metric in plan.metrics}
    if "taxa_mortalidade" not in metric_names:
        return None
    specs = {
        name: spec
        for name, spec in _socioeconomic_metric_specs().items()
        if name != "mortalidade_infantil_1ano"
    }
    socioeconomic_metric = next(
        (
            (name, spec)
            for name, spec in specs.items()
            if name in metric_names
            or spec[1] == _chart_value(chart_plan, "x_dimension")
            or spec[1] == _chart_value(chart_plan, "y_column")
        ),
        None,
    )
    if socioeconomic_metric is None:
        return None
    if not (set(plan.answer_shape.required_dimensions) & {"estado", "SG_UF", "estado_socioeconomico"}):
        return None

    _name, (expression, alias, where_condition, _names) = socioeconomic_metric
    latest_year_condition = 's."NU_ANO" = (SELECT MAX("NU_ANO") FROM socioeconomico)'
    return (
        "WITH mortality AS ("
        ' SELECT mu."SG_UF" AS estado,'
        ' ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS taxa_mortalidade'
        " FROM internacoes i"
        ' JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"'
        ' GROUP BY mu."SG_UF"'
        "), socioeconomic_metric AS ("
        f' SELECT mu."SG_UF" AS estado, {expression} AS {alias}'
        " FROM socioeconomico s"
        ' JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"'
        f" WHERE {where_condition} AND {latest_year_condition}"
        ' GROUP BY mu."SG_UF"'
        ")"
        f" SELECT mortality.estado, mortality.taxa_mortalidade, socioeconomic_metric.{alias}"
        " FROM mortality"
        " JOIN socioeconomic_metric ON mortality.estado = socioeconomic_metric.estado"
        " ORDER BY mortality.taxa_mortalidade DESC;"
    )


def _build_internacoes_multi_metric_chart_sql(plan: SemanticPlan, chart_plan) -> str | None:
    metric_specs = {
        "taxa_mortalidade": (
            'ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)',
            "taxa_mortalidade",
            "",
        ),
        "receita_total": ('ROUND(SUM(i."VAL_TOT"), 2)', "receita_total", 'i."VAL_TOT" IS NOT NULL'),
        "custo_medio": ('ROUND(AVG(i."VAL_TOT"), 2)', "custo_medio", 'i."VAL_TOT" IS NOT NULL'),
        "media_dias_permanencia": (
            'ROUND(AVG(i."DIAS_PERM"), 2)',
            "media_dias_permanencia",
            'i."DIAS_PERM" IS NOT NULL',
        ),
        "idade_media": ('ROUND(AVG(i."IDADE"), 2)', "idade_media", 'i."IDADE" IS NOT NULL'),
        "valor_total_uti": (
            'ROUND(SUM(i."VAL_UTI"), 2)',
            "valor_total_uti",
            'i."VAL_UTI" IS NOT NULL AND i."VAL_UTI" > 0',
        ),
        "total_mortes": (
            'SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END)',
            "total_mortes",
            "",
        ),
        "total_internacoes": ("COUNT(*)", "total_internacoes", ""),
    }
    requested_metrics = [
        str(_chart_value(chart_plan, "x_dimension") or ""),
        str(_chart_value(chart_plan, "y_column") or ""),
    ]
    selected: list[tuple[str, str, str]] = []
    for metric in requested_metrics:
        selected_aliases = {alias for _expression, alias, _where in selected}
        if metric in metric_specs and metric not in selected_aliases:
            selected.append(metric_specs[metric])
    if len(selected) < 2:
        return None

    required_dimensions = [
        dimension
        for dimension in plan.answer_shape.required_dimensions
        if dimension not in metric_specs
    ]
    joins: list[str] = []
    where_conditions: list[str] = []
    if "estado" in required_dimensions or "SG_UF" in required_dimensions:
        joins.append('JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"')
        entity_select = 'mu."SG_UF" AS estado'
        entity_group = 'mu."SG_UF"'
    elif "municipio" in required_dimensions:
        joins.append('JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"')
        entity_select = 'mu."NO_MUNICIPIO" AS municipio'
        entity_group = 'mu."NO_MUNICIPIO"'
        where_conditions.append('mu."NO_MUNICIPIO" IS NOT NULL')
    elif "ano" in required_dimensions:
        entity_select = 'EXTRACT(YEAR FROM i."DT_INTER") AS ano'
        entity_group = 'EXTRACT(YEAR FROM i."DT_INTER")'
        where_conditions.append('i."DT_INTER" IS NOT NULL')
    else:
        return None

    for _expression, _alias, where_condition in selected:
        if where_condition:
            where_conditions.append(where_condition)

    metric_selects = [f"{expression} AS {alias}" for expression, alias, _where in selected]
    where_clause = (
        f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}" if where_conditions else ""
    )
    order_alias = selected[-1][1]
    is_temporal = " AS ano" in entity_select
    return (
        f"SELECT {entity_select}, "
        + ", ".join(metric_selects)
        + " FROM internacoes i "
        + " ".join(dict.fromkeys(joins))
        + where_clause
        + f" GROUP BY {entity_group}"
        + f" ORDER BY {order_alias} {'ASC' if is_temporal else 'DESC'}"
        + ("" if is_temporal else " LIMIT 100")
        + ";"
    )


def _build_internacoes_scalar_chart_sql(
    plan: SemanticPlan,
    dimensions: list[str],
    *,
    y_column: str,
) -> str | None:
    if plan.answer_shape.required_dimensions or dimensions:
        return None
    metric_names = {metric.name for metric in plan.metrics}
    metric_expression, metric_alias = _internacoes_metric_expression(y_column, metric_names)
    if not metric_expression:
        return None
    where_conditions = _internacoes_semantic_filter_conditions(plan)
    where_conditions.extend(_internacoes_metric_filter_conditions(metric_alias))
    where_clause = f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}" if where_conditions else ""
    return f"SELECT {metric_expression} AS {metric_alias} FROM internacoes i{where_clause};"


def _build_procedure_time_series_chart_sql(
    plan: SemanticPlan,
    dimensions: list[str],
    *,
    y_column: str,
) -> str | None:
    if not {"ano", "procedimento"}.issubset(set(dimensions)):
        return None
    metric_names = {metric.name for metric in plan.metrics}
    metric_expression, metric_alias = _internacoes_metric_expression(y_column, metric_names)
    if metric_alias not in {"total_internacoes", "total_mortes", "taxa_mortalidade"}:
        return None

    base_conditions = [
        'i."DT_INTER" IS NOT NULL',
        *_internacoes_semantic_filter_conditions(plan),
        *_internacoes_metric_filter_conditions(metric_alias),
        *_nonempty_label_conditions('p."NOME_PROC"'),
    ]
    where_clause = " AND ".join(dict.fromkeys(base_conditions))
    top_n = plan.answer_shape.top_n or 10
    return (
        "WITH top_procedimentos AS ("
        ' SELECT p."NOME_PROC" AS procedimento, COUNT(*) AS total_geral'
        " FROM internacoes i"
        ' JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"'
        ' JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"'
        f" WHERE {where_clause}"
        ' GROUP BY p."NOME_PROC"'
        ' ORDER BY total_geral DESC'
        f" LIMIT {top_n}"
        ")"
        ' SELECT EXTRACT(YEAR FROM i."DT_INTER") AS ano,'
        ' p."NOME_PROC" AS procedimento,'
        f" {metric_expression} AS {metric_alias}"
        " FROM internacoes i"
        ' JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"'
        ' JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"'
        ' JOIN top_procedimentos tp ON p."NOME_PROC" = tp.procedimento'
        f" WHERE {where_clause}"
        ' GROUP BY EXTRACT(YEAR FROM i."DT_INTER"), p."NOME_PROC"'
        " ORDER BY ano ASC, MAX(tp.total_geral) DESC;"
    )


def _build_socioeconomic_chart_sql(
    plan: SemanticPlan,
    dimensions: list[str],
    *,
    expression: str,
    alias: str,
    where_condition: str,
    chart_type: str,
) -> str | None:
    selected_dimensions: list[tuple[str, str]] = []
    joins = ""
    if "ano" in dimensions:
        selected_dimensions.append(('s."NU_ANO"', "ano"))
    if any(dimension in dimensions for dimension in ["estado", "uf"]):
        joins = ' JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"'
        selected_dimensions.append(('mu."SG_UF"', "estado"))
    elif "municipio" in dimensions:
        joins = ' JOIN municipios mu ON s."CO_MUNICIPIO_6D" = mu."CO_MUNICIPIO_6D"'
        selected_dimensions.append(('mu."NO_MUNICIPIO"', "municipio"))
    if not selected_dimensions:
        selected_dimensions.append(('s."NU_ANO"', "ano"))

    where_conditions = [where_condition]
    recent_years = _recent_years(plan)
    if recent_years is not None:
        where_conditions.append(_latest_year_filter_sql("s", "NU_ANO", recent_years))
    where_clause = " AND ".join(where_conditions)
    select_dims = ", ".join(f"{expr} AS {alias_name}" for expr, alias_name in selected_dimensions)
    group_by = ", ".join(expr for expr, _alias in selected_dimensions)
    order_by = "ano" if selected_dimensions[0][1] == "ano" else alias
    direction = "ASC" if order_by == "ano" else "DESC"
    limit = ""
    if chart_type in {"bar", "pie", "donut"} and selected_dimensions[0][1] in {"municipio"}:
        limit = f" LIMIT {plan.answer_shape.top_n or 10}"
    return (
        f"SELECT {select_dims}, {expression} AS {alias}"
        " FROM socioeconomico s"
        f"{joins}"
        f" WHERE {where_clause}"
        f" GROUP BY {group_by}"
        f" ORDER BY {order_by} {direction}"
        f"{limit};"
    )


def _build_internacoes_chart_sql(
    plan: SemanticPlan,
    dimensions: list[str],
    *,
    y_column: str,
    chart_type: str,
    chart_plan=None,
) -> str | None:
    metric_names = {metric.name for metric in plan.metrics}
    selected_dimensions: list[tuple[str, str]] = []
    joins: list[str] = []
    where_conditions: list[str] = []
    age_band_expression = (
        'CASE WHEN i."IDADE" < 1 THEN \'Menor de 1 ano\' '
        'WHEN i."IDADE" BETWEEN 1 AND 4 THEN \'1 a 4 anos\' '
        'WHEN i."IDADE" BETWEEN 5 AND 14 THEN \'5 a 14 anos\' '
        'WHEN i."IDADE" BETWEEN 15 AND 29 THEN \'15 a 29 anos\' '
        'WHEN i."IDADE" BETWEEN 30 AND 59 THEN \'30 a 59 anos\' '
        'WHEN i."IDADE" >= 60 THEN \'60 anos ou mais\' ELSE \'Nao informado\' END'
    )

    def add_dimension(expression: str, alias: str) -> None:
        if alias not in {existing_alias for _expr, existing_alias in selected_dimensions}:
            selected_dimensions.append((expression, alias))

    if "ano" in dimensions:
        add_dimension('EXTRACT(YEAR FROM i."DT_INTER")', "ano")
        where_conditions.append('i."DT_INTER" IS NOT NULL')
    if "mes" in dimensions:
        add_dimension('EXTRACT(MONTH FROM i."DT_INTER")', "mes")
        where_conditions.append('i."DT_INTER" IS NOT NULL')
    if any(dimension in dimensions for dimension in ["estado", "uf"]):
        joins.append('JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"')
        add_dimension('mu."SG_UF"', "estado")
    if "regiao_saude" in dimensions:
        joins.append('JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"')
        add_dimension('mu."NO_REGIAO_SAUDE"', "regiao_saude")
        where_conditions.append('mu."NO_REGIAO_SAUDE" IS NOT NULL')
    if "municipio" in dimensions:
        joins.append('JOIN municipios mu ON i."MUNIC_RES" = mu."CO_MUNICIPIO_6D"')
        add_dimension('mu."NO_MUNICIPIO"', "municipio")
        where_conditions.append('mu."NO_MUNICIPIO" IS NOT NULL')
    if "especialidade" in dimensions:
        joins.append('JOIN especialidade e ON i."ESPEC" = e."ESPEC"')
        add_dimension('e."DESCRICAO"', "especialidade")
    if "procedimento" in dimensions:
        joins.append('JOIN internacao_procedimento ip ON i."N_AIH" = ip."N_AIH"')
        joins.append('JOIN procedimentos p ON ip."PROC_REA" = p."PROC_REA"')
        add_dimension('p."NOME_PROC"', "procedimento")
        where_conditions.extend(_nonempty_label_conditions('p."NOME_PROC"'))
    if "hospital" in dimensions:
        add_dimension('i."CNES"', "hospital")
        where_conditions.append('i."CNES" IS NOT NULL')
    if "sexo" in dimensions:
        add_dimension(
            'CASE WHEN i."SEXO" = 1 THEN \'Masculino\' WHEN i."SEXO" = 3 THEN \'Feminino\' ELSE \'Ignorado\' END',
            "sexo",
        )
        where_conditions.append('i."SEXO" IN (1, 3)')
    if "raca_cor" in dimensions:
        joins.append('JOIN raca_cor r ON i."RACA_COR" = r."RACA_COR"')
        add_dimension('r."DESCRICAO"', "raca_cor")
        where_conditions.append('i."RACA_COR" IN (1, 2, 3, 4, 5)')
    if "faixa_etaria" in dimensions:
        add_dimension(age_band_expression, "faixa_etaria")
        where_conditions.append('i."IDADE" IS NOT NULL')
    elif "idade" in dimensions:
        add_dimension('i."IDADE"', "idade")
        where_conditions.append('i."IDADE" IS NOT NULL')
    if "nacionalidade" in dimensions:
        joins.append('LEFT JOIN nacionalidade n ON i."NACIONAL" = n."NACIONAL"')
        add_dimension('COALESCE(n."DESCRICAO", \'Nao informado\')', "nacionalidade")
    if "causa_morte" in dimensions:
        joins.append('JOIN cid c ON i."DIAG_PRINC" = c."CID"')
        add_dimension('c."DESCRICAO"', "causa_morte")
        where_conditions.extend(_nonempty_label_conditions('c."DESCRICAO"'))
    elif "cid_capitulo" in dimensions:
        joins.append('JOIN cid c ON i."DIAG_PRINC" = c."CID"')
        add_dimension('c."DS_CAPITULO"', "cid_capitulo")
        where_conditions.extend(_nonempty_label_conditions('c."DS_CAPITULO"'))
    elif "diagnostico" in dimensions:
        joins.append('JOIN cid c ON i."DIAG_PRINC" = c."CID"')
        add_dimension('c."DESCRICAO"', "diagnostico")
        where_conditions.extend(_nonempty_label_conditions('c."DESCRICAO"'))

    where_conditions.extend(_internacoes_semantic_filter_conditions(plan))

    recent_years = _recent_years(plan, chart_plan)
    if recent_years is not None:
        where_conditions.append(_latest_year_filter_sql("i", "DT_INTER", recent_years))

    metric_expression, metric_alias = _internacoes_metric_expression(y_column, metric_names)
    if not metric_expression:
        return None
    if metric_alias == "total_mortes":
        where_conditions.append('i."MORTE" = true')
    elif metric_alias == "valor_total_uti":
        where_conditions.append('i."VAL_UTI" IS NOT NULL AND i."VAL_UTI" > 0')
    elif metric_alias in {"receita_total", "custo_medio"}:
        where_conditions.append('i."VAL_TOT" IS NOT NULL')
    elif metric_alias == "media_dias_permanencia":
        where_conditions.append('i."DIAS_PERM" IS NOT NULL')
    elif metric_alias == "idade_media":
        where_conditions.append('i."IDADE" IS NOT NULL')

    if not selected_dimensions:
        if metric_alias in {"total_mortes", "taxa_mortalidade"}:
            add_dimension('EXTRACT(YEAR FROM i."DT_INTER")', "ano")
            where_conditions.append('i."DT_INTER" IS NOT NULL')
        else:
            return None

    deduped_joins = list(dict.fromkeys(joins))
    select_dims = ", ".join(f"{expr} AS {alias}" for expr, alias in selected_dimensions)
    group_by = ", ".join(expr for expr, _alias in selected_dimensions)
    where_clause = f" WHERE {' AND '.join(dict.fromkeys(where_conditions))}" if where_conditions else ""
    having = ""
    minimum_group_count = _minimum_group_count(plan)
    if minimum_group_count:
        having = f" HAVING COUNT(*) > {minimum_group_count}"
    order_alias = selected_dimensions[0][1] if selected_dimensions[0][1] == "ano" else metric_alias
    direction = "ASC" if order_alias == "ano" or "lowest_rank_requested" in plan.constraints else "DESC"
    limit = ""
    dimension_aliases = {alias for _expr, alias in selected_dimensions}
    high_cardinality = {
        "municipio",
        "diagnostico",
        "causa_morte",
        "cid_capitulo",
        "nacionalidade",
        "procedimento",
        "hospital",
    } & dimension_aliases
    has_non_temporal_dimension = bool(dimension_aliases - {"ano", "mes"})
    if plan.answer_shape.top_n_scope == "global" and has_non_temporal_dimension:
        limit = f" LIMIT {plan.answer_shape.top_n or 10}"
    elif chart_type in {"bar", "pie", "donut"} and high_cardinality:
        limit = f" LIMIT {plan.answer_shape.top_n or 10}"
    return (
        f"SELECT {select_dims}, {metric_expression} AS {metric_alias}"
        " FROM internacoes i "
        + " ".join(deduped_joins)
        + where_clause
        + f" GROUP BY {group_by}"
        + having
        + f" ORDER BY {order_alias} {direction}"
        + limit
        + ";"
    )


def _internacoes_semantic_filter_conditions(plan: SemanticPlan) -> list[str]:
    conditions: list[str] = []
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if field == "obstetrico":
            conditions.append('i."ESPEC" = 2')
        elif field == "uti":
            conditions.append('i."VAL_UTI" IS NOT NULL AND i."VAL_UTI" > 0')
        elif field == "sexo" and values:
            numeric_values = [value for value in values if re.fullmatch(r"\d+", value)]
            if numeric_values:
                conditions.append(f'i."SEXO" IN ({", ".join(numeric_values)})')
        elif field == "ano" and values:
            numeric_values = [value for value in values if re.fullmatch(r"(?:19|20)\d{2}", value)]
            if len(numeric_values) == 1:
                conditions.append(f'EXTRACT(YEAR FROM i."DT_INTER") = {numeric_values[0]}')
            elif numeric_values:
                conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") IN ({", ".join(numeric_values)})'
                )
        elif field == "ano_intervalo" and len(values) >= 2:
            if all(re.fullmatch(r"(?:19|20)\d{2}", value) for value in values[:2]):
                conditions.append(
                    f'EXTRACT(YEAR FROM i."DT_INTER") BETWEEN {values[0]} AND {values[1]}'
                )
        elif field == "idade" and values:
            numeric_values = [value for value in values if re.fullmatch(r"\d+", value)]
            if numeric_values:
                operator = (
                    semantic_filter.operator
                    if semantic_filter.operator in {"=", "<", "<=", ">", ">="}
                    else "="
                )
                conditions.append(f'i."IDADE" {operator} {numeric_values[0]}')
        elif field == "diagnostico_principal_prefix" and values:
            prefix_conditions = " OR ".join(
                f'i."DIAG_PRINC" LIKE {_sql_string_literal(value.upper())}'
                for value in values
            )
            conditions.append(f"({prefix_conditions})")
        elif field == "diagnostico_principal_codigo" and values:
            quoted = ", ".join(_sql_string_literal(value.upper()) for value in values)
            conditions.append(f'i."DIAG_PRINC" IN ({quoted})')
        elif field == "diagnostico_principal_descricao" and values:
            description_conditions = " OR ".join(
                f'c."DESCRICAO" ILIKE {_sql_string_literal(f"%{value}%")}'
                for value in values
            )
            conditions.append(
                f'i."DIAG_PRINC" IN (SELECT c."CID" FROM cid c WHERE {description_conditions})'
            )
        elif field == "desfecho" and any("morte" in value.lower() for value in values):
            conditions.append('i."MORTE" = true')
    return conditions


def _without_uti_value_conditions(conditions: list[str]) -> list[str]:
    return [condition for condition in conditions if '"VAL_UTI"' not in condition]


def _has_uti_semantic_filter(plan: SemanticPlan) -> bool:
    return any(semantic_filter.field.lower() == "uti" for semantic_filter in plan.filters)


def _procedure_name_filter_conditions(plan: SemanticPlan) -> list[str]:
    conditions: list[str] = []
    for semantic_filter in plan.filters:
        if semantic_filter.field.lower() != "procedimento_nome":
            continue
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if not values:
            continue
        if semantic_filter.operator.upper() in {"ILIKE", "LIKE"}:
            conditions.extend(
                f'p."NOME_PROC" ILIKE {_sql_string_literal(f"%{value}%")}'
                for value in values
            )
        elif semantic_filter.operator.upper() in {"=", "IN"}:
            quoted = ", ".join(_sql_string_literal(value.upper()) for value in values)
            conditions.append(f'UPPER(p."NOME_PROC") IN ({quoted})')
    return conditions


def _diagnosis_semantic_filter_conditions(
    plan: SemanticPlan, *, table_alias: str = "i"
) -> list[str]:
    conditions: list[str] = []
    diagnosis_column = f'{table_alias}."DIAG_PRINC"'
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if not values:
            continue
        if field == "diagnostico_principal_codigo":
            quoted = ", ".join(_sql_string_literal(value.upper()) for value in values)
            conditions.append(f"{diagnosis_column} IN ({quoted})")
        elif field == "diagnostico_principal_prefix":
            prefix_conditions = " OR ".join(
                f"{diagnosis_column} LIKE {_sql_string_literal(value.upper())}"
                for value in values
            )
            conditions.append(f"({prefix_conditions})")
        elif field == "diagnostico_principal_descricao":
            description_conditions = " OR ".join(
                f'c."DESCRICAO" ILIKE {_sql_string_literal(f"%{value}%")}'
                for value in values
            )
            conditions.append(
                f'{diagnosis_column} IN (SELECT c."CID" FROM cid c WHERE {description_conditions})'
            )
    return conditions


def _diagnosis_join_cohort_condition(plan: SemanticPlan) -> str | None:
    predicates: list[str] = []
    has_prefix_filter = any(
        semantic_filter.field.lower() == "diagnostico_principal_prefix"
        and any(str(value).strip() for value in semantic_filter.values)
        for semantic_filter in plan.filters
    )
    for semantic_filter in plan.filters:
        field = semantic_filter.field.lower()
        values = [str(value).strip() for value in semantic_filter.values if str(value).strip()]
        if not values:
            continue
        if field == "diagnostico_principal_codigo":
            quoted = ", ".join(_sql_string_literal(value.upper()) for value in values)
            predicates.append(f'c."CID" IN ({quoted})')
        elif field == "diagnostico_principal_prefix":
            predicates.extend(
                f'c."CID" LIKE {_sql_string_literal(value.upper())}' for value in values
            )
        elif field == "diagnostico_principal_descricao" or (
            field == "diagnostico_conceito_termo_expandido" and not has_prefix_filter
        ):
            predicates.extend(
                f'c."DESCRICAO" ILIKE {_sql_string_literal(f"%{value}%")}'
                for value in values
                if "cid " not in value.lower()
            )
    if not predicates:
        return None
    return "(" + " OR ".join(dict.fromkeys(predicates)) + ")"


def _internacoes_metric_filter_conditions(metric_alias: str) -> list[str]:
    if metric_alias == "total_mortes":
        return ['i."MORTE" = true']
    if metric_alias == "valor_total_uti":
        return ['i."VAL_UTI" IS NOT NULL AND i."VAL_UTI" > 0']
    if metric_alias in {"receita_total", "custo_medio"}:
        return ['i."VAL_TOT" IS NOT NULL']
    if metric_alias == "media_dias_permanencia":
        return ['i."DIAS_PERM" IS NOT NULL']
    if metric_alias == "idade_media":
        return ['i."IDADE" IS NOT NULL']
    return []


def _nonempty_label_conditions(column: str) -> list[str]:
    return [
        f"{column} IS NOT NULL",
        f"TRIM({column}) <> ''",
        f"{column} NOT IN ('Nao preenchido', 'Nao informado')",
    ]


def _internacoes_metric_expression(y_column: str, metric_names: set[str]) -> tuple[str | None, str]:
    if y_column == "valor_total_uti":
        return ('ROUND(SUM(i."VAL_UTI"), 2)', "valor_total_uti")
    if y_column == "receita_total" or "receita_total" in metric_names:
        return ('ROUND(SUM(i."VAL_TOT"), 2)', "receita_total")
    if y_column == "media_dias_permanencia":
        return ('ROUND(AVG(i."DIAS_PERM"), 2)', "media_dias_permanencia")
    if y_column == "idade_media":
        return ('ROUND(AVG(i."IDADE"), 2)', "idade_media")
    if y_column == "custo_medio" or "media" in metric_names:
        return ('ROUND(AVG(i."VAL_TOT"), 2)', "custo_medio")
    if y_column == "taxa_mortalidade" or "taxa_mortalidade" in metric_names:
        return (
            'ROUND(SUM(CASE WHEN i."MORTE" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)',
            "taxa_mortalidade",
        )
    if y_column == "total_mortes" or "total_mortes" in metric_names:
        return ("COUNT(*)", "total_mortes")
    if y_column == "total_internacoes" or {"total", "total_internacoes"} & metric_names:
        return ("COUNT(*)", "total_internacoes")
    return None, y_column or "valor"


def generate_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Generate SQL using ChatPromptTemplate with table-specific rules."""
    start_time = time.time()

    logger.info("SQL generation node started", extra={"user_query": state["user_query"][:100]})

    try:
        user_query = state["user_query"]
        schema_context = state.get("schema_context", "")
        selected_tables = state.get("selected_tables", [])
        semantic_plan = state.get("semantic_plan")
        chart_plan = state.get("chart_plan")
        ablation_flags = state.get("ablation_flags") or {}

        plan_audit = audit_pre_sql_plan(
            user_query=user_query,
            semantic_plan=semantic_plan,
            chart_plan=chart_plan,
        )
        state["plan_audit"] = plan_audit
        if plan_audit["passed"]:
            state["structured_error"] = None
        else:
            state["structured_error"] = {
                "layer": "plan_audit",
                "code": "pre_sql_plan_audit_failed",
                "errors": plan_audit["errors"],
            }

        chart_requested = bool(_chart_value(chart_plan, "requested", False))
        chart_expected_shape = str(_chart_value(chart_plan, "expected_result_shape") or "")
        chart_requires_tabular_result = chart_requested and chart_expected_shape in {
            "time_metric",
            "time_series_metric",
            "category_metric",
            "wide_metric_comparison",
        }

        deterministic_sql = _build_deterministic_chart_sql(semantic_plan, chart_plan)
        if deterministic_sql:
            state["generated_sql"] = deterministic_sql
            state["current_error"] = None
            state = add_ai_message(
                state,
                f"Generated SQL query (deterministic_chart): {deterministic_sql}",
            )
            meta = state.get("response_metadata", {}) or {}
            meta["sql_generation_confidence"] = 1.0
            meta["sql_generation_reasoning"] = (
                "Deterministic chart SQL generated from the semantic and chart plans."
            )
            state["response_metadata"] = meta
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)
            logger.info(
                "SQL generated via deterministic chart macro",
                extra={"sql": deterministic_sql[:200], "execution_time": execution_time},
            )
            return state

        if chart_requires_tabular_result:
            state["structured_error"] = {
                "layer": "sql_generation",
                "code": "chart_sql_compiler_required",
                "message": "Chart requests with tabular shape must use chart-compatible SQL.",
            }
        else:
            deterministic_sql = _build_deterministic_analytic_sql(semantic_plan, ablation_flags)
            if deterministic_sql:
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    f"Generated SQL query (deterministic_analytic): {deterministic_sql}",
                )
                meta = state.get("response_metadata", {}) or {}
                meta["sql_generation_confidence"] = 1.0
                meta["sql_generation_reasoning"] = (
                    "Deterministic analytic SQL generated from the semantic plan."
                )
                meta.update(analytic_metadata_for_plan(semantic_plan))
                state["response_metadata"] = meta
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)
                logger.info(
                    "SQL generated via deterministic analytic macro",
                    extra={"sql": deterministic_sql[:200], "execution_time": execution_time},
                )
                return state

            deterministic_sql = _build_deterministic_scalar_sql(semantic_plan)
            if deterministic_sql:
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    f"Generated SQL query (deterministic_scalar): {deterministic_sql}",
                )
                meta = state.get("response_metadata", {}) or {}
                meta["sql_generation_confidence"] = 1.0
                meta["sql_generation_reasoning"] = (
                    "Deterministic scalar SQL generated from the semantic plan."
                )
                state["response_metadata"] = meta
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)
                logger.info(
                    "SQL generated via deterministic scalar macro",
                    extra={"sql": deterministic_sql[:200], "execution_time": execution_time},
                )
                return state

            deterministic_sql = _build_deterministic_grouped_sql(semantic_plan)
            if deterministic_sql:
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    f"Generated SQL query (deterministic_grouped): {deterministic_sql}",
                )
                meta = state.get("response_metadata", {}) or {}
                meta["sql_generation_confidence"] = 1.0
                meta["sql_generation_reasoning"] = (
                    "Deterministic grouped SQL generated from the semantic plan."
                )
                state["response_metadata"] = meta
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)
                logger.info(
                    "SQL generated via deterministic grouped macro",
                    extra={"sql": deterministic_sql[:200], "execution_time": execution_time},
                )
                return state

        llm_manager = get_llm_manager()

        reasoning_plan = state.get("reasoning_plan")
        if reasoning_plan:
            user_query = (
                f"{user_query}\n\n"
                f"[PLANO DE RACIOCÍNIO PRÉ-GERADO]\n"
                f"{reasoning_plan}\n"
                f"Siga este plano ao gerar o SQL."
            )
        if semantic_plan:
            try:
                from ..semantic.catalog import render_catalog_context_for_plan
                from ..semantic.plan_schema import SemanticPlan

                parsed_plan = SemanticPlan.model_validate(semantic_plan)
                semantic_prompt = parsed_plan.to_prompt_block()
                catalog_prompt = render_catalog_context_for_plan(parsed_plan)
                if catalog_prompt.strip() != "[SEMANTIC CATALOG CONTEXT]":
                    semantic_prompt = f"{semantic_prompt}\n\n{catalog_prompt}"
            except Exception:
                semantic_prompt = f"[SEMANTIC PLAN - SQL MUST SATISFY]\n{semantic_plan}"
            user_query = (
                f"{user_query}\n\n"
                f"{semantic_prompt}\n"
                "Antes de escrever a SQL, preserve métricas, dimensões, filtros, granularidade e shape desse plano."
            )
        if chart_plan:
            try:
                from ..visualization.schema import ChartPlan

                parsed_chart_plan = ChartPlan.model_validate(chart_plan)
                chart_prompt = parsed_chart_plan.to_prompt_block()
            except Exception:
                chart_prompt = (
                    f"[CHART PLAN - SQL RESULT MUST SUPPORT THIS VISUALIZATION]\n{chart_plan}"
                )
            user_query = (
                f"{user_query}\n\n"
                f"{chart_prompt}\n"
                "Quando houver ChartPlan requested=true, a SQL deve retornar colunas compatíveis com required_columns. "
                "Prefira formato tidy/long para series_dimension: uma linha por x_dimension e series_dimension, "
                "com a métrica em y_column. Não gere colunas extras que sejam códigos de domínio se elas não forem necessárias ao gráfico."
            )

        logger.info("Tables selected for SQL generation", extra={"tables": selected_tables})

        formatted_messages, pregeneration_hints = build_sql_generation_messages(
            user_query=user_query,
            schema_context=schema_context,
            selected_tables=selected_tables,
            ablation_flags=ablation_flags,
        )

        logger.debug(
            "Template prepared",
            extra={
                "message_count": len(formatted_messages),
                "has_pregeneration_hints": bool(pregeneration_hints),
            },
        )

        sql_query: str | None = None
        generation_method = "structured"
        if should_use_llamaindex_sql_draft(ablation_flags):
            try:
                from .llamaindex_sql_generator import generate_llamaindex_sql_draft

                draft = generate_llamaindex_sql_draft(
                    user_query=user_query,
                    schema_context=schema_context,
                    selected_tables=selected_tables,
                    semantic_plan=semantic_plan if isinstance(semantic_plan, dict) else None,
                    chart_plan=chart_plan if isinstance(chart_plan, dict) else None,
                    model=llm_manager.config.llm_model,
                    temperature=llm_manager.config.llm_temperature,
                )
                sql_query = llm_manager._clean_sql_query(draft.sql)
                if sql_query:
                    generation_method = draft.source
                    meta = state.get("response_metadata", {}) or {}
                    meta["sql_generation_source"] = draft.source
                    meta["sql_generation_confidence"] = draft.confidence
                    meta["sql_generation_reasoning"] = draft.reasoning
                    state["response_metadata"] = meta
                    logger.info(
                        "SQL generated via LlamaIndex draft",
                        extra={
                            "sql": sql_query[:200],
                            "confidence": draft.confidence,
                        },
                    )
            except Exception as llama_err:
                meta = state.get("response_metadata", {}) or {}
                meta["llamaindex_sql_draft_error"] = str(llama_err)
                state["response_metadata"] = meta
                logger.warning(
                    "LlamaIndex SQL draft failed, falling back to current generator",
                    extra={"error": str(llama_err)},
                )

        if not sql_query:
            try:
                structured_result = llm_manager.invoke_chat_structured(
                    formatted_messages, SQLOutput
                )
                sql_query = llm_manager._clean_sql_query(structured_result.sql)
                logger.info(
                    "SQL generated via structured output",
                    extra={
                        "sql": sql_query[:200],
                        "reasoning": structured_result.reasoning[:120],
                        "confidence": structured_result.confidence,
                    },
                )
                meta = state.get("response_metadata", {}) or {}
                meta["sql_generation_confidence"] = structured_result.confidence
                meta["sql_generation_reasoning"] = structured_result.reasoning
                meta["sql_generation_source"] = "current_structured_output"
                state["response_metadata"] = meta
            except Exception as struct_err:
                logger.warning(
                    "Structured output failed, falling back to text parse",
                    extra={"error": str(struct_err)},
                )
                generation_method = "text_fallback"
                response = llm_manager.invoke_chat(formatted_messages)
                sql_query = (
                    response.content.strip() if hasattr(response, "content") else str(response)
                )
                sql_query = llm_manager._clean_sql_query(sql_query)

        if sql_query:
            state["generated_sql"] = sql_query
            state["current_error"] = None
            state = add_ai_message(state, f"Generated SQL query ({generation_method}): {sql_query}")
            logger.info(
                "SQL generated successfully",
                extra={
                    "sql": sql_query[:200],
                    "method": generation_method,
                },
            )

        else:
            logger.warning(
                "SQL generation: empty response on first attempt, trying simplified prompt"
            )
            try:
                simplified_messages = [
                    SystemMessage(
                        content=(
                            "You are a DuckDB SQL expert. Generate ONLY a valid SQL SELECT query "
                            "for the Brazilian healthcare database sihrd5. "
                            "Return ONLY the SQL, no explanation.\n\n"
                            f"DATABASE SCHEMA:\n{schema_context}"
                        )
                    ),
                    HumanMessage(content=f"USER QUERY: {user_query}\n\nGenerate the SQL query:"),
                ]
                retry_response = llm_manager.invoke_chat(simplified_messages)
                retry_sql = (
                    retry_response.content.strip()
                    if hasattr(retry_response, "content")
                    else str(retry_response)
                )
                retry_sql = llm_manager._clean_sql_query(retry_sql)
                if retry_sql:
                    state["generated_sql"] = retry_sql
                    state["current_error"] = None
                    state = add_ai_message(state, f"Generated SQL (simplified retry): {retry_sql}")
                    logger.info("SQL generated on retry", extra={"sql": retry_sql[:200]})
                else:
                    raise ValueError("Retry also produced empty SQL")
            except Exception as retry_err:
                error_message = "Failed to generate SQL query - empty response (all attempts)"
                state = add_error(
                    state, error_message, "sql_generation_error", ExecutionPhase.SQL_GENERATION
                )
                state["retry_count"] = state.get("retry_count", 0) + 1
                state["generation_retry_count"] = state.get("generation_retry_count", 0) + 1
                logger.warning(
                    "SQL generation failed on all attempts", extra={"error": str(retry_err)}
                )

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)

        logger.info("SQL generation completed", extra={"execution_time": execution_time})

        return state

    except Exception as e:
        error_message = f"SQL generation failed: {str(e)}"
        state = add_error(
            state, error_message, "sql_generation_error", ExecutionPhase.SQL_GENERATION
        )
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["generation_retry_count"] = state.get("generation_retry_count", 0) + 1

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_GENERATION, execution_time)

        logger.error(
            "SQL generation failed",
            extra={
                "error": str(e),
                "execution_time": execution_time,
            },
        )

        return state


__all__ = [
    "SQLOutput",
    "reasoning_node",
    "_build_pregeneration_hints",
    "_analytic_response_templates_enabled",
    "_build_deterministic_analytic_sql",
    "_build_deterministic_grouped_sql",
    "build_sql_generation_messages",
    "generate_sql_node",
]
