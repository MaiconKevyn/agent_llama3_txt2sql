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


_UF_RE = re.compile(
    r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b",
    re.I,
)


def _extract_top_n(query_lower: str) -> int | None:
    patterns = [
        r"\btop\s*-?\s*(\d+)\b",
        r"\b(\d+)\s+(?:principais|maiores|menores|mais\s+comuns|mais\s+frequentes)\b",
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


def _infer_dimensions(query_lower: str) -> list[SemanticDimension]:
    dims: list[SemanticDimension] = []
    checks = [
        ("estado", "municipios.estado", ["estado", "uf"]),
        ("municipio", "municipios.nome", ["município", "municipio", "cidade"]),
        ("hospital", "internacoes.CNES", ["hospital", "hospitais", "cnes"]),
        ("especialidade", "especialidade.DESCRICAO", ["especialidade"]),
        ("diagnostico", "cid.CD_DESCRICAO", ["diagnóstico", "diagnostico", "cid", "doença", "doenca"]),
        ("procedimento", "procedimentos.NOME_PROC", ["procedimento"]),
        ("sexo", "internacoes.SEXO", ["sexo", "homens", "mulheres", "masculino", "feminino"]),
        ("raca_cor", "internacoes.RACA_COR", ["raça", "raca", "cor"]),
        ("instrucao", "internacoes.INSTRU", ["instrução", "instrucao", "escolaridade"]),
        ("faixa_etaria", "internacoes.IDADE", ["faixa etária", "faixa etaria", "idade"]),
        ("ano", "EXTRACT(YEAR FROM internacoes.DT_INTER)", ["ano", "anual", "evolução", "evolucao"]),
        ("mes", "EXTRACT(MONTH FROM internacoes.DT_INTER)", ["mês", "mes", "mensal"]),
    ]
    for name, source, tokens in checks:
        if _contains_any(query_lower, tokens):
            dims.append(_dimension(name, source))
    return dims


def _infer_metrics(query_lower: str) -> list[SemanticMetric]:
    metrics: list[SemanticMetric] = []

    if any(token in query_lower for token in ["taxa de mortalidade", "mortalidade hospitalar"]):
        metrics.append(
            SemanticMetric(
                name="taxa_mortalidade",
                expression_type="rate",
                numerator_condition='MORTE = true',
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

    if any(token in query_lower for token in ["custo médio", "custo medio", "valor médio", "valor medio", "média", "media"]):
        metric_name = "custo_medio_uti" if "uti" in query_lower else "media"
        required = ["VAL_UTI > 0"] if "uti" in query_lower else []
        metrics.append(SemanticMetric(name=metric_name, expression_type="avg", required_filters=required))

    if any(token in query_lower for token in ["total", "quantos", "quantas", "número de", "numero de", "quantidade"]):
        metrics.append(SemanticMetric(name="total", expression_type="count"))

    if any(token in query_lower for token in ["crescimento", "queda", "variação", "variacao", "delta"]):
        metrics.append(SemanticMetric(name="delta_temporal", expression_type="delta"))

    if not metrics:
        metrics.append(SemanticMetric(name="requested_metric", expression_type="unknown"))

    return metrics


def _infer_filters(query: str, query_lower: str) -> list[SemanticFilter]:
    filters: list[SemanticFilter] = []
    ufs = sorted({m.group(1).upper() for m in _UF_RE.finditer(query)})
    if ufs:
        filters.append(SemanticFilter(field="estado", values=ufs, operator="IN" if len(ufs) > 1 else "="))

    years = sorted({m.group(0) for m in re.finditer(r"\b(?:19|20)\d{2}\b", query)})
    if years:
        filters.append(SemanticFilter(field="ano", values=years, operator="IN" if len(years) > 1 else "="))

    if "uti" in query_lower:
        filters.append(SemanticFilter(field="uti", values=["VAL_UTI > 0"], operator="semantic"))
    asks_rate = any(token in query_lower for token in ["taxa", "percentual", "proporção", "proporcao"])
    if any(token in query_lower for token in ["óbito", "obito", "morte", "mortes"]) and not asks_rate:
        filters.append(SemanticFilter(field="desfecho", values=["MORTE = true"], operator="semantic"))

    return filters


def build_semantic_plan(user_query: str) -> SemanticPlan:
    """Build a generic semantic contract for a user question."""
    query = user_query or ""
    q = query.lower()

    top_n = _extract_top_n(q)
    dimensions = _infer_dimensions(q)
    metrics = _infer_metrics(q)
    filters = _infer_filters(query, q)

    has_temporal_trend = any(token in q for token in ["evolução", "evolucao", "série temporal", "serie temporal", "ao longo", "anual"])
    has_distribution = any(token in q for token in ["distribuição", "distribuicao", "como se distribui"])
    has_unknown_bucket = any(token in q for token in ["sem informação", "sem informacao", "não informado", "nao informado", "incluindo os casos sem"])
    has_absence = (
        any(token in q for token in ["nunca", "nenhum", "nenhuma", "sem registro", "não tiveram", "nao tiveram"])
        or ("sem " in q and not has_unknown_bucket)
    )
    has_rate = any(metric.expression_type == "rate" for metric in metrics)
    has_delta = any(metric.expression_type == "delta" for metric in metrics)

    per_group_tokens = [
        "por estado", "em cada estado", "de cada estado",
        "por município", "por municipio", "em cada município", "em cada municipio",
        "por hospital", "em cada hospital",
        "por especialidade", "em cada especialidade",
        "por ano", "em cada ano",
        "por sexo", "para cada sexo", "em cada sexo", "cada sexo",
        "por faixa", "para cada faixa", "em cada faixa",
        "por grupo", "para cada grupo", "em cada grupo",
    ]
    top_n_scope = "per_group" if top_n and any(token in q for token in per_group_tokens) else ("global" if top_n else "none")

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

    required_dimensions = [dim.name for dim in dimensions if dim.name in {
        "estado", "municipio", "hospital", "especialidade", "diagnostico",
        "procedimento", "sexo", "raca_cor", "instrucao", "faixa_etaria", "ano", "mes",
    }]
    constraints: list[str] = []
    null_policy: list[str] = []

    if top_n_scope == "per_group":
        constraints.append("top_n_per_group_requires_window_partition")
    if has_rate:
        constraints.append("rate_denominator_must_preserve_full_scope")
    if has_absence:
        constraints.append("absence_condition_requires_antijoin_or_aggregate_zero")
    if has_delta or "entre" in q and len([f for f in filters if f.field == "ano"]) >= 1:
        constraints.append("temporal_comparison_requires_separate_period_aggregates")
    if has_unknown_bucket:
        null_policy.append("include_unknown_bucket_with_left_join_or_coalesce")

    if intent == "count" and not required_dimensions and not top_n:
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
    if any(token in q for token in ["idhm", "bolsa família", "bolsa familia", "população", "populacao", "saneamento"]):
        base_grain = "municipio_ano_metrica"
    elif "procedimento" in q:
        base_grain = "procedimento_ocorrencia"

    return SemanticPlan(
        intent=intent,
        base_grain=base_grain,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        answer_shape=answer_shape,
        constraints=constraints,
        null_policy=null_policy,
    )
