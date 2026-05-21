"""Pre-SQL chart planning for explicit visualization requests."""

from __future__ import annotations

import re
import unicodedata

from .schema import (
    ChartFilter,
    ChartPlan,
    ChartTimeWindow,
    ExpectedResultShape,
    VisualizationIntent,
)


def build_chart_plan(
    user_query: str,
    intent: VisualizationIntent,
    semantic_plan: dict | None = None,
) -> ChartPlan:
    """Extract structured chart parameters before SQL generation.

    The plan is a contract, not rendering code. SQL generation should satisfy
    its result shape so the deterministic chart renderer does not need to guess.
    """

    if not intent.requested:
        return ChartPlan(requested=False, reason="visualization not requested")

    normalized = _normalize(user_query)
    metric = _infer_metric(normalized)
    x_dimension = _infer_x_dimension(normalized)
    series_dimension = _infer_series_dimension(normalized)
    time_window = _infer_time_window(normalized)
    chart_type = _infer_chart_type(
        intent, x_dimension=x_dimension, series_dimension=series_dimension
    )
    if chart_type == "scatter":
        scatter_axes = _infer_scatter_axes(normalized)
        if scatter_axes:
            x_dimension, y_column = scatter_axes
            metric = y_column
            series_dimension = None
        else:
            y_column = _default_y_column(metric)
    else:
        y_column = _default_y_column(metric)
    expected_shape = _infer_expected_shape(
        x_dimension=x_dimension,
        series_dimension=series_dimension,
        chart_type=chart_type,
    )
    required_columns = _required_columns(x_dimension, series_dimension, y_column, expected_shape)

    return ChartPlan(
        requested=True,
        chart_type=chart_type,
        metric=metric,
        metric_expression=_metric_expression(metric),
        x_dimension=x_dimension,
        series_dimension=series_dimension,
        y_column=y_column,
        grain=_infer_grain(x_dimension, series_dimension),
        expected_result_shape=expected_shape,
        filters=_infer_filters(normalized),
        time_window=time_window,
        required_columns=required_columns,
        sql_shape_guidance=_shape_guidance(
            x_dimension=x_dimension,
            series_dimension=series_dimension,
            y_column=y_column,
            time_window=time_window,
            expected_shape=expected_shape,
        ),
        reason="structured chart parameters extracted before SQL generation",
    )


def validate_sql_against_chart_plan(
    chart_plan: ChartPlan | dict | None,
    sql: str,
) -> tuple[bool, str | None]:
    """Validate that SQL can satisfy the requested chart contract."""

    if not chart_plan or not sql:
        return True, None
    plan = chart_plan if isinstance(chart_plan, ChartPlan) else ChartPlan.model_validate(chart_plan)
    if not plan.requested:
        return True, None

    text = re.sub(r"\s+", " ", sql).strip().lower()
    if plan.time_window.type == "last_n_available_years":
        if "current_date" in text or "now()" in text:
            return False, (
                "CHART PLAN ERROR: last_n_available_years charts must use the latest year "
                "available in the data, not CURRENT_DATE/NOW()."
            )
        if re.search(r"max\s*\(\s*extract\s*\(\s*year[\s\S]{0,160}interval\s+'?\d+\s+years?", text):
            return False, (
                "CHART PLAN ERROR: last_n_available_years charts must subtract integer years "
                "from the numeric max year, not subtract an INTERVAL from MAX(EXTRACT(YEAR ...))."
            )
        if re.search(
            r"\b(?:where|and|or)\s+\(?\s*(?:\w+\.)?\"?dt_inter\"?\s*>=\s*"
            r"\(\s*select\s+max\s*\(\s*extract\s*\(\s*year",
            text,
        ):
            return False, (
                "CHART PLAN ERROR: last_n_available_years charts must compare extracted years "
                "to MAX(EXTRACT(YEAR FROM DT_INTER)), not compare DT_INTER dates directly to "
                "a numeric year."
            )
        if "dt_inter" not in text or "max(" not in text:
            return False, (
                "CHART PLAN ERROR: last_n_available_years charts must anchor the window on "
                "MAX(EXTRACT(YEAR FROM DT_INTER)) from the data."
            )

    missing_columns = [
        column
        for column in plan.required_columns
        if column and not _sql_outputs_column(text, column)
    ]
    if missing_columns:
        return False, (
            "CHART PLAN ERROR: SQL does not output chart required columns: "
            f"{', '.join(missing_columns)}."
        )

    if plan.metric == "receita_total":
        if not _sql_uses_table(text, "internacoes") or not _sql_sums_val_tot(text):
            return False, (
                "CHART PLAN ERROR: receita_total charts must aggregate "
                "internacoes.VAL_TOT with SUM and use internacoes as the fact table, "
                "not socioeconomico."
            )

    if plan.series_dimension == "sexo" or plan.x_dimension == "sexo":
        has_labels = bool(
            re.search(
                r"\bcase\s+when[\s\S]{0,240}(masculino|homens?|hom)[\s\S]{0,240}(feminino|mulheres?|mul)",
                text,
                re.I,
            )
            or re.search(r"\bjoin\s+sexo\b[\s\S]{0,240}\bdescri[cç][aã]o\b", text, re.I)
            or (
                re.search(r"\bas\s+\"?[a-z_]*(masculino|homens?)\"?\b", text, re.I)
                and re.search(r"\bas\s+\"?[a-z_]*(feminino|mulheres?)\"?\b", text, re.I)
            )
        )
        if not has_labels:
            return False, (
                "CHART PLAN ERROR: sexo series must output human-readable labels "
                "via CASE WHEN \"SEXO\"=1 THEN 'Masculino' WHEN \"SEXO\"=3 THEN 'Feminino' "
                "(or pivot aliases AS homens/mulheres), not raw SEXO codes."
            )

    if plan.x_dimension and _requires_unfilled_category_exclusion(plan):
        if not _sql_excludes_unfilled_category(text):
            return False, (
                "CHART PLAN ERROR: clinical category charts must exclude unfilled labels "
                "such as 'Nao preenchido', 'Nao informado', empty strings, and NULL values "
                "before ORDER BY/LIMIT."
            )

    return True, None


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _infer_metric(normalized_query: str) -> str:
    if any(
        token in normalized_query for token in ["taxa de mortalidade", "mortalidade hospitalar"]
    ):
        return "taxa_mortalidade"
    if any(
        token in normalized_query
        for token in [
            "receita",
            "faturamento",
            "valor total",
            "custo",
            "custos",
            "revenue",
            "cost",
        ]
    ):
        return "receita_total"
    if any(
        token in normalized_query
        for token in ["idade media", "idade média", "media de idade", "média de idade"]
    ):
        return "idade_media"
    if any(
        token in normalized_query
        for token in [
            "media de permanencia",
            "média de permanência",
            "permanencia media",
            "permanência média",
            "dias de permanencia",
            "dias de permanência",
        ]
    ):
        return "media_dias_permanencia"
    if any(
        token in normalized_query
        for token in ["morte", "mortes", "obito", "obitos", "death", "deaths"]
    ):
        return "total_mortes"
    if any(
        token in normalized_query
        for token in [
            "internacao",
            "internacoes",
            "paciente",
            "pacientes",
            "procedimento",
            "procedimentos",
            "admission",
            "admissions",
        ]
    ):
        return "total_internacoes"
    return "requested_metric"


def _infer_x_dimension(normalized_query: str) -> str | None:
    if _is_temporal_query(normalized_query):
        return "ano"
    if any(token in normalized_query for token in ["por mes", "mensal", "mensais", "monthly"]):
        return "mes"
    if any(token in normalized_query for token in ["por nacionalidade", "nacionalidade"]):
        return "nacionalidade"
    if any(
        token in normalized_query
        for token in ["por municipio", "por cidade", "municipio", "municipios", "cidade", "cidades"]
    ):
        return "municipio"
    if any(
        token in normalized_query
        for token in ["por estado", "por uf", "estados", "estado", "ufs", "uf", "by state"]
    ):
        return "estado"
    if "regiao de saude" in normalized_query or "regioes de saude" in normalized_query:
        return "regiao_saude"
    if any(
        token in normalized_query
        for token in ["raca cor", "raca/cor", "raça cor", "raça/cor", "por raca", "por raça", "por cor"]
    ):
        return "raca_cor"
    if any(
        token in normalized_query
        for token in [
            "por especialidade",
            "especialidade medica",
            "especialidade médica",
            "especialidades",
        ]
    ):
        return "especialidade"
    if any(token in normalized_query for token in ["por procedimento", "procedimentos"]):
        return "procedimento"
    if any(
        token in normalized_query
        for token in [
            "capitulo cid",
            "capitulos cid",
            "grupo cid",
            "grupos cid",
            "categoria cid",
            "categorias cid",
        ]
    ):
        return "cid_capitulo"
    if any(
        token in normalized_query
        for token in [
            "diagnostico principal",
            "diagnosticos principais",
            "diagnosticos",
            "diagnostico",
            "cids",
            "cid",
        ]
    ):
        return "diagnostico"
    if any(token in normalized_query for token in ["por hospital", "hospitais"]):
        return "hospital"
    if any(
        token in normalized_query
        for token in ["por faixa etaria", "por faixa etária", "faixa etaria", "faixa etária"]
    ):
        return "faixa_etaria"
    if any(token in normalized_query for token in ["causa de morte", "causas de morte"]):
        return "causa_morte"
    if "por sexo" in normalized_query or _mentions_both_sexes(normalized_query):
        return "sexo"
    if any(token in normalized_query for token in ["por idade", "idade"]):
        return "idade"
    return None


def _infer_scatter_axes(normalized_query: str) -> tuple[str, str] | None:
    metric_patterns = [
        ("receita_total", ["receita", "faturamento", "valor total", "custo", "cost", "revenue"]),
        ("taxa_mortalidade", ["taxa de mortalidade", "mortalidade hospitalar"]),
        ("idade_media", ["idade media", "idade média", "media de idade", "média de idade"]),
        (
            "media_dias_permanencia",
            [
                "media de permanencia",
                "média de permanência",
                "dias de permanencia",
                "dias de permanência",
                "media de dias",
            ],
        ),
        ("total_mortes", ["total de mortes", "mortes", "death", "deaths"]),
        ("total_internacoes", ["total de internacoes", "internacoes", "admissions"]),
    ]
    matches: list[tuple[int, str]] = []
    for metric, patterns in metric_patterns:
        positions = [
            normalized_query.find(pattern)
            for pattern in patterns
            if normalized_query.find(pattern) >= 0
        ]
        if positions:
            matches.append((min(positions), metric))
    ordered = []
    for _, metric in sorted(matches):
        if metric not in ordered:
            ordered.append(metric)
    if len(ordered) >= 2:
        return ordered[0], ordered[1]
    return None


def _infer_series_dimension(normalized_query: str) -> str | None:
    is_temporal = _is_temporal_query(normalized_query)
    if is_temporal and _mentions_both_sexes(normalized_query):
        return "sexo"
    if "por estado" in normalized_query and is_temporal:
        return "estado"
    return None


def _infer_time_window(normalized_query: str) -> ChartTimeWindow:
    recent_years = _recent_year_window(normalized_query)
    if recent_years is not None:
        return ChartTimeWindow(
            type="last_n_available_years", n=recent_years, date_column="DT_INTER"
        )

    year_range = re.search(
        r"\b((?:19|20)\d{2})\s*(?:-|a|ate|até)\s*((?:19|20)\d{2})\b", normalized_query
    )
    if year_range:
        return ChartTimeWindow(
            type="year_range",
            start_year=int(year_range.group(1)),
            end_year=int(year_range.group(2)),
            date_column="DT_INTER",
        )
    return ChartTimeWindow(type="none")


def _infer_chart_type(
    intent: VisualizationIntent,
    *,
    x_dimension: str | None,
    series_dimension: str | None,
) -> str:
    if intent.chart_hint != "auto":
        return intent.chart_hint
    if x_dimension in {"ano", "mes"}:
        return "line"
    if series_dimension or x_dimension:
        return "bar"
    return "kpi"


def _infer_expected_shape(
    *,
    x_dimension: str | None,
    series_dimension: str | None,
    chart_type: str,
) -> ExpectedResultShape:
    if chart_type == "kpi":
        return "single_metric"
    if x_dimension in {"ano", "mes"} and series_dimension:
        return "time_series_metric"
    if x_dimension in {"ano", "mes"}:
        return "time_metric"
    if x_dimension:
        return "category_metric"
    return "unknown"


def _infer_filters(normalized_query: str) -> list[ChartFilter]:
    filters: list[ChartFilter] = []
    if any(token in normalized_query for token in ["morte", "mortes", "obito", "obitos"]):
        filters.append(
            ChartFilter(
                field="MORTE",
                operator="=",
                values=[True],
                semantic="death outcome",
            )
        )
    if _mentions_both_sexes(normalized_query):
        filters.append(
            ChartFilter(
                field="SEXO",
                operator="IN",
                values=[1, 3],
                semantic="1=homens, 3=mulheres",
            )
        )
    return filters


def _required_columns(
    x_dimension: str | None,
    series_dimension: str | None,
    y_column: str,
    expected_shape: ExpectedResultShape,
) -> list[str]:
    if (
        expected_shape in {"time_series_metric", "category_metric"}
        and x_dimension
        and series_dimension
    ):
        return [x_dimension, series_dimension, y_column]
    if expected_shape == "time_metric" and x_dimension:
        return [x_dimension, y_column]
    if expected_shape == "single_metric":
        return [y_column]
    return [column for column in [x_dimension, series_dimension, y_column] if column]


def _shape_guidance(
    *,
    x_dimension: str | None,
    series_dimension: str | None,
    y_column: str,
    time_window: ChartTimeWindow,
    expected_shape: ExpectedResultShape,
) -> str:
    sex_label_hint = (
        " For 'sexo', emit human-readable labels via "
        "CASE WHEN \"SEXO\"=1 THEN 'Masculino' WHEN \"SEXO\"=3 THEN 'Feminino' END, "
        "not raw codes."
    )
    window_hint = _window_shape_hint(time_window)
    if (
        expected_shape == "time_series_metric"
        and x_dimension == "ano"
        and series_dimension == "sexo"
    ):
        return (
            f"Return tidy long rows with columns: ano, sexo, {y_column}. "
            "Group by ano and sexo so each year has one row per sex."
            f"{sex_label_hint}{window_hint}"
        )
    if expected_shape == "time_series_metric" and x_dimension and series_dimension:
        sex_hint = sex_label_hint if series_dimension == "sexo" or x_dimension == "sexo" else ""
        return (
            f"Return tidy long rows with columns: {x_dimension}, {series_dimension}, {y_column}. "
            f"Group by {x_dimension} and {series_dimension}.{sex_hint}{window_hint}"
        )
    if expected_shape == "time_metric" and x_dimension:
        return f"Return one row per {x_dimension} with columns: {x_dimension}, {y_column}.{window_hint}"
    if expected_shape == "category_metric" and x_dimension:
        sex_hint = sex_label_hint if x_dimension == "sexo" else ""
        missing_hint = _clinical_missing_shape_hint(x_dimension)
        return (
            f"Return one row per {x_dimension} with columns: {x_dimension}, {y_column}."
            f"{sex_hint}{missing_hint}"
        )
    if expected_shape == "single_metric":
        return f"Return a single scalar row with column: {y_column}."
    return "Return only the columns required by the chart."


def _window_shape_hint(time_window: ChartTimeWindow) -> str:
    if time_window.type == "last_n_available_years" and time_window.n:
        return (
            f" For the time window: take the last {time_window.n} available years anchored on "
            "MAX(EXTRACT(YEAR FROM DT_INTER)) from internacoes, then keep all years where "
            f"EXTRACT(YEAR FROM DT_INTER) >= MAX_YEAR - {time_window.n - 1}. "
            "Do not collapse to a single year and do not use CURRENT_DATE/NOW()."
        )
    if time_window.type == "year_range" and time_window.start_year and time_window.end_year:
        return (
            f" For the time window: keep years where EXTRACT(YEAR FROM DT_INTER) "
            f"BETWEEN {time_window.start_year} AND {time_window.end_year}."
        )
    return ""


def _clinical_missing_shape_hint(x_dimension: str | None) -> str:
    if x_dimension and any(
        token in x_dimension.lower()
        for token in ["causa", "diagnostico", "doenca", "cid", "motivo"]
    ):
        return (
            " Exclude missing/unfilled clinical categories such as 'Nao preenchido', "
            "'Nao informado', empty strings, and NULL values from the chart result."
        )
    return ""


def _requires_unfilled_category_exclusion(plan: ChartPlan) -> bool:
    return plan.chart_type in {"bar", "pie", "donut"} and any(
        token in plan.x_dimension.lower()
        for token in ["causa", "diagnostico", "doenca", "cid", "motivo"]
    )


def _sql_excludes_unfilled_category(sql_text: str) -> bool:
    has_unfilled_label_filter = bool(
        re.search(r"(<>|!=|not\s+in|not\s+like)[\s\S]{0,80}na[oã]\s+preench", sql_text, re.I)
        or re.search(r"na[oã]\s+preench[\s\S]{0,80}(<>|!=|not\s+in|not\s+like)", sql_text, re.I)
    )
    has_empty_string_filter = bool(re.search(r"(<>|!=)\s*''|nullif\s*\(|trim\s*\(", sql_text, re.I))
    has_null_filter = " is not null" in sql_text
    return has_unfilled_label_filter and (has_null_filter or has_empty_string_filter)


def _default_y_column(metric: str) -> str:
    return {
        "total_mortes": "total_mortes",
        "total_internacoes": "total_internacoes",
        "taxa_mortalidade": "taxa_mortalidade",
        "idade_media": "idade_media",
        "media_dias_permanencia": "media_dias_permanencia",
        "receita_total": "receita_total",
    }.get(metric, "valor")


def _metric_expression(metric: str) -> str | None:
    return {
        "total_mortes": 'COUNT rows where "MORTE" = true',
        "total_internacoes": "COUNT rows",
        "taxa_mortalidade": "SUM(MORTE=true) * 100.0 / COUNT(*)",
        "idade_media": 'AVG("IDADE")',
        "media_dias_permanencia": 'AVG("DIAS_PERM")',
        "receita_total": 'SUM("VAL_TOT")',
    }.get(metric)


def _infer_grain(x_dimension: str | None, series_dimension: str | None) -> str:
    dimensions = [dimension for dimension in [x_dimension, series_dimension] if dimension]
    return "_".join(dimensions) if dimensions else "single_metric"


def _recent_year_window(normalized_query: str) -> int | None:
    match = re.search(r"\b(?:ultimos|ultimas)\s+(\d+)\s+anos\b", normalized_query)
    return int(match.group(1)) if match else None


def _is_temporal_query(normalized_query: str) -> bool:
    return bool(_recent_year_window(normalized_query)) or any(
        token in normalized_query
        for token in [
            "por ano",
            "por anos",
            "ano a ano",
            "ao longo dos anos",
            "ao longo do tempo",
            "evolucao",
            "evolução",
            "serie temporal",
            "linha temporal",
            "temporal",
        ]
    )


def _mentions_both_sexes(normalized_query: str) -> bool:
    return _mentions_male(normalized_query) and _mentions_female(normalized_query)


def _mentions_male(normalized_query: str) -> bool:
    return bool(re.search(r"\b(homens?|masculin[oa]s?)\b", normalized_query))


def _mentions_female(normalized_query: str) -> bool:
    return bool(re.search(r"\b(mulheres?|ulheres?|feminin[oa]s?)\b", normalized_query))


def _sql_outputs_column(sql_lower: str, column: str) -> bool:
    normalized_column = column.lower()
    patterns = [
        rf"\bas\s+\"?{re.escape(normalized_column)}\"?\b",
        rf"\b\"?{re.escape(normalized_column)}\"?\s*,",
        rf"\b\"?{re.escape(normalized_column)}\"?\s+from\b",
    ]
    return any(re.search(pattern, sql_lower, re.I) for pattern in patterns)


def _sql_uses_table(sql_lower: str, table: str) -> bool:
    return bool(re.search(rf"\b(?:from|join)\s+\"?{re.escape(table.lower())}\"?\b", sql_lower))


def _sql_sums_val_tot(sql_lower: str) -> bool:
    return bool(re.search(r'\bsum\s*\(\s*(?:[a-z_][\w]*\.)?"?val_tot"?\s*\)', sql_lower))
