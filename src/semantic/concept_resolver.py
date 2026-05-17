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
            "doencas pulmonares",
            "doenças pulmonares",
            "doenca pulmonar",
            "doença pulmonar",
            "problemas pulmonares",
            "problema pulmonar",
            "problemas respiratorios",
            "problemas respiratórios",
        ),
        resolved_codes=(),
        resolved_prefixes=("J%",),
        labels=("CID J00-J99 - Doencas do aparelho respiratorio",),
        default_denominator_filters={},
        expanded_terms=("doenca respiratoria", "doenca pulmonar", "cid j"),
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
