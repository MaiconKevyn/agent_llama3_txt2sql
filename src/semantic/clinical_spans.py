"""Helpers for normalizing clinical text spans extracted from user queries."""

from __future__ import annotations

from dataclasses import dataclass, field

import re


@dataclass(frozen=True)
class ClinicalSpanNormalization:
    original: str
    normalized: str
    removed_modifiers: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original.strip().lower() != self.normalized.strip().lower()


_RELATIVE_YEAR_PATTERNS = (
    re.compile(
        r"\b(?:em|no|na|nos|nas|durante|para)?\s*(?:os|as)?\s*"
        r"(?:últimos|ultimos|últimas|ultimas)\s+\d+\s+anos?\b",
        re.I,
    ),
    re.compile(
        r"\b(?:em|no|na|nos|nas)?\s*(?:anos\s+)?mais\s+recentes"
        r"\s*\(?\s*\d+\s+anos?\s*\)?",
        re.I,
    ),
)

_EXPLICIT_YEAR_PATTERNS = (
    re.compile(
        r"\b(?:em|no|na|nos|nas|de|entre)\s+(?:19|20)\d{2}"
        r"(?:\s*(?:,|e|a|até|ate|-)\s*(?:19|20)\d{2})+\b",
        re.I,
    ),
    re.compile(r"\b(?:em|no|na|nos|nas)\s+(?:19|20)\d{2}\b", re.I),
)

_GROUPING_TRAILING_PATTERN = re.compile(
    r"\b(?:por|segundo|conforme)\s+"
    r"(?:ano|anos|m[eê]s|meses|trimestre|trimestres|estado|uf|munic[ií]pio|"
    r"sexo|idade|faixa|grupo|ra[cç]a(?:/cor)?|raca(?:/cor)?|cor|cores|"
    r"instru[cç][aã]o|escolaridade)\b.*$",
    re.I,
)

_ANSWER_SHAPE_TRAILING_PATTERN = re.compile(
    r"\b(?:ao\s+longo\s+d[eo]s?\s+anos?|evolu[cç][aã]o|tend[eê]ncia|s[eé]rie)\b.*$",
    re.I,
)

_LEADING_CONTEXT_PATTERN = re.compile(
    r"^(?:n[uú]mero|numero|total|quantidade|qtd|contagem)\s+(?:de\s+)?",
    re.I,
)


def normalize_clinical_span(value: str) -> ClinicalSpanNormalization:
    """Remove query modifiers from a candidate clinical concept span."""

    original = re.sub(r"\s+", " ", (value or "").strip())
    normalized = original
    removed: list[str] = []

    for pattern in (
        *_RELATIVE_YEAR_PATTERNS,
        *_EXPLICIT_YEAR_PATTERNS,
        _GROUPING_TRAILING_PATTERN,
        _ANSWER_SHAPE_TRAILING_PATTERN,
        _LEADING_CONTEXT_PATTERN,
    ):
        normalized, count = pattern.subn(" ", normalized)
        if count:
            removed.append(pattern.pattern)
            normalized = re.sub(r"\s+", " ", normalized).strip(" -,.")

    normalized = _trim_dangling_connectors(normalized)
    return ClinicalSpanNormalization(
        original=original,
        normalized=normalized,
        removed_modifiers=removed,
    )


def _trim_dangling_connectors(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value or "").strip(" -,.")
    normalized = re.sub(r"\b(?:em|no|na|nos|nas|de|do|da|dos|das|por)\s*$", "", normalized, flags=re.I)
    normalized = re.sub(r"^(?:de|do|da|dos|das)\s+", "", normalized, flags=re.I)
    return re.sub(r"\s+", " ", normalized).strip(" -,.")
