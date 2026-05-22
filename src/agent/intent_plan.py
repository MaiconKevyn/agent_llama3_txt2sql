"""Structured user-intent contracts for agent planning.

This module is intentionally independent from SQL generation. It represents
what the user is asking for, then downstream resolvers and compilers decide how
to satisfy the request against the database.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.semantic.domain_resolvers import resolve_clinical_domain, resolve_population_group
from src.visualization.intent import detect_visualization_intent

PersonaHint = Literal["common_user", "clinician", "researcher", "manager", "auditor", "unknown"]
PrimaryTask = Literal[
    "direct_metric",
    "trend",
    "comparison",
    "ranking",
    "breakdown",
    "association",
    "data_quality",
    "chart",
    "out_of_scope",
]
Presentation = Literal["text", "table", "chart", "mixed"]
ToolName = Literal[
    "inspect_schema",
    "resolve_concepts",
    "resolve_temporal_scope",
    "resolve_join_policy",
    "compile_sql",
    "execute_sql",
    "validate_result_contract",
    "build_chart",
    "clarify_or_refuse",
]


class MetricSlot(BaseModel):
    name: str
    expression_type: str = "unknown"
    required_filters: list[str] = Field(default_factory=list)


class CohortSlot(BaseModel):
    name: str
    filters: list[dict[str, object]] = Field(default_factory=list)
    caveat: str | None = None


class ConceptSlot(BaseModel):
    name: str
    concept_type: Literal["clinical", "population", "geographic", "operational", "unknown"] = "unknown"
    filters: list[dict[str, object]] = Field(default_factory=list)


class TemporalScope(BaseModel):
    type: Literal["none", "last_n_available_years", "year", "year_range"] = "none"
    n: int | None = None
    start_year: int | None = None
    end_year: int | None = None
    date_column: str = "DT_INTER"


class GroupingSlot(BaseModel):
    name: str


class ToolRequest(BaseModel):
    name: ToolName
    reason: str


class IntentPlan(BaseModel):
    user_question: str
    persona_hint: PersonaHint = "unknown"
    primary_task: PrimaryTask = "direct_metric"
    presentation: Presentation = "text"
    metric_slots: list[MetricSlot] = Field(default_factory=list)
    cohort_slots: list[CohortSlot] = Field(default_factory=list)
    concept_slots: list[ConceptSlot] = Field(default_factory=list)
    temporal_scope: TemporalScope | None = None
    grouping_slots: list[GroupingSlot] = Field(default_factory=list)
    requested_tools: list[ToolRequest] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    requires_clarification: bool = False

    @model_validator(mode="after")
    def _chart_presentation_uses_chart_task(self) -> IntentPlan:
        if self.presentation == "chart" and self.primary_task == "direct_metric":
            self.primary_task = "chart"
        return self


def build_intent_plan(user_question: str) -> IntentPlan:
    """Build a deterministic intent fallback for tests and offline operation."""

    question = user_question or ""
    normalized = _normalize(question)
    visualization = detect_visualization_intent(question)
    presentation: Presentation = "chart" if visualization.requested else "text"
    primary_task = _infer_primary_task(normalized, presentation)
    temporal_scope = _infer_temporal_scope(normalized)
    metric_slots = _infer_metric_slots(normalized)
    concept_slots = _infer_concept_slots(question)
    cohort_slots = _infer_cohort_slots(question)
    groupings = _infer_grouping_slots(normalized)
    persona_hint = _infer_persona(normalized)
    out_of_scope = _looks_out_of_scope(normalized)

    plan = IntentPlan(
        user_question=question,
        persona_hint=persona_hint,
        primary_task="out_of_scope" if out_of_scope else primary_task,
        presentation=presentation,
        metric_slots=metric_slots,
        cohort_slots=cohort_slots,
        concept_slots=concept_slots,
        temporal_scope=temporal_scope,
        grouping_slots=groupings,
        requires_clarification=out_of_scope,
        uncertainty=["schema_may_not_support_requested_variable"] if out_of_scope else [],
    )
    return plan


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _infer_primary_task(normalized: str, presentation: Presentation) -> PrimaryTask:
    if presentation == "chart":
        if any(
            token in normalized
            for token in ["compare", "comparar", "comparando", "comparacao", "comparação"]
        ):
            return "comparison"
        if _looks_like_observational_association(normalized) or _looks_like_socioeconomic_association(normalized):
            return "association"
        if re.search(r"\bscatter\b|\bdispersao\b|\bdispersão\b", normalized):
            return "association"
        if _looks_like_ranking(normalized):
            return "ranking"
        if _has_temporal_language(normalized):
            return "trend"
        return "chart"
    if any(
        token in normalized
        for token in ["compare", "comparar", "comparando", "comparacao", "comparação"]
    ):
        return "comparison"
    if _looks_like_seasonal_comparison(normalized):
        return "comparison"
    if _looks_like_observational_association(normalized) or _looks_like_socioeconomic_association(normalized):
        return "association"
    if _looks_like_data_quality(normalized):
        return "data_quality"
    if _looks_like_ranking(normalized):
        return "ranking"
    if any(
        token in normalized
        for token in [
            "tendencia",
            "evolucao",
            "evolução",
            "ao longo",
            "serie anual",
            "série anual",
            "serie temporal",
            "série temporal",
            "anual",
        ]
    ):
        return "trend"
    if _has_recent_year_window(normalized):
        return "trend"
    if _looks_like_temporal_grouping(normalized):
        return "trend"
    if any(
        token in normalized
        for token in ["relacao", "relação", "associacao", "associação", "associado", "associada"]
    ):
        return "association"
    if any(
        token in normalized
        for token in [
            "por sexo",
            "por idade",
            "por municipio",
            "por estado",
            "por especialidade",
            "por faixa",
            "por raca",
            "por raça",
        ]
    ):
        return "breakdown"
    return "direct_metric"


def _infer_temporal_scope(normalized: str) -> TemporalScope | None:
    recent = re.search(
        r"\b(?:ultimos|ultimas|recentes)\s+(\d+|cinco|tres|três|dez)\s+anos?\b"
        r"|\b(?:nos\s+)?(\d+|cinco|tres|três|dez)\s+anos?\s+mais\s+recentes\b",
        normalized,
    )
    if recent:
        raw_value = recent.group(1) or recent.group(2)
        value = {"tres": 3, "três": 3, "cinco": 5, "dez": 10}.get(raw_value)
        return TemporalScope(type="last_n_available_years", n=value or int(raw_value))
    year_range = re.search(
        r"\b(?:entre\s+)?((?:19|20)\d{2})\s*(?:-|a|ate|até|e)\s*((?:19|20)\d{2})\b",
        normalized,
    )
    if year_range:
        return TemporalScope(
            type="year_range",
            start_year=int(year_range.group(1)),
            end_year=int(year_range.group(2)),
        )
    year = re.search(r"\b((?:19|20)\d{2})\b", normalized)
    if year:
        return TemporalScope(type="year", start_year=int(year.group(1)), end_year=int(year.group(1)))
    return TemporalScope(type="none") if _has_temporal_language(normalized) else None


def _infer_metric_slots(normalized: str) -> list[MetricSlot]:
    if any(token in normalized for token in ["morte", "mortes", "obito", "obitos", "óbito", "óbitos"]):
        return [MetricSlot(name="total_mortes", expression_type="count", required_filters=["MORTE = true"])]
    if "taxa" in normalized and "mortalidade" in normalized:
        return [MetricSlot(name="taxa_mortalidade", expression_type="rate")]
    if any(token in normalized for token in ["custo", "valor", "receita"]):
        return [MetricSlot(name="receita_total", expression_type="sum")]
    return [MetricSlot(name="total_internacoes", expression_type="count")]


def _infer_concept_slots(question: str) -> list[ConceptSlot]:
    filters = resolve_clinical_domain(question)
    if not filters:
        return []
    return [
        ConceptSlot(
            name="clinical_concept",
            concept_type="clinical",
            filters=[filter_.model_dump() for filter_ in filters],
        )
    ]


def _infer_cohort_slots(question: str) -> list[CohortSlot]:
    filters = resolve_population_group(question)
    if not filters:
        return []
    return [
        CohortSlot(
            name="population_group",
            filters=[filter_.model_dump() for filter_ in filters],
            caveat="semantic population policy applied",
        )
    ]


def _infer_grouping_slots(normalized: str) -> list[GroupingSlot]:
    groups: list[GroupingSlot] = []
    if _has_temporal_language(normalized):
        groups.append(GroupingSlot(name="ano"))
    for token, group in [
        ("por sexo", "sexo"),
        ("por municipio", "municipio"),
        ("por estado", "estado"),
        ("por uf", "estado"),
        ("por faixa etaria", "faixa_etaria"),
    ]:
        if token in normalized and group not in {item.name for item in groups}:
            groups.append(GroupingSlot(name=group))
    return groups


def _infer_persona(normalized: str) -> PersonaHint:
    if any(token in normalized for token in ["pesquisa", "associacao", "associação", "coorte"]):
        return "researcher"
    if any(token in normalized for token in ["paciente", "clinico", "clínico", "medico", "médico"]):
        return "clinician"
    if any(token in normalized for token in ["hospital", "gestor", "custo", "receita"]):
        return "manager"
    if any(token in normalized for token in ["qualidade", "nulo", "cobertura", "lookup"]):
        return "auditor"
    return "common_user"


def _looks_out_of_scope(normalized: str) -> bool:
    return any(
        token in normalized
        for token in [
            "antibiotico",
            "antibiótico",
            "vacina",
            "sobrevida",
            "sobrevida apos alta",
            "sobrevida após alta",
            "hemograma",
            "laboratorial",
            "remedio",
            "remédio",
            "medicamento",
            "prescrito",
            "reinternacao",
            "reinternação",
            "causou",
            "causal",
            "bairro",
            "renda individual",
            "saturacao",
            "saturação",
            "sinais vitais",
        ]
    )


def _has_temporal_language(normalized: str) -> bool:
    return any(
        token in normalized
        for token in ["ultimos", "ultimas", "ano", "anos", "mensal", "evolucao", "evolução"]
    )


def _has_recent_year_window(normalized: str) -> bool:
    return bool(
        re.search(r"\b(?:ultimos|ultimas|recentes)\s+\w+\s+anos?\b", normalized)
        or re.search(r"\b(?:nos\s+)?\w+\s+anos?\s+mais\s+recentes\b", normalized)
        or re.search(r"\banos\s+recentes\b", normalized)
    )


def _looks_like_ranking(normalized: str) -> bool:
    age_only = re.search(r"\bmenores\s+de\s+\d+\s+anos?\b", normalized)
    return bool(
        re.search(r"\b(?:ranking|top)\b", normalized)
        or re.search(r"\bmais\s+(?:frequentes?|comuns?)\b", normalized)
        or re.search(r"\b(?:maior|menor|maiores)\b", normalized)
        or (not age_only and re.search(r"\bmenores\b", normalized))
        or re.search(r"\b(?:tiveram|teve|tem|têm)\s+mais\b", normalized)
        or re.search(r"\bcom\s+mais\b", normalized)
    )


def _looks_like_temporal_grouping(normalized: str) -> bool:
    return bool(
        re.search(r"\bpor\s+(?:ano|anos|mes|m[eê]s|trimestre)\b", normalized)
        or re.search(r"\bao\s+longo\b", normalized)
        or re.search(r"\baument(?:ou|aram)|reduz(?:iu|iram)|cresceu|cairam|ca[ií]ram\b", normalized)
    )


def _looks_like_data_quality(normalized: str) -> bool:
    return any(
        token in normalized
        for token in [
            "nulo",
            "nulos",
            "vazio",
            "vazia",
            "ausente",
            "sem informacao",
            "sem informação",
            "lookup",
            "codigos",
            "códigos",
            "nunca aparecem",
            "qualidade",
            "cobertura",
            "nao tem",
            "não tem",
            "nao possui",
            "não possui",
            "mapeado",
        ]
    )


def _looks_like_seasonal_comparison(normalized: str) -> bool:
    return bool(
        ("inverno" in normalized or "verao" in normalized or "verão" in normalized)
        and re.search(r"\b(?:aument|reduz|cresc|queda|diminui)", normalized)
    )


def _looks_like_socioeconomic_association(normalized: str) -> bool:
    has_socioeconomic = any(
        token in normalized
        for token in ["pib", "mortalidade infantil", "medicos por 1000", "médicos por 1000"]
    )
    has_relationship = " e " in normalized or "entre" in normalized or "relacao" in normalized
    return has_socioeconomic and has_relationship


def _looks_like_observational_association(normalized: str) -> bool:
    has_comparison_language = bool(
        re.search(r"\b(?:tiveram|teve|tem|têm|apresentaram?)\s+maior\b", normalized)
        or re.search(r"\bmaior\s+(?:mortalidade|taxa|risco|frequencia|frequência)\b", normalized)
    )
    has_outcome = any(
        token in normalized
        for token in ["mortalidade", "morte", "mortes", "obito", "obitos", "óbito", "óbitos"]
    )
    has_cohort = any(
        token in normalized
        for token in ["paciente", "pacientes", "idoso", "idosos", "criança", "crianca"]
    )
    return has_comparison_language and has_outcome and has_cohort
