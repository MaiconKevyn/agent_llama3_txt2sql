"""Clinical concept resolution helpers for semantic planning.

The resolver is intentionally deterministic first: it maps common user-facing
clinical terms to auditable CID codes and metadata that downstream SQL can use.
Database-backed and LLM-backed candidate expansion can be added behind this
interface without changing the planner contract.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel, Field


class ResolvedClinicalConcept(BaseModel):
    """Resolved clinical concept with auditable CID targets."""

    input_term: str
    canonical_name: str
    resolved_codes: list[str] = Field(default_factory=list)
    resolved_prefixes: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    resolution_strategy: str
    confidence: float
    warnings: list[str] = Field(default_factory=list)
    default_denominator_filters: dict[str, str] = Field(default_factory=dict)
    expanded_terms: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _ConceptDefinition:
    canonical_name: str
    aliases: tuple[str, ...]
    resolved_codes: tuple[str, ...]
    resolved_prefixes: tuple[str, ...]
    labels: tuple[str, ...]
    default_denominator_filters: dict[str, str]
    expanded_terms: tuple[str, ...] = ()
    confidence: float = 0.95


_CONCEPTS: tuple[_ConceptDefinition, ...] = (
    _ConceptDefinition(
        canonical_name="cancer de prostata",
        aliases=(
            "cancer de prostata",
            "câncer de próstata",
            "neoplasia maligna da prostata",
            "neoplasia maligna da próstata",
            "tumor maligno de prostata",
            "tumor maligno da prostata",
            "prostata cancer",
            "prostate cancer",
        ),
        resolved_codes=("C61",),
        resolved_prefixes=(),
        labels=("C61 - Neopl malig da prostata",),
        default_denominator_filters={"sexo": "1"},
        expanded_terms=("prostata", "neopl malig da prostata"),
    ),
    _ConceptDefinition(
        canonical_name="covid",
        aliases=(
            "covid",
            "covid 19",
            "covid-19",
            "coronavirus",
            "coronavírus",
            "sars cov 2",
            "sars-cov-2",
        ),
        resolved_codes=("B342", "B972"),
        resolved_prefixes=(),
        labels=(
            "B342 - Infecc p/coronavirus NE",
            "B972 - Coronavirus como causa de doenc class outr cap",
        ),
        default_denominator_filters={},
        expanded_terms=("covid", "coronavirus"),
    ),
    _ConceptDefinition(
        canonical_name="doencas respiratorias",
        aliases=(
            "doencas respiratorias",
            "doenças respiratórias",
            "doenca respiratoria",
            "doença respiratória",
            "respiratorias",
            "respiratórias",
            "respiratorios",
            "respiratórios",
            "doencas pulmonares",
            "doenças pulmonares",
            "doenca pulmonar",
            "doença pulmonar",
            "problemas pulmonares",
            "problema pulmonar",
            "problemas respiratorios",
            "problemas respiratórios",
            "aparelho respiratorio",
            "aparelho respiratório",
            "doencas do aparelho respiratorio",
            "doenças do aparelho respiratório",
            "causa respiratoria",
            "causa respiratória",
            "causas respiratorias",
            "causas respiratórias",
            "condicoes respiratorias",
            "condições respiratórias",
            "cid respiratorio",
            "cid respiratório",
            "cid de respiratorio",
            "cid de respiratório",
            "cid j",
        ),
        resolved_codes=(),
        resolved_prefixes=("J%",),
        labels=("CID J00-J99 - Doencas do aparelho respiratorio",),
        default_denominator_filters={},
        expanded_terms=("doenca respiratoria", "doenca pulmonar", "cid j"),
    ),
    _ConceptDefinition(
        canonical_name="asma",
        aliases=("asma", "asmas", "asthma"),
        resolved_codes=("J45", "J46"),
        resolved_prefixes=(),
        labels=("CID J45-J46 - Asma e estado de mal asmatico",),
        default_denominator_filters={},
        expanded_terms=("asma", "estado de mal asmatico"),
    ),
    _ConceptDefinition(
        canonical_name="neoplasias",
        aliases=(
            "neoplasia",
            "neoplasias",
            "cancer",
            "câncer",
            "neoplasias malignas",
            "tumores malignos",
        ),
        resolved_codes=(),
        resolved_prefixes=("C%",),
        labels=("CID C00-C99 - Neoplasias malignas",),
        default_denominator_filters={},
        expanded_terms=("cid c", "neoplasia maligna"),
    ),
    _ConceptDefinition(
        canonical_name="doencas cardiovasculares",
        aliases=(
            "doencas cardiovasculares",
            "doenças cardiovasculares",
            "doenca cardiovascular",
            "doença cardiovascular",
            "cardiovascular",
            "cardiovasculares",
            "doencas do aparelho circulatorio",
            "doenças do aparelho circulatório",
            "problemas do coracao",
            "problemas do coração",
            "problema do coracao",
            "problema do coração",
            "doencas do coracao",
            "doenças do coração",
            "doencas cardiacas",
            "doenças cardíacas",
        ),
        resolved_codes=(),
        resolved_prefixes=("I%",),
        labels=("CID I00-I99 - Doencas do aparelho circulatorio",),
        default_denominator_filters={},
        expanded_terms=("cid i", "cardiovascular", "aparelho circulatorio"),
    ),
    _ConceptDefinition(
        canonical_name="doencas infecciosas e parasitarias",
        aliases=(
            "doencas infecciosas e parasitarias",
            "doenças infecciosas e parasitárias",
            "doencas infecciosas",
            "doenças infecciosas",
            "infeccoes",
            "infecções",
            "infecciosas",
        ),
        resolved_codes=(),
        resolved_prefixes=("A%", "B%"),
        labels=("CID A00-B99 - Algumas doencas infecciosas e parasitarias",),
        default_denominator_filters={},
        expanded_terms=("infecciosa", "parasitaria", "cid a", "cid b"),
    ),
    _ConceptDefinition(
        canonical_name="gravidez parto e puerperio",
        aliases=(
            "gravidez parto puerperio",
            "gravidez parto e puerperio",
            "gravidez parto ou puerperio",
            "gravidez, parto ou puerperio",
            "gravidez, parto e puerperio",
            "gravidez, parto ou puerpério",
            "gravidez parto e puerpério",
        ),
        resolved_codes=(),
        resolved_prefixes=("O%",),
        labels=("CID O00-O99 - Gravidez, parto e puerperio",),
        default_denominator_filters={"sexo": "3"},
        expanded_terms=("gravidez", "parto", "puerperio"),
    ),
    _ConceptDefinition(
        canonical_name="tuberculose",
        aliases=("tuberculose", "tuberculoses"),
        resolved_codes=(),
        resolved_prefixes=("A15%", "A16%", "A17%", "A18%", "A19%"),
        labels=("CID A15-A19 - Tuberculose",),
        default_denominator_filters={},
        expanded_terms=("tuberc", "tuberculose"),
    ),
    _ConceptDefinition(
        canonical_name="insuficiencia renal",
        aliases=("insuficiencia renal", "insuficiência renal", "falencia renal", "falência renal"),
        resolved_codes=(),
        resolved_prefixes=("N17%", "N18%", "N19%"),
        labels=("CID N17-N19 - Insuficiencia renal",),
        default_denominator_filters={},
        expanded_terms=("insuf renal", "renal"),
    ),
    _ConceptDefinition(
        canonical_name="acidente vascular cerebral",
        aliases=(
            "acidente vascular cerebral",
            "avc",
            "derrame cerebral",
            "doenca cerebrovascular",
            "doença cerebrovascular",
        ),
        resolved_codes=(),
        resolved_prefixes=("I60%", "I61%", "I62%", "I63%", "I64%"),
        labels=("CID I60-I64 - Doencas cerebrovasculares agudas",),
        default_denominator_filters={},
        expanded_terms=("cerebrovascular", "acidente vascular cerebral"),
    ),
    _ConceptDefinition(
        canonical_name="colelitiase",
        aliases=(
            "colelitiase",
            "colelitíase",
            "pedra na vesicula",
            "pedra na vesícula",
            "calculo biliar",
            "cálculo biliar",
        ),
        resolved_codes=(),
        resolved_prefixes=("K80%",),
        labels=("CID K80 - Colelitiase",),
        default_denominator_filters={},
        expanded_terms=("colelitiase", "vesicula biliar"),
    ),
)


def normalize_clinical_text(value: str) -> str:
    """Normalize user clinical text for deterministic matching."""
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower()
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = normalized.replace("-", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def resolve_clinical_concept(term: str) -> ResolvedClinicalConcept | None:
    """Resolve a clinical term to known CID codes when a deterministic alias matches."""
    normalized_term = normalize_clinical_text(term)
    if not normalized_term:
        return None

    for concept in _CONCEPTS:
        for alias in concept.aliases:
            normalized_alias = normalize_clinical_text(alias)
            if not normalized_alias:
                continue
            if _contains_alias(normalized_term, normalized_alias):
                return _to_resolved_concept(term, concept)
    return None


def find_clinical_concepts(text: str) -> list[ResolvedClinicalConcept]:
    """Find all deterministic clinical concepts mentioned in free text."""
    normalized_text = normalize_clinical_text(text)
    if not normalized_text:
        return []

    resolved: list[ResolvedClinicalConcept] = []
    seen: set[str] = set()
    for concept in _CONCEPTS:
        if concept.canonical_name in seen:
            continue
        if any(
            _contains_alias(normalized_text, normalize_clinical_text(alias))
            for alias in concept.aliases
        ):
            resolved.append(_to_resolved_concept(text, concept))
            seen.add(concept.canonical_name)
    return resolved


def _contains_alias(text: str, alias: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.I))


def _to_resolved_concept(
    input_term: str,
    concept: _ConceptDefinition,
) -> ResolvedClinicalConcept:
    return ResolvedClinicalConcept(
        input_term=input_term,
        canonical_name=concept.canonical_name,
        resolved_codes=list(concept.resolved_codes),
        resolved_prefixes=list(concept.resolved_prefixes),
        labels=list(concept.labels),
        resolution_strategy="curated_alias",
        confidence=concept.confidence,
        default_denominator_filters=dict(concept.default_denominator_filters),
        expanded_terms=list(concept.expanded_terms),
    )
