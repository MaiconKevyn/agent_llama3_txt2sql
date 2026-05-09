"""Conservative semantic planner for broad Text-to-SQL intent contracts.

This module intentionally avoids benchmark-specific rules. It extracts reusable
semantic patterns such as rates, rankings, per-group top-N, temporal series,
absence conditions, and null-bucket requirements.
"""

from __future__ import annotations

import re

from .plan_schema import (
    AnswerShape,
    SemanticDimension,
    SemanticFilter,
    SemanticMetric,
    SemanticPlan,
)
from .profile_store import SemanticProfileStore

_UF_RE = re.compile(
    r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b",
    re.I,
)

_STATE_NAME_TO_UF = {
    "acre": "AC",
    "alagoas": "AL",
    "amapá": "AP",
    "amapa": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceará": "CE",
    "ceara": "CE",
    "distrito federal": "DF",
    "espírito santo": "ES",
    "espirito santo": "ES",
    "goiás": "GO",
    "goias": "GO",
    "maranhão": "MA",
    "maranhao": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "pará": "PA",
    "paraíba": "PB",
    "paraiba": "PB",
    "paraná": "PR",
    "parana": "PR",
    "pernambuco": "PE",
    "piauí": "PI",
    "piaui": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondônia": "RO",
    "rondonia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "são paulo": "SP",
    "sao paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}


def _extract_top_n(query_lower: str) -> int | None:
    patterns = [
        r"\btop\s*-?\s*(\d+)\b",
        r"\b(\d+)\s+(?:principais|maiores|menores|mais\s+comuns|mais\s+frequentes)\b",
        r"\b(?:os|as)?\s*(\d+)\s+(?:munic[ií]pios|cidades|hospitais|procedimentos|diagn[oó]sticos)\b",
        r"\b(?:os|as)\s+(\d+)\s+\w+\s+(?:com|de|mais|maior|menor)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    if re.search(r"\b(?:maior|menor|principal|mais\s+comum|mais\s+frequente)\b", query_lower):
        return 1
    return None


def _dimension(name: str, source: str, role: str = "group") -> SemanticDimension:
    return SemanticDimension(name=name, source=source, role=role)


def _contains_any(query_lower: str, tokens: list[str]) -> bool:
    for token in tokens:
        if " " in token:
            if token in query_lower:
                return True
        elif re.search(rf"(?<!\w){re.escape(token)}(?!\w)", query_lower):
            return True
    return False


def _has_hospital_location_context(query_lower: str) -> bool:
    return _contains_any(
        query_lower,
        [
            "atende",
            "atendem",
            "atendimento",
            "atendimentos",
            "recebe",
            "recebem",
            "localização do hospital",
            "localizacao do hospital",
            "cidade do hospital",
            "município do hospital",
            "municipio do hospital",
            "onde ficam hospitais",
            "onde estão os hospitais",
            "onde estao os hospitais",
        ],
    )


def _has_group_phrase(query_lower: str, dimension: str) -> bool:
    dimension_terms = {
        "estado": ["estado", "uf"],
        "municipio": ["município", "municipio", "cidade"],
        "municipio_hospital": [
            "município",
            "municipio",
            "cidade",
            "município de atendimento",
            "municipio de atendimento",
        ],
        "estado_hospital": ["estado", "uf", "estado de atendimento", "estado do hospital"],
        "hospital": ["hospital"],
        "especialidade": ["especialidade"],
        "diagnostico": ["diagnóstico", "diagnostico", "cid", "doença", "doenca"],
        "procedimento": ["procedimento"],
        "sexo": ["sexo"],
        "raca_cor": ["raça", "raca", "cor"],
        "instrucao": [
            "instrução",
            "instrucao",
            "escolaridade",
            "nível de instrução",
            "nivel de instrucao",
            "grau de instrução",
            "grau de instrucao",
        ],
        "faixa_etaria": ["idade", "faixa etária", "faixa etaria"],
        "ano": ["ano"],
        "mes": ["mês", "mes"],
        "trimestre": ["trimestre"],
    }
    prefixes = ["por", "por cada", "para cada", "em cada", "de cada"]
    for term in dimension_terms.get(dimension, []):
        for prefix in prefixes:
            if f"{prefix} {term}" in query_lower:
                return True
    return False


def _is_entity_list_question(query_lower: str, dimension: str) -> bool:
    entity_patterns = {
        "estado": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?estados\b",
        "municipio": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?munic[ií]pios\b",
        "municipio_hospital": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?munic[ií]pios\b",
        "hospital": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?hospitais\b",
        "especialidade": r"\bquais\s+(?:são\s+)?(?:as\s+)?especialidades\b",
        "diagnostico": r"\bquais\s+(?:são\s+)?(?:os\s+|as\s+)?(?:diagn[oó]sticos|cids|doenças|doencas)\b",
        "procedimento": r"\bquais\s+(?:são\s+)?(?:os\s+)?procedimentos\b",
    }
    pattern = entity_patterns.get(dimension)
    return bool(pattern and re.search(pattern, query_lower, re.I))


def _filter_output_dimensions(
    dimensions: list[SemanticDimension],
    query_lower: str,
    *,
    top_n: int | None,
    has_temporal_trend: bool,
    has_distribution: bool,
    has_delta: bool,
) -> list[SemanticDimension]:
    """Keep only dimensions that define output grain, not scalar filters."""
    result: list[SemanticDimension] = []
    for dim in dimensions:
        if dim.name == "ano":
            keep = has_temporal_trend or has_delta or _has_group_phrase(query_lower, dim.name)
        elif dim.name in {"mes", "trimestre"}:
            keep = _has_group_phrase(query_lower, dim.name)
        elif dim.name in {"sexo", "faixa_etaria", "raca_cor", "instrucao"}:
            keep = has_distribution or _has_group_phrase(query_lower, dim.name)
        else:
            keep = (
                has_distribution
                or _has_group_phrase(query_lower, dim.name)
                or _is_entity_list_question(query_lower, dim.name)
                or bool(top_n)
            )
        if keep:
            result.append(dim)
    return result


def _infer_dimensions(query_lower: str) -> list[SemanticDimension]:
    dims: list[SemanticDimension] = []
    hospital_location_context = _has_hospital_location_context(query_lower) or _contains_any(
        query_lower,
        ["hospital", "hospitais", "cnes"],
    )
    checks = [
        (
            "estado_hospital" if hospital_location_context else "estado",
            "municipios.estado",
            ["estado", "uf"],
        ),
        (
            "municipio_hospital" if hospital_location_context else "municipio",
            "municipios.nome",
            ["município", "municipio", "municípios", "municipios", "cidade", "cidades"],
        ),
        ("hospital", "internacoes.CNES", ["hospital", "hospitais", "cnes"]),
        ("especialidade", "especialidade.DESCRICAO", ["especialidade"]),
        (
            "diagnostico",
            "cid.CD_DESCRICAO",
            ["diagnóstico", "diagnostico", "cid", "doença", "doenca"],
        ),
        ("procedimento", "procedimentos.NOME_PROC", ["procedimento", "procedimentos"]),
        ("sexo", "internacoes.SEXO", ["sexo", "homens", "mulheres", "masculino", "feminino"]),
        ("raca_cor", "internacoes.RACA_COR", ["raça", "raca", "cor"]),
        (
            "instrucao",
            "instrucao.DESCRICAO",
            [
                "instrução",
                "instrucao",
                "escolaridade",
                "nível de instrução",
                "nivel de instrucao",
                "grau de instrução",
                "grau de instrucao",
            ],
        ),
        ("faixa_etaria", "internacoes.IDADE", ["faixa etária", "faixa etaria", "idade"]),
        (
            "ano",
            "EXTRACT(YEAR FROM internacoes.DT_INTER)",
            ["ano", "anual", "evolução", "evolucao"],
        ),
        ("mes", "EXTRACT(MONTH FROM internacoes.DT_INTER)", ["mês", "mes", "mensal"]),
        (
            "trimestre",
            "EXTRACT(QUARTER FROM internacoes.DT_INTER)",
            ["trimestre", "trimestral"],
        ),
    ]
    for name, source, tokens in checks:
        if _contains_any(query_lower, tokens):
            dims.append(_dimension(name, source))
    return dims


def _infer_metrics(query_lower: str) -> list[SemanticMetric]:
    metrics: list[SemanticMetric] = []

    if "mortalidade infantil" in query_lower:
        metrics.append(
            SemanticMetric(
                name="mortalidade_infantil_1ano",
                expression_type="avg",
                required_filters=["metrica = 'mortalidade_infantil_1ano'"],
            )
        )
    elif any(token in query_lower for token in ["taxa de mortalidade", "mortalidade hospitalar"]):
        metrics.append(
            SemanticMetric(
                name="taxa_mortalidade",
                expression_type="rate",
                numerator_condition="MORTE = true",
                denominator_scope="all_rows_matching_non_outcome_filters",
            )
        )
    elif any(token in query_lower for token in ["taxa", "percentual", "proporção", "proporcao"]):
        metrics.append(
            SemanticMetric(
                name="proporcao",
                expression_type="rate",
                denominator_scope="all_rows_matching_scope_filters",
            )
        )

    if "mortalidade infantil" not in query_lower and any(
        token in query_lower
        for token in ["custo médio", "custo medio", "valor médio", "valor medio", "média", "media"]
    ):
        metric_name = "custo_medio_uti" if "uti" in query_lower else "media"
        required = ["VAL_UTI > 0"] if "uti" in query_lower else []
        metrics.append(
            SemanticMetric(name=metric_name, expression_type="avg", required_filters=required)
        )

    if any(
        token in query_lower
        for token in ["total", "quantos", "quantas", "número de", "numero de", "quantidade"]
    ) or any(
        token in query_lower
        for token in ["pacientes", "internacoes", "internaçoes", "internações"]
    ):
        metrics.append(SemanticMetric(name="total", expression_type="count"))

    if any(
        token in query_lower for token in ["crescimento", "queda", "variação", "variacao", "delta"]
    ):
        metrics.append(SemanticMetric(name="delta_temporal", expression_type="delta"))

    if not metrics:
        metrics.append(SemanticMetric(name="requested_metric", expression_type="unknown"))

    return metrics


def _infer_filters(query: str, query_lower: str) -> list[SemanticFilter]:
    filters: list[SemanticFilter] = []
    ufs = sorted({m.group(1).upper() for m in _UF_RE.finditer(query)})
    for state_name, uf in sorted(
        _STATE_NAME_TO_UF.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.search(rf"(?<!\w){re.escape(state_name)}(?!\w)", query_lower, re.I):
            ufs.append(uf)
    ufs = sorted(set(ufs))
    if ufs:
        filters.append(
            SemanticFilter(field="estado", values=ufs, operator="IN" if len(ufs) > 1 else "=")
        )

    years = sorted({m.group(0) for m in re.finditer(r"\b(?:19|20)\d{2}\b", query)})
    if years:
        filters.append(
            SemanticFilter(field="ano", values=years, operator="IN" if len(years) > 1 else "=")
        )

    if "uti" in query_lower:
        filters.append(SemanticFilter(field="uti", values=["VAL_UTI > 0"], operator="semantic"))
    if _contains_any(query_lower, ["homens", "masculino"]):
        filters.append(SemanticFilter(field="sexo", values=["1"], operator="="))
    if _contains_any(query_lower, ["mulheres", "feminino"]):
        filters.append(SemanticFilter(field="sexo", values=["3"], operator="="))
    if "mortalidade infantil" in query_lower:
        filters.append(
            SemanticFilter(
                field="metrica",
                values=["mortalidade_infantil_1ano"],
                operator="=",
            )
        )
    asks_rate = any(
        token in query_lower for token in ["taxa", "percentual", "proporção", "proporcao"]
    )
    if (
        any(token in query_lower for token in ["óbito", "obito", "morte", "mortes"])
        and not asks_rate
    ):
        filters.append(
            SemanticFilter(field="desfecho", values=["MORTE = true"], operator="semantic")
        )

    return filters


def build_semantic_plan(
    user_query: str,
    profile_store: SemanticProfileStore | None = None,
) -> SemanticPlan:
    """Build a generic semantic contract for a user question."""
    query = user_query or ""
    q = query.lower()

    top_n = _extract_top_n(q)
    raw_dimensions = _infer_dimensions(q)
    metrics = _infer_metrics(q)
    filters = _infer_filters(query, q)
    metric_names = {metric.name for metric in metrics}

    has_temporal_trend = any(
        token in q
        for token in [
            "evolução",
            "evolucao",
            "série temporal",
            "serie temporal",
            "ao longo",
            "anual",
        ]
    )
    has_distribution = any(
        token in q for token in ["distribuição", "distribuicao", "como se distribui"]
    )
    has_unknown_bucket = any(
        token in q
        for token in [
            "sem informação",
            "sem informacao",
            "não informado",
            "nao informado",
            "incluindo os casos sem",
        ]
    )
    has_absence = any(
        token in q
        for token in ["nunca", "nenhum", "nenhuma", "sem registro", "não tiveram", "nao tiveram"]
    ) or ("sem " in q and not has_unknown_bucket)
    has_rate = any(metric.expression_type == "rate" for metric in metrics)
    has_delta = any(metric.expression_type == "delta" for metric in metrics)
    dimensions = _filter_output_dimensions(
        raw_dimensions,
        q,
        top_n=top_n,
        has_temporal_trend=has_temporal_trend,
        has_distribution=has_distribution,
        has_delta=has_delta,
    )

    per_group_tokens = [
        "por estado",
        "em cada estado",
        "de cada estado",
        "por município",
        "por municipio",
        "em cada município",
        "em cada municipio",
        "por hospital",
        "em cada hospital",
        "por especialidade",
        "em cada especialidade",
        "por ano",
        "em cada ano",
        "por sexo",
        "para cada sexo",
        "em cada sexo",
        "cada sexo",
        "por faixa",
        "para cada faixa",
        "em cada faixa",
        "por grupo",
        "para cada grupo",
        "em cada grupo",
    ]
    top_n_scope = (
        "per_group"
        if top_n and any(token in q for token in per_group_tokens)
        else ("global" if top_n else "none")
    )

    if has_temporal_trend or has_delta:
        intent = "trend"
    elif top_n:
        intent = "ranking"
    elif has_distribution:
        intent = "distribution"
    elif has_rate:
        intent = "rate"
    elif any(token in q for token in ["quantos", "quantas", "número de", "numero de", "total de"]):
        intent = "count"
    else:
        intent = "unknown"

    required_dimensions = [
        dim.name
        for dim in dimensions
        if dim.name
        in {
            "estado",
            "estado_hospital",
            "municipio",
            "municipio_hospital",
            "hospital",
            "especialidade",
            "diagnostico",
            "procedimento",
            "sexo",
            "raca_cor",
            "instrucao",
            "faixa_etaria",
            "ano",
            "mes",
        }
    ]
    constraints: list[str] = []
    null_policy: list[str] = []

    if top_n_scope == "per_group":
        constraints.append("top_n_per_group_requires_window_partition")
    if has_rate:
        constraints.append("rate_denominator_must_preserve_full_scope")
    if any(dim.name in {"municipio_hospital", "estado_hospital"} for dim in dimensions):
        constraints.append("join_path_hospital_location_required")
    if "instrucao" in required_dimensions:
        constraints.append("domain_instrucao_valid_required")
        if not any(semantic_filter.field == "instrucao_valid" for semantic_filter in filters):
            filters.append(
                SemanticFilter(
                    field="instrucao_valid",
                    values=["INSTRU IS NOT NULL", "INSTRU != 0"],
                    operator="semantic",
                )
            )
    if "mortalidade_infantil_1ano" in metric_names:
        constraints.append("socioeconomico_metric_filter_required")
    if has_absence:
        constraints.append("absence_condition_requires_antijoin_or_aggregate_zero")
    if has_delta or "entre" in q and len([f for f in filters if f.field == "ano"]) >= 1:
        constraints.append("temporal_comparison_requires_separate_period_aggregates")
    if has_unknown_bucket:
        null_policy.append("include_unknown_bucket_with_left_join_or_coalesce")

    high_cardinality_average_rank = (
        top_n
        and top_n_scope == "per_group"
        and any(metric.expression_type in {"avg", "rate"} for metric in metrics)
        and any(dim in {"hospital", "municipio", "municipio_hospital"} for dim in required_dimensions)
    )
    if high_cardinality_average_rank:
        constraints.append("top_n_average_high_cardinality_requires_minimum_group_size")
        filters.append(
            SemanticFilter(field="minimum_group_count", values=["100"], operator=">")
        )

    if intent == "count" and not required_dimensions and not top_n:
        row_grain = "single_scalar"
    elif (
        not required_dimensions
        and not top_n
        and not has_temporal_trend
        and any(metric.expression_type != "unknown" for metric in metrics)
    ):
        row_grain = "single_scalar"
    elif top_n_scope == "per_group":
        row_grain = "top_n_per_group"
    elif top_n_scope == "global":
        row_grain = "top_n_global"
    elif has_temporal_trend:
        row_grain = "time_series"
    elif required_dimensions:
        row_grain = "one_row_per_group"
    else:
        row_grain = "unknown"

    answer_shape = AnswerShape(
        row_grain=row_grain,
        top_n=top_n,
        top_n_scope=top_n_scope,
        required_dimensions=required_dimensions,
        requires_group_by=bool(required_dimensions and row_grain != "single_scalar"),
        include_unknown_bucket=has_unknown_bucket,
    )

    base_grain = "internacao"
    if any(
        token in q
        for token in [
            "idhm",
            "mortalidade infantil",
            "bolsa família",
            "bolsa familia",
            "população",
            "populacao",
            "saneamento",
        ]
    ):
        base_grain = "municipio_ano_metrica"
    elif "procedimento" in q:
        base_grain = "procedimento_ocorrencia"

    plan = SemanticPlan(
        intent=intent,
        base_grain=base_grain,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        answer_shape=answer_shape,
        constraints=constraints,
        null_policy=null_policy,
    )
    if profile_store is not None:
        _enrich_plan_with_profile(plan, query, profile_store)
    return plan


_DIMENSION_PROFILE_COLUMNS = {
    "estado": ("municipios", "estado"),
    "hospital": ("internacoes", "CNES"),
    "procedimento": ("atendimentos", "PROC_REA"),
    "sexo": ("internacoes", "SEXO"),
    "raca_cor": ("internacoes", "RACA_COR"),
    "ano": ("internacoes", "DT_INTER"),
    "mes": ("internacoes", "DT_INTER"),
}


def _enrich_plan_with_profile(
    plan: SemanticPlan,
    user_query: str,
    profile_store: SemanticProfileStore,
) -> None:
    q = user_query.lower()

    if any(dim.name in {"ano", "mes"} for dim in plan.dimensions) or _contains_any(
        q, ["ano", "anual", "mensal", "mês", "mes", "evolução", "evolucao"]
    ):
        temporal_range = profile_store.temporal_range("internacoes", "DT_INTER")
        if temporal_range:
            min_value, max_value = temporal_range
            plan.ambiguities.append(
                f"profile_temporal_coverage: internacoes.DT_INTER ranges from {min_value} to {max_value}"
            )
            _append_temporal_filter_warnings(plan, min_value, max_value)

    for dim in plan.dimensions:
        column_ref = _DIMENSION_PROFILE_COLUMNS.get(dim.name)
        if not column_ref:
            continue
        table, column = column_ref
        column_profile = profile_store.get_column(table, column)
        if column_profile is None:
            continue
        if column_profile.kind == "identifier" or profile_store.high_cardinality(table, column):
            plan.ambiguities.append(
                f"profile_cardinality: {dim.name} uses high-cardinality identifier {table}.{column}"
            )
        null_rate = profile_store.null_rate(table, column)
        if null_rate and null_rate > 0:
            plan.ambiguities.append(
                f"profile_nulls: {table}.{column} has null_rate={null_rate:.3f}"
            )

    if plan.answer_shape.include_unknown_bucket and not plan.null_policy:
        plan.null_policy.append("include_unknown_bucket_with_left_join_or_coalesce")

    if "sexo" in plan.answer_shape.required_dimensions:
        _add_domain_hint(plan, profile_store, "internacoes", "SEXO")


def _append_temporal_filter_warnings(
    plan: SemanticPlan,
    min_value: str | None,
    max_value: str | None,
) -> None:
    if not min_value or not max_value:
        return
    min_year = _extract_year(min_value)
    max_year = _extract_year(max_value)
    if min_year is None or max_year is None:
        return
    for semantic_filter in plan.filters:
        if semantic_filter.field != "ano":
            continue
        for value in semantic_filter.values:
            try:
                year = int(value)
            except ValueError:
                continue
            if year < min_year or year > max_year:
                plan.ambiguities.append(
                    f"profile_temporal_filter_out_of_range: ano={year} outside {min_year}-{max_year}"
                )


def _add_domain_hint(
    plan: SemanticPlan,
    profile_store: SemanticProfileStore,
    table: str,
    column: str,
) -> None:
    profile = profile_store.get_column(table, column)
    if profile is None or not profile.top_values:
        return
    values = [str(item.get("value")) for item in profile.top_values[:5]]
    plan.ambiguities.append(f"profile_domain_values: {table}.{column} common_values={values}")


def _extract_year(value: str) -> int | None:
    match = re.search(r"\b(?:19|20)\d{2}\b", value)
    if not match:
        return None
    return int(match.group(0))
