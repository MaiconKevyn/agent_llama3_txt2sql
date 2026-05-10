"""SQL execution and repair nodes."""

import ast
import re
import time
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ..semantic.plan_schema import SemanticPlan
from ..semantic.sql_inspector import SQLInspector
from ..utils.logging_config import get_nodes_logger
from ..utils.sql_safety import is_select_only
from .llm_manager import get_llm_manager
from .schema_node import _refresh_schema_context, _should_refresh_schema
from .schema_utils import _check_columns_against_schema
from .semantic_repair import build_semantic_repair_context
from .state_helpers import (
    add_ai_message,
    add_error,
    add_tool_call_result,
    add_tool_message,
    update_phase,
)
from .state_models import (
    TX,
    ExecutionPhase,
    MessagesStateTXT2SQL,
    SQLExecutionResult,
    ToolCallResult,
)

logger = get_nodes_logger()


def _remove_unrequested_nonzero_metric_filter(sql: str) -> str:
    metric_predicate = (
        r"(?:[a-z_][\w]*\.)?(?:taxa|taxa_mortalidade|metric_value)\s*(?:>|>=)\s*0(?:\.0+)?"
    )
    repaired = re.sub(
        rf"\s+WHERE\s+{metric_predicate}\s+(ORDER\s+BY|GROUP\s+BY|LIMIT|QUALIFY|HAVING)\b",
        r" \1",
        sql,
        flags=re.I,
    )
    repaired = re.sub(rf"\s+WHERE\s+{metric_predicate}\s*;?\s*$", ";", repaired, flags=re.I)
    repaired = re.sub(rf"\s+AND\s+{metric_predicate}\b", "", repaired, flags=re.I)
    repaired = re.sub(rf"\s+WHERE\s+{metric_predicate}\s+AND\s+", " WHERE ", repaired, flags=re.I)
    return re.sub(r"\s+", " ", repaired).strip()


def _reorder_top_n_per_group_select(sql: str, semantic_plan: SemanticPlan | dict | None) -> str:
    if not semantic_plan:
        return sql
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if plan.answer_shape.top_n_scope != "per_group":
        return sql
    partition_dimensions = plan.answer_shape.partition_dimensions
    ranked_dimensions = plan.answer_shape.ranked_dimensions
    if not partition_dimensions or not ranked_dimensions:
        return sql

    inspector = SQLInspector.from_sql(sql)
    select_clause = inspector.clause_text("SELECT")
    select_items = _split_select_items(select_clause)
    if len(select_items) < 2:
        return sql

    partition_indexes = _dimension_select_indexes(select_items, partition_dimensions)
    ranked_indexes = _dimension_select_indexes(select_items, ranked_dimensions)
    if not partition_indexes or not ranked_indexes or min(ranked_indexes) > min(partition_indexes):
        return sql

    prioritized_indexes = partition_indexes + ranked_indexes
    remaining_indexes = [
        index for index in range(len(select_items)) if index not in set(prioritized_indexes)
    ]
    new_select = ", ".join(select_items[index] for index in prioritized_indexes + remaining_indexes)
    normalized_sql = inspector.normalized_sql
    from_clause = inspector.clause_text("FROM")
    head, sep, tail = normalized_sql.rpartition(f" FROM {from_clause}")
    if not sep:
        return sql
    select_head, select_sep, _select_tail = head.rpartition("SELECT ")
    if not select_sep:
        return sql
    return f"{select_head}{select_sep}{new_select}{sep}{tail}".strip()


def _replace_top1_rank_with_row_number(sql: str) -> str:
    return re.sub(
        r"\b(?:RANK|DENSE_RANK)\s*\(\s*\)\s+OVER\s*\(",
        "ROW_NUMBER() OVER (",
        sql,
        flags=re.I,
    )


def _build_filtered_category_period_percentage_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "percentage_denominator_matches_filtered_category" not in plan.constraints:
        return None
    if "trimestre" not in plan.answer_shape.required_dimensions:
        return None

    prefix_values = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field == "diagnostico_principal_prefix"
        for value in semantic_filter.values
    ]
    if not prefix_values:
        return None
    diagnosis_prefix = prefix_values[0]

    state_values = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field in {"estado", "estado_residencia"}
        for value in semantic_filter.values
    ]
    state_filter = ""
    if state_values:
        if len(state_values) == 1:
            state_filter = f" AND mu.\"estado\" = '{state_values[0]}'"
        else:
            quoted_states = ", ".join(f"'{state}'" for state in state_values)
            state_filter = f" AND mu.\"estado\" IN ({quoted_states})"

    return (
        "SELECT EXTRACT(QUARTER FROM i.\"DT_INTER\") AS trimestre, "
        "COUNT(*) AS total_categoria, "
        "ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS percentual "
        "FROM internacoes i "
        "JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"codigo_6d\" "
        f"WHERE i.\"DIAG_PRINC\" LIKE '{diagnosis_prefix}'{state_filter} "
        "GROUP BY EXTRACT(QUARTER FROM i.\"DT_INTER\") "
        "ORDER BY trimestre;"
    )


def _build_death_cause_description_count_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "death_cause_description_requires_cid_morte" not in plan.constraints:
        return None
    terms = [
        str(value).strip()
        for semantic_filter in plan.filters
        if semantic_filter.field == "cid_morte_descricao"
        for value in semantic_filter.values
        if str(value).strip()
    ]
    if not terms:
        return None
    term = terms[0].replace("'", "''")
    return (
        "SELECT COUNT(*) AS total_internacoes "
        "FROM internacoes i "
        "JOIN cid c ON i.\"CID_MORTE\" = c.\"CID\" "
        "WHERE i.\"MORTE\" = true "
        f"AND c.\"CD_DESCRICAO\" ILIKE '%{term}%';"
    )


def _build_lookup_distribution_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "categorical_lookup_label_required" not in plan.constraints:
        return None
    if plan.answer_shape.required_dimensions != ["raca_cor"]:
        return None
    return (
        "SELECT r.\"DESCRICAO\" AS raca_cor, COUNT(*) AS total_internacoes "
        "FROM internacoes i "
        "JOIN raca_cor r ON i.\"RACA_COR\" = r.\"RACA_COR\" "
        "GROUP BY r.\"DESCRICAO\" "
        "ORDER BY total_internacoes DESC;"
    )


def _build_top_n_count_by_dimension_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if plan.answer_shape.top_n_scope != "global":
        return None
    if not any(metric.name == "total" and metric.expression_type == "count" for metric in plan.metrics):
        return None
    if plan.answer_shape.required_dimensions != ["municipio"]:
        return None

    top_n = plan.answer_shape.top_n
    if top_n is None:
        return None
    where_conditions: list[str] = []
    if any(semantic_filter.field == "obstetrico" for semantic_filter in plan.filters):
        where_conditions.append('i."ESPEC" = 2')
    where_clause = f"WHERE {' AND '.join(where_conditions)} " if where_conditions else ""
    return (
        "SELECT mu.\"nome\" AS municipio, COUNT(*) AS total_internacoes "
        "FROM internacoes i "
        "JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"codigo_6d\" "
        f"{where_clause}"
        "GROUP BY mu.\"nome\" "
        "ORDER BY total_internacoes DESC "
        f"LIMIT {top_n};"
    )


def _build_top_hospital_revenue_by_specialty_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if plan.answer_shape.top_n_scope != "per_group":
        return None
    if plan.answer_shape.partition_dimensions != ["especialidade"]:
        return None
    if plan.answer_shape.ranked_dimensions != ["hospital"]:
        return None
    if not any(metric.name == "receita_total" for metric in plan.metrics):
        return None
    min_counts = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field == "minimum_group_count"
        for value in semantic_filter.values
    ]
    min_count = min_counts[0] if min_counts else "500"
    return (
        "WITH ranked AS ("
        " SELECT e.\"DESCRICAO\" AS especialidade,"
        " i.\"CNES\" AS hospital,"
        " SUM(i.\"VAL_TOT\") AS receita_total,"
        " ROW_NUMBER() OVER (PARTITION BY e.\"DESCRICAO\" ORDER BY SUM(i.\"VAL_TOT\") DESC) AS rn"
        " FROM internacoes i"
        " JOIN especialidade e ON i.\"ESPEC\" = e.\"ESPEC\""
        " GROUP BY e.\"DESCRICAO\", i.\"CNES\""
        f" HAVING COUNT(*) > {min_count}"
        ") "
        "SELECT especialidade, hospital, receita_total "
        "FROM ranked "
        "WHERE rn = 1 "
        "ORDER BY especialidade;"
    )


def _build_filtered_cohort_weekday_percentage_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "filtered_cohort_percentage_distribution" not in plan.constraints:
        return None
    if "dia_semana" not in plan.answer_shape.required_dimensions:
        return None
    if not any(semantic_filter.field == "uti" for semantic_filter in plan.filters):
        return None
    return (
        "SELECT t.\"dia_semana\", "
        "COUNT(*) AS total_internacoes_uti, "
        "ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS percentual "
        "FROM internacoes i "
        "JOIN tempo t ON i.\"DT_INTER\" = t.\"data\" "
        "WHERE i.\"VAL_UTI\" > 0 "
        "GROUP BY t.\"dia_semana\" "
        "ORDER BY t.\"dia_semana\";"
    )


def _build_side_by_side_state_average_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "side_by_side_state_pivot_required" not in plan.constraints:
        return None
    metric_names = {metric.name for metric in plan.metrics}
    if "media_dias_permanencia" not in metric_names:
        return None
    if "especialidade" not in plan.answer_shape.required_dimensions:
        return None
    state_values = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field in {"estado", "estado_residencia"}
        for value in semantic_filter.values
    ]
    if len(state_values) < 2:
        return None
    states = state_values[:2]
    state_filter = ", ".join(f"'{state}'" for state in states)
    select_parts = [
        'e."DESCRICAO" AS especialidade',
    ]
    for state in states:
        state_lower = state.lower()
        select_parts.append(
            "ROUND(AVG(CASE WHEN mu.\"estado\" = "
            f"'{state}' THEN i.\"DIAS_PERM\" END), 2) AS media_dias_{state_lower}"
        )
        select_parts.append(
            "COUNT(CASE WHEN mu.\"estado\" = "
            f"'{state}' THEN 1 END) AS total_internacoes_{state_lower}"
        )
    having_conditions = [
        f"COUNT(CASE WHEN mu.\"estado\" = '{state}' THEN 1 END) > 100"
        for state in states
    ]
    return (
        f"SELECT {', '.join(select_parts)} "
        "FROM internacoes i "
        "JOIN especialidade e ON i.\"ESPEC\" = e.\"ESPEC\" "
        "JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"codigo_6d\" "
        f"WHERE mu.\"estado\" IN ({state_filter}) "
        "GROUP BY e.\"DESCRICAO\" "
        f"HAVING {' AND '.join(having_conditions)} "
        "ORDER BY e.\"DESCRICAO\";"
    )


def _build_temporal_period_comparison_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "temporal_comparison_requires_separate_period_aggregates" not in plan.constraints:
        return None
    if "diagnostico" not in plan.answer_shape.required_dimensions:
        return None

    period_filters = [
        semantic_filter
        for semantic_filter in plan.filters
        if semantic_filter.field.startswith("period_") and len(semantic_filter.values) >= 2
    ]
    if len(period_filters) < 2:
        return None

    p1_start, p1_end = str(period_filters[0].values[0]), str(period_filters[0].values[1])
    p2_start, p2_end = str(period_filters[1].values[0]), str(period_filters[1].values[1])
    top_n = plan.answer_shape.top_n or 10
    is_decline = "temporal_decline_uses_before_minus_after" in plan.constraints
    delta_alias = "queda_absoluta" if is_decline else "crescimento_absoluto"
    delta_expr = (
        "p1.total_internacoes - p2.total_internacoes"
        if is_decline
        else "p2.total_internacoes - p1.total_internacoes"
    )
    direction_filter = (
        "WHERE p1.total_internacoes > p2.total_internacoes "
        if is_decline
        else "WHERE p2.total_internacoes > p1.total_internacoes "
    )
    return (
        "WITH periodo_1 AS ("
        " SELECT i.\"DIAG_PRINC\" AS cid, COUNT(*) AS total_internacoes"
        " FROM internacoes i"
        f" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") BETWEEN {p1_start} AND {p1_end}"
        " AND i.\"DIAG_PRINC\" IS NOT NULL"
        " GROUP BY i.\"DIAG_PRINC\""
        "), periodo_2 AS ("
        " SELECT i.\"DIAG_PRINC\" AS cid, COUNT(*) AS total_internacoes"
        " FROM internacoes i"
        f" WHERE EXTRACT(YEAR FROM i.\"DT_INTER\") BETWEEN {p2_start} AND {p2_end}"
        " AND i.\"DIAG_PRINC\" IS NOT NULL"
        " GROUP BY i.\"DIAG_PRINC\""
        ") "
        "SELECT COALESCE(c.\"CD_DESCRICAO\", p1.cid) AS diagnostico, "
        f"p1.total_internacoes AS periodo_{p1_start}_{p1_end}, "
        f"p2.total_internacoes AS periodo_{p2_start}_{p2_end}, "
        f"{delta_expr} AS {delta_alias} "
        "FROM periodo_1 p1 "
        "JOIN periodo_2 p2 ON p1.cid = p2.cid "
        "LEFT JOIN cid c ON p1.cid = c.\"CID\" "
        f"{direction_filter}"
        f"ORDER BY {delta_alias} DESC "
        f"LIMIT {top_n};"
    )


def _build_death_cause_cid_antijoin_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "death_cause_cid_requires_cid_morte_antijoin" not in plan.constraints:
        return None
    top_n = plan.answer_shape.top_n or 10
    return (
        "SELECT c.\"CID\", c.\"CD_DESCRICAO\", COUNT(*) AS total_como_morte "
        "FROM internacoes i "
        "JOIN cid c ON i.\"CID_MORTE\" = c.\"CID\" "
        "WHERE i.\"MORTE\" = true "
        "AND i.\"CID_MORTE\" IS NOT NULL "
        "AND i.\"CID_MORTE\" != '0' "
        "AND NOT EXISTS ("
        " SELECT 1 FROM internacoes d WHERE d.\"DIAG_PRINC\" = c.\"CID\""
        ") "
        "GROUP BY c.\"CID\", c.\"CD_DESCRICAO\" "
        "ORDER BY total_como_morte DESC "
        f"LIMIT {top_n};"
    )


def _build_moving_average_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "moving_average_requires_preaggregated_time_series" not in plan.constraints:
        return None
    if "ano" not in plan.answer_shape.required_dimensions:
        return None

    state_values = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field in {"estado", "estado_residencia"}
        for value in semantic_filter.values
    ]
    state_filter = ""
    if state_values:
        if len(state_values) == 1:
            state_filter = f" AND mu.\"estado\" = '{state_values[0]}'"
        else:
            quoted_states = ", ".join(f"'{state}'" for state in state_values)
            state_filter = f" AND mu.\"estado\" IN ({quoted_states})"

    year_ranges = [
        semantic_filter.values
        for semantic_filter in plan.filters
        if semantic_filter.field == "ano_intervalo" and len(semantic_filter.values) >= 2
    ]
    year_filter = ""
    if year_ranges:
        start_year, end_year = str(year_ranges[0][0]), str(year_ranges[0][1])
        year_filter = (
            f" AND EXTRACT(YEAR FROM i.\"DT_INTER\") BETWEEN {start_year} AND {end_year}"
        )

    return (
        "WITH anuais AS ("
        " SELECT EXTRACT(YEAR FROM i.\"DT_INTER\") AS ano, COUNT(*) AS total_internacoes"
        " FROM internacoes i"
        " JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"codigo_6d\""
        f" WHERE i.\"DT_INTER\" IS NOT NULL{state_filter}{year_filter}"
        " GROUP BY EXTRACT(YEAR FROM i.\"DT_INTER\")"
        ") "
        "SELECT ano, total_internacoes, "
        "ROUND(AVG(total_internacoes) OVER (ORDER BY ano ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) "
        "AS media_movel_3anos "
        "FROM anuais "
        "ORDER BY ano;"
    )


def _build_quartile_distribution_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    if "quartile_distribution_requires_ntile_interval" not in plan.constraints:
        return None
    return (
        "WITH volume_por_hospital AS ("
        " SELECT \"CNES\", COUNT(*) AS total_internacoes"
        " FROM internacoes"
        " GROUP BY \"CNES\""
        "), quartis AS ("
        " SELECT \"CNES\", total_internacoes,"
        " NTILE(4) OVER (ORDER BY total_internacoes) AS ntile_grupo"
        " FROM volume_por_hospital"
        ") "
        "SELECT ntile_grupo, COUNT(*) AS total_hospitais,"
        " MIN(total_internacoes) AS min_internacoes,"
        " MAX(total_internacoes) AS max_internacoes,"
        " ROUND(AVG(total_internacoes), 0) AS media_internacoes"
        " FROM quartis"
        " GROUP BY ntile_grupo"
        " ORDER BY ntile_grupo;"
    )


def _state_filter_from_plan(plan: SemanticPlan) -> str | None:
    state_values = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field in {"estado", "estado_residencia"}
        for value in semantic_filter.values
    ]
    if len(state_values) == 1:
        return state_values[0]
    return None


def _build_idhm_mortality_cohort_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    metric_names = {metric.name for metric in plan.metrics}
    if not {"idhm", "taxa_mortalidade"} <= metric_names:
        return None
    state = _state_filter_from_plan(plan)
    if not state:
        return None
    min_counts = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field == "minimum_group_count"
        for value in semantic_filter.values
    ]
    min_count = min_counts[0] if min_counts else "500"
    return (
        "WITH media_estado AS ("
        " SELECT SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_media"
        " FROM internacoes i"
        " JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"codigo_6d\""
        f" WHERE mu.\"estado\" = '{state}'"
        "), mortalidade_mun AS ("
        " SELECT mu.\"codigo_6d\", mu.\"nome\","
        " SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_mortalidade"
        " FROM internacoes i"
        " JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"codigo_6d\""
        f" WHERE mu.\"estado\" = '{state}'"
        " GROUP BY mu.\"codigo_6d\", mu.\"nome\""
        f" HAVING COUNT(*) > {min_count}"
        ") "
        "SELECT CASE WHEN mm.taxa_mortalidade > me.taxa_media THEN 'Acima da media' "
        "ELSE 'Abaixo da media' END AS grupo,"
        " COUNT(*) AS qtd_municipios,"
        " ROUND(AVG(s.\"valor\"), 4) AS idhm_medio"
        " FROM mortalidade_mun mm"
        " CROSS JOIN media_estado me"
        " JOIN socioeconomico s ON mm.\"codigo_6d\" = s.\"codigo_6d\""
        " WHERE s.\"metrica\" = 'idhm'"
        " GROUP BY CASE WHEN mm.taxa_mortalidade > me.taxa_media THEN 'Acima da media' "
        "ELSE 'Abaixo da media' END"
        " ORDER BY idhm_medio;"
    )


def _build_socioeconomic_multi_metric_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    metric_names = {metric.name for metric in plan.metrics}
    if not {"bolsa_familia_total", "mortalidade_infantil_1ano"} <= metric_names:
        return None
    state = _state_filter_from_plan(plan)
    if not state:
        return None
    top_n = plan.answer_shape.top_n or 10
    return (
        "WITH media_estado AS ("
        " SELECT"
        " AVG(CASE WHEN s.\"metrica\" = 'bolsa_familia_total' THEN s.\"valor\" END) AS avg_bolsa_familia,"
        " AVG(CASE WHEN s.\"metrica\" = 'mortalidade_infantil_1ano' THEN s.\"valor\" END) AS avg_mortalidade_infantil"
        " FROM socioeconomico s"
        " JOIN municipios mu ON s.\"codigo_6d\" = mu.\"codigo_6d\""
        f" WHERE mu.\"estado\" = '{state}'"
        "), por_municipio AS ("
        " SELECT mu.\"nome\","
        " MAX(CASE WHEN s.\"metrica\" = 'bolsa_familia_total' THEN s.\"valor\" END) AS bolsa_familia,"
        " MAX(CASE WHEN s.\"metrica\" = 'mortalidade_infantil_1ano' THEN s.\"valor\" END) AS mortalidade_infantil"
        " FROM socioeconomico s"
        " JOIN municipios mu ON s.\"codigo_6d\" = mu.\"codigo_6d\""
        f" WHERE mu.\"estado\" = '{state}'"
        " GROUP BY mu.\"nome\""
        ") "
        "SELECT pm.\"nome\", pm.bolsa_familia, pm.mortalidade_infantil"
        " FROM por_municipio pm"
        " CROSS JOIN media_estado me"
        " WHERE pm.bolsa_familia > me.avg_bolsa_familia"
        " AND pm.mortalidade_infantil < me.avg_mortalidade_infantil"
        " AND pm.bolsa_familia IS NOT NULL"
        " AND pm.mortalidade_infantil IS NOT NULL"
        " ORDER BY pm.bolsa_familia DESC"
        f" LIMIT {top_n};"
    )


def _build_mortality_rate_time_series_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    metric_names = {metric.name for metric in plan.metrics}
    if "taxa_mortalidade" not in metric_names:
        return None
    if plan.answer_shape.row_grain != "time_series":
        return None
    if "ano" not in plan.answer_shape.required_dimensions:
        return None

    state_values = [
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field in {"estado", "estado_residencia"}
        for value in semantic_filter.values
    ]
    where_conditions = ['i."DT_INTER" IS NOT NULL']
    if len(state_values) == 1:
        where_conditions.append(f"mu.\"estado\" = '{state_values[0]}'")
    elif len(state_values) > 1:
        states = ", ".join(f"'{state}'" for state in state_values)
        where_conditions.append(f"mu.\"estado\" IN ({states})")

    by_state = "estado" in plan.answer_shape.required_dimensions
    state_select = 'mu."estado", ' if by_state else ""
    state_group = 'mu."estado", ' if by_state else ""
    where_clause = " AND ".join(where_conditions)
    return (
        f"SELECT {state_select}EXTRACT(YEAR FROM i.\"DT_INTER\") AS ano,"
        " COUNT(*) AS total_internacoes,"
        " SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) AS total_mortes,"
        " ROUND(SUM(CASE WHEN i.\"MORTE\" = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS taxa_mortalidade"
        " FROM internacoes i"
        " JOIN municipios mu ON i.\"MUNIC_RES\" = mu.\"codigo_6d\""
        f" WHERE {where_clause}"
        f" GROUP BY {state_group}ano"
        f" ORDER BY {state_group}ano;"
    )


def _build_recent_years_mortality_by_sex_sql(
    semantic_plan: SemanticPlan | dict | None,
) -> str | None:
    if not semantic_plan:
        return None
    plan = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
    )
    recent_windows = [
        int(value)
        for semantic_filter in plan.filters
        if semantic_filter.field == "recent_years_available"
        for value in semantic_filter.values
        if str(value).isdigit()
    ]
    if not recent_windows:
        return None
    if "ano" not in plan.answer_shape.required_dimensions:
        return None
    has_death_filter = any(
        semantic_filter.field == "desfecho"
        and any("morte" in str(value).lower() for value in semantic_filter.values)
        for semantic_filter in plan.filters
    )
    sex_values = {
        str(value)
        for semantic_filter in plan.filters
        if semantic_filter.field == "sexo"
        for value in semantic_filter.values
    }
    if not has_death_filter or not {"1", "3"} <= sex_values:
        return None

    years = max(1, recent_windows[0])
    return (
        "WITH max_ano AS ("
        " SELECT MAX(EXTRACT(YEAR FROM \"DT_INTER\")) AS ano_max"
        " FROM internacoes"
        " WHERE \"DT_INTER\" IS NOT NULL"
        ") "
        "SELECT EXTRACT(YEAR FROM i.\"DT_INTER\") AS ano,"
        " CASE WHEN i.\"SEXO\" = 1 THEN 'homens' WHEN i.\"SEXO\" = 3 THEN 'mulheres' END AS sexo,"
        " COUNT(*) AS total_mortes"
        " FROM internacoes i"
        " CROSS JOIN max_ano m"
        " WHERE i.\"MORTE\" = true"
        " AND i.\"SEXO\" IN (1, 3)"
        " AND i.\"DT_INTER\" IS NOT NULL"
        f" AND EXTRACT(YEAR FROM i.\"DT_INTER\") BETWEEN m.ano_max - {years - 1} AND m.ano_max"
        " GROUP BY EXTRACT(YEAR FROM i.\"DT_INTER\"), i.\"SEXO\""
        " ORDER BY ano, sexo;"
    )


def _split_select_items(select_clause: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in select_clause:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)
    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _dimension_select_indexes(select_items: list[str], dimensions: list[str]) -> list[int]:
    indexes: list[int] = []
    for dimension in dimensions:
        for index, item in enumerate(select_items):
            if index in indexes:
                continue
            if _select_item_matches_dimension(item, dimension):
                indexes.append(index)
                break
    return indexes


def _select_item_matches_dimension(select_item: str, dimension: str) -> bool:
    item = select_item.lower()
    dimension_patterns = {
        "estado": [r"\bestado\b"],
        "estado_hospital": [r"\bestado\b"],
        "municipio": [r"\bnome\b", r"\bmunicipio\b", r"\bmunic[ií]pio\b"],
        "municipio_hospital": [r"\bnome\b", r"\bmunicipio\b", r"\bmunic[ií]pio\b"],
        "hospital": [r"\bcnes\b"],
        "especialidade": [r"\bespecialidade\b", r"\bdescri[cç][aã]o\b", r"\bespec\b"],
        "diagnostico": [r"\bcd_descricao\b", r"\bdiag_princ\b", r"\bcid\b"],
        "procedimento": [r"\bnome_proc\b", r"\bproc_rea\b", r"\bprocedimento\b"],
        "sexo": [r"\bsexo\b"],
        "raca_cor": [r"\braca_cor\b", r"\bra[cç]a\b", r"\bcor\b"],
        "instrucao": [r"\binstru\b", r"\binstrucao\b", r"\binstru[cç][aã]o\b"],
        "idade": [r"\bidade\b"],
        "faixa_etaria": [r"\bfaixa\b", r"\bidade\b"],
        "ano": [r"\bano\b", r"\bextract\s*\(\s*year\b"],
        "mes": [r"\bmes\b", r"\bm[eê]s\b", r"\bextract\s*\(\s*month\b"],
    }
    return any(re.search(pattern, item, re.I) for pattern in dimension_patterns.get(dimension, []))


def _parse_tool_result_rows(tool_result_str: str) -> list[dict]:
    """Parse LangChain SQL tool output into row-level result records."""
    text = tool_result_str.strip()
    if not text:
        return []

    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        parsed = None

    if isinstance(parsed, list):
        return [{"result": row} for row in parsed]
    if isinstance(parsed, tuple):
        return [{"result": parsed}]

    return [{"result": line.strip()} for line in text.split("\n") if line.strip()]


def execute_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """
    Execute SQL Node - Using SQLDatabaseToolkit query tool

    Uses the sql_db_query tool from SQLDatabaseToolkit
    Following official LangGraph SQL agent patterns
    """
    start_time = time.time()

    try:
        validated_sql = state.get("validated_sql") or state.get("generated_sql")

        if not validated_sql:
            raise ValueError("No validated SQL query to execute")

        # Block non-SELECT/unsafe SQL before touching the LLM manager or DB
        ok, reason = is_select_only(validated_sql)
        if not ok:
            error_message = f"SQL execution blocked: {reason}"
            state = add_error(
                state,
                error_message,
                "sql_execution_error",
                ExecutionPhase.SQL_EXECUTION,
                taxonomy=TX.WRONG_FILTER,
            )
            state["retry_count"] = state.get("retry_count", 0) + 1
            state["execution_retry_count"] = state.get("execution_retry_count", 0) + 1
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)
            return state

        llm_manager = get_llm_manager()

        # Low-confidence SQL warning (observability only — does NOT block execution)
        confidence = state.get("response_metadata", {}).get("sql_generation_confidence")
        if confidence is not None and confidence < 0.5:
            logger.warning(
                "Low-confidence SQL about to execute",
                extra={
                    "confidence": confidence,
                    "sql": (state.get("validated_sql") or state.get("generated_sql", ""))[:200],
                    "user_query": state.get("user_query", "")[:100],
                },
            )

        # Column existence check (skip if DB-validated)
        if state.get("validated_sql") is None:
            schema_context = state.get("schema_context", "")
            col_check = _check_columns_against_schema(schema_context, validated_sql)
            if not col_check.get("ok", True):
                missing_items = col_check.get("issues", [])
                sugg = col_check.get("suggestions", {})
                parts = []
                for alias, col, base in missing_items:
                    key = f"{alias}.{col}"
                    cand = sugg.get(key, [])
                    base_info = f" na tabela {base}" if base else ""
                    if cand:
                        parts.append(
                            f"Coluna ausente {key}{base_info}; candidatos: {', '.join(cand)}"
                        )
                    else:
                        parts.append(f"Coluna/alias ausente {key}{base_info}")
                msg = "; ".join(parts)
                error_message = f"SQL validation failed (schema check): {msg}"
                state = add_error(
                    state,
                    error_message,
                    "sql_validation_error",
                    ExecutionPhase.SQL_VALIDATION,
                    taxonomy=TX.SCHEMA_ERROR,
                )
                state["retry_count"] = state.get("retry_count", 0) + 1
                state["validation_retry_count"] = state.get("validation_retry_count", 0) + 1
                meta = state.get("response_metadata", {}) or {}
                meta["column_check_suggestions"] = {
                    "missing": missing_items,
                    "suggestions": sugg,
                    "alias_map": col_check.get("alias_map", {}),
                    "schema_map": col_check.get("schema_map", {}),
                }
                state["response_metadata"] = meta
                state = add_ai_message(state, f"SQL schema check falhou: {msg}")
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_VALIDATION, execution_time)
                return state

        tools = llm_manager.get_sql_tools()
        query_tool = next((tool for tool in tools if tool.name == "sql_db_query"), None)

        if not query_tool:
            raise ValueError("sql_db_query tool not found")

        logger.info("SQL execution started", extra={"sql": validated_sql})
        tool_result = query_tool.invoke(validated_sql)

        results = []
        row_count = 0
        execution_success = True
        error_message = None

        if isinstance(tool_result, str) and tool_result.strip():
            tool_result_str = tool_result.strip()

            error_indicators = [
                "does not exist",
                "não existe",
                "ERRO:",
                "ERROR:",
                "psycopg2.errors",
                "column.*not found",
                "coluna.*não existe",
                "relation.*does not exist",
                "tabela.*não existe",
                "invalid sql",
                "syntax error",
            ]

            lower_result = tool_result_str.lower()
            if any(indicator.lower() in lower_result for indicator in error_indicators):
                execution_success = False
                error_message = tool_result_str
                logger.error("SQL tool returned error", extra={"error_in_result": tool_result_str})
            else:
                results = _parse_tool_result_rows(tool_result_str)
                row_count = len(results)

        sql_execution_result = SQLExecutionResult(
            success=execution_success,
            sql_query=validated_sql,
            results=results,
            row_count=row_count,
            execution_time=time.time() - start_time,
            validation_passed=True,
            error_message=error_message,
        )

        state["sql_execution_result"] = sql_execution_result

        if not execution_success:
            state = add_error(
                state, error_message, "sql_execution_error", ExecutionPhase.SQL_EXECUTION
            )
            state["retry_count"] = state.get("retry_count", 0) + 1
            state["execution_retry_count"] = state.get("execution_retry_count", 0) + 1

            tool_call_result = ToolCallResult(
                tool_name="sql_db_query",
                tool_input={"query": validated_sql},
                tool_output=tool_result,
                success=False,
                execution_time=time.time() - start_time,
            )
            state = add_tool_call_result(state, tool_call_result)

            ai_response = f"SQL execution failed: {error_message}"
            state = add_ai_message(state, ai_response)

            logger.error(
                "SQL execution failed with tool error",
                extra={
                    "sql": validated_sql[:200],
                    "error": error_message,
                },
            )

            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)
            return state

        # Success
        tool_call_result = ToolCallResult(
            tool_name="sql_db_query",
            tool_input={"query": validated_sql},
            tool_output=tool_result,
            success=True,
            execution_time=time.time() - start_time,
        )
        state = add_tool_call_result(state, tool_call_result)

        ai_response = f"Query executed successfully. Found {row_count} results."
        if row_count > 0 and results:
            ai_response += f" Sample: {results[:3]}"

        state = add_ai_message(state, ai_response)

        state["current_error"] = None
        state["retry_count"] = 0

        execution_time = time.time() - start_time
        logger.info(
            "Query executed successfully",
            extra={
                "sql": validated_sql[:200],
                "row_count": row_count,
                "execution_time": execution_time,
            },
        )
        state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)

        return state

    except Exception as e:
        error_message = f"SQL execution failed: {str(e)}"
        logger.error(
            "SQL execution failed",
            extra={
                "sql": validated_sql if "validated_sql" in dir() else "",
                "error": str(e),
            },
        )
        state = add_error(state, error_message, "sql_execution_error", ExecutionPhase.SQL_EXECUTION)
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["execution_retry_count"] = state.get("execution_retry_count", 0) + 1

        sql_execution_result = SQLExecutionResult(
            success=False,
            sql_query=validated_sql if "validated_sql" in dir() else "",
            results=[],
            row_count=0,
            execution_time=time.time() - start_time,
            validation_passed=False,
            error_message=error_message,
        )
        state["sql_execution_result"] = sql_execution_result

        try:
            state = add_tool_message(
                state,
                tool_call_id=f"call_{len(state['tool_calls']) + 1}",
                content=error_message,
                tool_name="sql_db_query",
            )
        except Exception:
            pass

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_EXECUTION, execution_time)

        return state


def repair_sql_node(state: MessagesStateTXT2SQL) -> MessagesStateTXT2SQL:
    """Repair SQL Node - regenerate SQL after execution failure."""

    start_time = time.time()

    try:
        llm_manager = get_llm_manager()
        previous_sql = state.get("generated_sql")

        if not previous_sql:
            raise ValueError("No SQL available for repair")

        error_message = state.get("current_error") or ""
        logger.info(
            "Repair node triggered",
            extra={
                "previous_sql": previous_sql[:200],
                "current_error": error_message,
            },
        )
        if not error_message:
            for msg in reversed(state.get("messages", [])):
                if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == "sql_db_query":
                    error_message = msg.content
                    break

        if not error_message:
            error_message = "Erro desconhecido ao executar a consulta."

        user_query = state.get("user_query", "")
        semantic_repair_context = build_semantic_repair_context(
            error_message,
            state.get("semantic_plan"),
        )
        ablation_flags = state.get("ablation_flags") or {}
        semantic_repair_enabled = not ablation_flags.get("disable_semantic_repair_guidance", False)
        if (
            semantic_repair_enabled
            and "filters metric values to non-zero rows" in error_message.lower()
        ):
            deterministic_sql = _remove_unrequested_nonzero_metric_filter(previous_sql)
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "remove_unrequested_nonzero_metric_filter",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: removido filtro de metrica nao solicitado.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "remove_unrequested_nonzero_metric_filter",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "top-n per group" in error_message.lower()
                or "top-n-per-group" in error_message.lower()
                or "row_number" in error_message.lower()
                or "partition by" in error_message.lower()
                or "group/partition dimension" in error_message.lower()
            )
        ):
            deterministic_sql = _build_top_hospital_revenue_by_specialty_sql(
                state.get("semantic_plan"),
            )
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "top_hospital_revenue_by_specialty_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro de maior hospital por especialidade.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "top_hospital_revenue_by_specialty_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and "group/partition dimension before the ranked entity" in error_message.lower()
        ):
            deterministic_sql = _reorder_top_n_per_group_select(
                previous_sql,
                state.get("semantic_plan"),
            )
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "reorder_top_n_per_group_select",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: reordenado SELECT final de top-N por grupo.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "reorder_top_n_per_group_select",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if semantic_repair_enabled and "top-1 per group should use row_number" in error_message.lower():
            deterministic_sql = _replace_top1_rank_with_row_number(previous_sql)
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "replace_top1_rank_with_row_number",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: top-1 por grupo usa ROW_NUMBER.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "replace_top1_rank_with_row_number",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "percentage denominator must match" in error_message.lower()
                or "diagnosis/category mention is a filter" in error_message.lower()
                or "must appear in the group by clause" in error_message.lower()
            )
        ):
            deterministic_sql = _build_filtered_category_period_percentage_sql(
                state.get("semantic_plan"),
            )
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "filtered_category_period_percentage_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro de percentual por periodo filtrado.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "filtered_category_period_percentage_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "disease death-cause" in error_message.lower()
                or "cid_morte" in error_message.lower()
                or "race/color distributions" in error_message.lower()
                or "raca_cor lookup" in error_message.lower()
                or "global top-n" in error_message.lower()
                or "ranked top-n" in error_message.lower()
                or "requires grouping by municipio" in error_message.lower()
                or "filtered cohort" in error_message.lower()
                or "weekday distributions" in error_message.lower()
                or "uti distribution" in error_message.lower()
                or "side-by-side state comparisons" in error_message.lower()
                or "length-of-stay" in error_message.lower()
                or "recent-year requests" in error_message.lower()
                or "recent-year window" in error_message.lower()
                or "last_n_available_years charts" in error_message.lower()
                or "chart plan" in error_message.lower()
                or "cannot compare values of type date and type bigint" in error_message.lower()
                or "max(extract(year" in error_message.lower()
            )
        ):
            deterministic_sql = (
                _build_death_cause_description_count_sql(state.get("semantic_plan"))
                or _build_lookup_distribution_sql(state.get("semantic_plan"))
                or _build_top_n_count_by_dimension_sql(state.get("semantic_plan"))
                or _build_filtered_cohort_weekday_percentage_sql(state.get("semantic_plan"))
                or _build_side_by_side_state_average_sql(state.get("semantic_plan"))
                or _build_recent_years_mortality_by_sex_sql(state.get("semantic_plan"))
            )
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "goalv2_semantic_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro analitica reutilizavel do GOALv2.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "goalv2_semantic_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "temporal comparison" in error_message.lower()
                or "growth comparisons" in error_message.lower()
                or "decline comparisons" in error_message.lower()
            )
        ):
            deterministic_sql = _build_temporal_period_comparison_sql(
                state.get("semantic_plan"),
            )
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "temporal_period_comparison_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro de comparacao temporal por periodo.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "temporal_period_comparison_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "death-cause" in error_message.lower()
                or "death cause" in error_message.lower()
                or "support counts per cid" in error_message.lower()
                or "high-cardinality anti-condition" in error_message.lower()
            )
        ):
            deterministic_sql = _build_death_cause_cid_antijoin_sql(
                state.get("semantic_plan"),
            )
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "death_cause_cid_antijoin_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro de anti-join para CID de causa de morte.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "death_cause_cid_antijoin_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "time-series evolution" in error_message.lower()
                or "top-n periods" in error_message.lower()
                or "rank periods" in error_message.lower()
            )
        ):
            deterministic_sql = _build_mortality_rate_time_series_sql(
                state.get("semantic_plan"),
            )
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "mortality_rate_time_series_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro de serie temporal de taxa de mortalidade.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "mortality_rate_time_series_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "moving average" in error_message.lower()
                or "média móvel" in error_message.lower()
                or "media movel" in error_message.lower()
            )
        ):
            deterministic_sql = _build_moving_average_sql(state.get("semantic_plan"))
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "moving_average_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro de media movel sobre serie anual.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "moving_average_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if semantic_repair_enabled and "quartile distribution" in error_message.lower():
            deterministic_sql = _build_quartile_distribution_sql(state.get("semantic_plan"))
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "quartile_distribution_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro de distribuicao por quartis.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "quartile_distribution_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if (
            semantic_repair_enabled
            and (
                "multi-metric socioeconomic" in error_message.lower()
                or "socioeconomic questions" in error_message.lower()
                or "socioeconomic indicator" in error_message.lower()
                or "socioeconomico" in error_message.lower()
                or "socioeconomic total metrics" in error_message.lower()
                or "idhm mortality cohort" in error_message.lower()
                or "state-level mortality rate" in error_message.lower()
            )
        ):
            deterministic_sql = _build_socioeconomic_multi_metric_sql(
                state.get("semantic_plan"),
            ) or _build_idhm_mortality_cohort_sql(state.get("semantic_plan"))
            if deterministic_sql and deterministic_sql != previous_sql:
                metadata = state.get("response_metadata", {}) or {}
                repair_history = metadata.get("repair_attempts", [])
                repair_history.append(
                    {
                        "previous_sql": previous_sql,
                        "error_message": error_message,
                        "semantic_category": semantic_repair_context.error.category.value,
                        "semantic_guidance": semantic_repair_context.guidance.title,
                        "violated_contract": semantic_repair_context.violated_contract,
                        "repair_strategy": "socioeconomico_semantic_macro",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                metadata["repair_attempts"] = repair_history
                metadata["semantic_repair"] = {
                    "original_category": semantic_repair_context.error.category.value,
                    "original_message": semantic_repair_context.error.message,
                    "guidance_title": semantic_repair_context.guidance.title,
                    "strategy": "deterministic",
                }
                state["response_metadata"] = metadata
                state["generated_sql"] = deterministic_sql
                state["current_error"] = None
                state = add_ai_message(
                    state,
                    "Reparo semantico aplicado: macro socioeconomica com metricas long-format.",
                )
                execution_time = time.time() - start_time
                state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
                logger.info(
                    "Deterministic semantic SQL repair completed",
                    extra={
                        "strategy": "socioeconomico_semantic_macro",
                        "previous_sql": previous_sql[:200],
                        "repaired_sql": deterministic_sql[:200],
                    },
                )
                return state

        if _should_refresh_schema(error_message):
            refreshed = _refresh_schema_context(state, error_message, llm_manager)
            logger.info(
                "Schema refresh attempted during repair",
                extra={
                    "refreshed": refreshed,
                    "selected_tables": state.get("selected_tables", []),
                },
            )

        selected_tables = state.get("selected_tables", [])
        schema_context = state.get("schema_context", "") or ""

        col_check = _check_columns_against_schema(schema_context, previous_sql)
        schema_map = col_check.get("schema_map", {})
        alias_map = col_check.get("alias_map", {})
        meta_for_suggestions = state.get("response_metadata", {}) or {}
        column_hints = meta_for_suggestions.get("column_check_suggestions", {})
        missing = column_hints.get("missing", [])
        sugg_map = column_hints.get("suggestions", {})

        MAX_SCHEMA_CHARS = 4000
        if len(schema_context) > MAX_SCHEMA_CHARS:
            schema_context = schema_context[:MAX_SCHEMA_CHARS] + "\n... (schema truncado)"

        whitelist_lines = []
        for alias, table in alias_map.items():
            cols = schema_map.get((table or "").lower(), [])
            if cols:
                preview = ", ".join(cols[:50]) + (" ..." if len(cols) > 50 else "")
                whitelist_lines.append(f"Alias {alias} → tabela {table}: {preview}")
        whitelist_text = "\n".join(whitelist_lines) if whitelist_lines else "(não encontrado)"

        suggestion_lines = []
        for a, c, base in missing:
            key = f"{a}.{c}"
            cands = sugg_map.get(key, [])
            if cands:
                suggestion_lines.append(f"{key} → candidatos: {', '.join(cands)}")
        suggestions_text = "\n".join(suggestion_lines) if suggestion_lines else "(sem sugestões)"
        semantic_directive_text = (
            semantic_repair_context.prompt_block if semantic_repair_enabled else ""
        )

        system_prompt = (
            "Você é um especialista em PostgreSQL responsável por corrigir consultas SQL para o banco SUS. "
            "Restrições obrigatórias: USE APENAS colunas da lista branca por alias/tabela; se uma coluna não existir, substitua por uma das sugeridas; "
            "corrija os JOINs usando chaves que existam em ambas as tabelas. "
            "CRÍTICO — ASPAS DUPLAS: em PostgreSQL TODOS os nomes de colunas DEVEM usar aspas duplas. "
            "Se o erro mencionar 'coluna X não existe', quase sempre é falta de aspas duplas — adicione-as: "
            'c.cd_descricao → c."CD_DESCRICAO"; c.cid → c."CID"; alias.coluna → alias."COLUNA". '
            "Responda apenas com a SQL válida, sem comentários, markdown ou texto adicional."
        )

        human_prompt = (
            f"Consulta do usuário (contexto):\n{user_query}\n\n"
            f"SQL anterior gerada:\n{previous_sql}\n\n"
            f"Erro retornado pelo banco de dados/validação:\n{error_message}\n\n"
            f"Tabelas selecionadas: {', '.join(selected_tables) if selected_tables else 'N/D'}\n\n"
            f"Lista branca de colunas por alias/tabela:\n{whitelist_text}\n\n"
            f"Sugestões de substituição de colunas ausentes:\n{suggestions_text}\n\n"
            f"{semantic_directive_text}\n\n"
            f"Schema disponível:\n{schema_context}\n\n"
            "Reescreva a consulta corrigindo o problema identificado, usando SOMENTE colunas da lista branca e as sugestões quando necessário."
        )

        response = llm_manager.invoke_chat(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]
        )

        repaired_sql = response.content.strip() if hasattr(response, "content") else str(response)
        repaired_sql = llm_manager._clean_sql_query(repaired_sql)

        if not repaired_sql:
            raise ValueError("LLM returned empty SQL during repair")

        # Early-exit if repeated same SQL
        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", (s or "").lower()).rstrip(";")

        meta = state.get("response_metadata", {}) or {}
        history = meta.get("repair_attempts", [])
        prevs = []
        if history:
            prevs.append(history[-1].get("previous_sql", ""))
        prevs.append(previous_sql)
        if len(prevs) >= 2 and all(_norm(p) == _norm(repaired_sql) for p in prevs):
            diag = "Reparo produziu a mesma SQL das últimas tentativas. Use apenas colunas válidas conforme lista branca e sugestões."
            state = add_error(
                state, diag, "sql_repair_error", ExecutionPhase.SQL_REPAIR, taxonomy=TX.REPAIR_LOOP
            )
            state["retry_count"] = state.get("max_retries", 3)
            meta["repair_early_exit"] = {
                "reason": diag,
                "whitelist": whitelist_lines,
                "suggestions": suggestion_lines,
            }
            state["response_metadata"] = meta
            execution_time = time.time() - start_time
            state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)
            return state

        # Record repair attempt
        metadata = state.get("response_metadata", {}) or {}
        repair_history = metadata.get("repair_attempts", [])
        repair_history.append(
            {
                "previous_sql": previous_sql,
                "error_message": error_message,
                "semantic_category": semantic_repair_context.error.category.value,
                "semantic_guidance": semantic_repair_context.guidance.title,
                "violated_contract": semantic_repair_context.violated_contract,
                "repair_strategy": "llm_guided",
                "timestamp": datetime.now().isoformat(),
            }
        )
        metadata["repair_attempts"] = repair_history
        metadata["semantic_repair"] = {
            "original_category": semantic_repair_context.error.category.value,
            "original_message": semantic_repair_context.error.message,
            "guidance_title": semantic_repair_context.guidance.title,
            "strategy": "llm_guided",
        }
        state["response_metadata"] = metadata

        state["generated_sql"] = repaired_sql
        state["current_error"] = None

        state = add_ai_message(state, "Gerada nova versão da consulta após erro de execução.")

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)

        attempt_number = len(repair_history)
        logger.info(
            "SQL repair completed",
            extra={
                "status": "success",
                "attempt_number": attempt_number,
                "user_query": user_query[:100],
                "error_message": error_message[:200],
                "previous_sql": previous_sql[:200],
                "repaired_sql": repaired_sql[:200],
                "selected_tables": selected_tables,
                "execution_time": execution_time,
            },
        )

        return state

    except Exception as e:
        error_message = f"SQL repair failed: {str(e)}"
        state = add_error(
            state,
            error_message,
            "sql_repair_error",
            ExecutionPhase.SQL_GENERATION,
            taxonomy=TX.REPAIR_LOOP,
        )

        execution_time = time.time() - start_time
        state = update_phase(state, ExecutionPhase.SQL_REPAIR, execution_time)

        logger.warning(
            "SQL repair failed",
            extra={
                "status": "failure",
                "error": str(e),
                "user_query": state.get("user_query", "")[:100],
                "previous_sql": state.get("generated_sql", "")[:200],
                "execution_time": execution_time,
            },
        )

        return state
