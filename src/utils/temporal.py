"""Small temporal-expression helpers shared by planning layers."""

from __future__ import annotations

import re
import unicodedata

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\s*(?:-|a|ate|até)\s*((?:19|20)\d{2})\b",
    re.I,
)

_SINGLE_TOTAL_CUES = (
    "ao todo",
    "consolidado",
    "consolidada",
    "consolidados",
    "consolidadas",
    "no periodo inteiro",
    "no periodo todo",
    "soma total",
    "somando",
    "total acumulado",
    "total agregado",
    "total geral",
    "todos os anos juntos",
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def extract_explicit_year_list(text: str) -> list[str]:
    """Return explicit listed years, excluding continuous range endpoints."""

    normalized = _normalize(text)
    range_spans = [match.span() for match in _YEAR_RANGE_RE.finditer(normalized)]
    years: list[str] = []
    seen: set[str] = set()
    for match in _YEAR_RE.finditer(normalized):
        if any(start <= match.start() and match.end() <= end for start, end in range_spans):
            continue
        year = match.group(0)
        if year not in seen:
            seen.add(year)
            years.append(year)
    return years if len(years) >= 2 else []


def asks_single_total_across_years(text: str) -> bool:
    """Detect wording that asks for one aggregate across an explicit year list."""

    normalized = _normalize(text)
    if not extract_explicit_year_list(normalized):
        return False
    return any(cue in normalized for cue in _SINGLE_TOTAL_CUES)


def explicit_year_list_is_temporal_dimension(text: str) -> bool:
    """Return whether an explicit year list should become an output dimension."""

    return bool(extract_explicit_year_list(text)) and not asks_single_total_across_years(text)
