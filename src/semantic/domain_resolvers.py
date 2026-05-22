"""Reusable semantic domain resolvers.

These helpers resolve user-facing concepts into semantic filters without tying
the behavior to one benchmark question.
"""

from __future__ import annotations

import re

from .concept_resolver import normalize_clinical_text, resolve_clinical_concept
from .domain_policy import CHILD_AGE_UPPER_EXCLUSIVE
from .plan_schema import SemanticFilter


def resolve_population_group(text: str) -> list[SemanticFilter]:
    """Resolve population/cohort terms into reusable semantic filters."""

    normalized = normalize_clinical_text(text)
    if not normalized:
        return []
    if "mortalidade infantil" in normalized:
        return []

    explicit_child = _explicit_upper_age_filter(normalized)
    if explicit_child is not None:
        return [explicit_child]

    if re.search(
        r"\b(crianca|criancas|pediatrico|pediatricos|pediatrica|pediatricas|infantil|infantis)\b",
        normalized,
    ):
        return [
            SemanticFilter(
                field="idade",
                values=[str(CHILD_AGE_UPPER_EXCLUSIVE)],
                operator="<",
            )
        ]
    return []


def resolve_clinical_domain(text: str) -> list[SemanticFilter]:
    """Resolve broad clinical concepts into diagnosis filters."""

    concept = resolve_clinical_concept(text)
    if concept is None:
        return []

    filters: list[SemanticFilter] = []
    if concept.resolved_codes:
        filters.append(
            SemanticFilter(
                field="diagnostico_principal_codigo",
                values=concept.resolved_codes,
                operator="IN" if len(concept.resolved_codes) > 1 else "=",
            )
        )
    if concept.resolved_prefixes:
        filters.append(
            SemanticFilter(
                field="diagnostico_principal_prefix",
                values=concept.resolved_prefixes,
                operator="LIKE" if len(concept.resolved_prefixes) == 1 else "LIKE_ANY",
            )
        )
    if concept.labels:
        filters.append(
            SemanticFilter(
                field="diagnostico_conceito_label",
                values=concept.labels,
                operator="metadata",
            )
        )
    return filters


def _explicit_upper_age_filter(normalized: str) -> SemanticFilter | None:
    for pattern in [
        r"\bmenores\s+de\s+(\d+)\s+anos?\b",
        r"\bmenos\s+de\s+(\d+)\s+anos?\b",
        r"\bidade\s*<\s*(\d+)\b",
    ]:
        match = re.search(pattern, normalized)
        if match:
            value = int(match.group(1))
            if value == 1:
                return SemanticFilter(field="idade", values=["0"], operator="=")
            return SemanticFilter(field="idade", values=[str(value)], operator="<")
    return None
