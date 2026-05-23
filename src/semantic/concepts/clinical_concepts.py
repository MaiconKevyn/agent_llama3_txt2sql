"""Typed loader for the versioned clinical concept catalog."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CLINICAL_CONCEPTS_VERSION = "clinical_concepts_v1"
DEFAULT_CLINICAL_CONCEPTS_PATH = Path(__file__).with_name("clinical_concepts_v1.yaml")


@dataclass(frozen=True)
class ClinicalConceptDefinition:
    concept_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    resolved_codes: tuple[str, ...]
    resolved_prefixes: tuple[str, ...]
    labels: tuple[str, ...]
    default_denominator_filters: dict[str, str]
    expanded_terms: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    confidence: float = 0.95
    source: str = CLINICAL_CONCEPTS_VERSION


@lru_cache(maxsize=4)
def load_clinical_concepts(
    path: str | Path = DEFAULT_CLINICAL_CONCEPTS_PATH,
) -> tuple[ClinicalConceptDefinition, ...]:
    catalog_path = Path(path)
    with catalog_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    version = str(payload.get("version") or "").strip()
    if version != CLINICAL_CONCEPTS_VERSION:
        raise ValueError(
            f"Unsupported clinical concept catalog version {version!r}; "
            f"expected {CLINICAL_CONCEPTS_VERSION!r}."
        )

    concepts = payload.get("concepts") or {}
    if not isinstance(concepts, dict):
        raise ValueError("clinical concepts catalog must contain a mapping under 'concepts'.")

    return tuple(
        _definition_from_payload(concept_id, data) for concept_id, data in concepts.items()
    )


def _definition_from_payload(
    concept_id: str,
    payload: dict[str, Any],
) -> ClinicalConceptDefinition:
    if not isinstance(payload, dict):
        raise ValueError(f"clinical concept {concept_id!r} must be a mapping.")

    canonical_name = str(payload.get("canonical_name") or concept_id).strip()
    aliases = _as_tuple(payload.get("aliases"))
    if not aliases:
        raise ValueError(f"clinical concept {concept_id!r} must define at least one alias.")

    return ClinicalConceptDefinition(
        concept_id=concept_id,
        canonical_name=canonical_name,
        aliases=aliases,
        resolved_codes=_as_tuple(payload.get("resolved_codes")),
        resolved_prefixes=_as_tuple(payload.get("resolved_prefixes")),
        labels=_as_tuple(payload.get("labels")),
        default_denominator_filters={
            str(key): str(value)
            for key, value in (payload.get("default_denominator_filters") or {}).items()
        },
        expanded_terms=_as_tuple(payload.get("expanded_terms")),
        caveats=_as_tuple(payload.get("caveats")),
        confidence=float(payload.get("confidence", 0.95)),
    )


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
