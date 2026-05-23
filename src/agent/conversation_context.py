import re
from dataclasses import dataclass
from typing import Any

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
YEAR_ONLY_FOLLOWUP_RE = re.compile(
    r"^\s*(?:e\s+)?(?:em|no|na|para|ano\s+de)?\s*((?:19|20)\d{2})\s*[?.!]?\s*$",
    re.IGNORECASE,
)
DIMENSION_FOLLOWUP_RE = re.compile(
    r"^\s*(?:agora\s+)?(?:por|segundo|agrupad[ao]\s+por)\s+"
    r"(sexo|genero|g[e\u00ea]nero|uf|estado|munic[i\u00ed]pio|municipio|mes|m[e\u00ea]s)\s*[?.!]?\s*$",
    re.IGNORECASE,
)
UF_FILTER_FOLLOWUP_RE = re.compile(
    r"^\s*(?:agora\s+)?(?:s[o\u00f3]|somente|apenas)\s+(?:no|na|em)?\s*([A-Z]{2})\s*[?.!]?\s*$",
    re.IGNORECASE,
)

DIMENSION_LABELS = {
    "genero": "sexo",
    "g\u00eanero": "sexo",
    "mes": "mes",
}


@dataclass(frozen=True)
class ContextualFollowup:
    is_followup: bool
    resolved_query: str
    canonical_query: str
    metadata: dict[str, Any]


def resolve_contextual_followup(
    *,
    user_query: str,
    cached_result: dict[str, Any] | None,
) -> ContextualFollowup:
    """Resolve short textual follow-ups against the last analytic query in a session."""

    previous_query = _previous_query(cached_result)
    if not previous_query:
        return _not_followup(user_query)

    stripped_query = user_query.strip()
    year_match = YEAR_ONLY_FOLLOWUP_RE.match(stripped_query)
    if year_match:
        year = year_match.group(1)
        canonical = _replace_or_append_year(previous_query, year)
        return _followup(
            user_query=user_query,
            previous_query=previous_query,
            canonical_query=canonical,
            followup_type="year_filter",
            applied={"year": year},
        )

    dimension_match = DIMENSION_FOLLOWUP_RE.match(stripped_query)
    if dimension_match:
        dimension = _normalize_dimension(dimension_match.group(1))
        canonical = _append_clause(previous_query, f"por {dimension}")
        return _followup(
            user_query=user_query,
            previous_query=previous_query,
            canonical_query=canonical,
            followup_type="add_dimension",
            applied={"dimension": dimension},
        )

    uf_match = UF_FILTER_FOLLOWUP_RE.match(stripped_query)
    if uf_match:
        uf = uf_match.group(1).upper()
        canonical = _append_clause(previous_query, f"no estado {uf}")
        return _followup(
            user_query=user_query,
            previous_query=previous_query,
            canonical_query=canonical,
            followup_type="add_uf_filter",
            applied={"uf": uf},
        )

    return _not_followup(user_query)


def _previous_query(cached_result: dict[str, Any] | None) -> str | None:
    if not cached_result:
        return None
    query = cached_result.get("canonical_query") or cached_result.get("user_query")
    if not isinstance(query, str) or not query.strip():
        return None
    return query.strip()


def _not_followup(user_query: str) -> ContextualFollowup:
    return ContextualFollowup(
        is_followup=False,
        resolved_query=user_query,
        canonical_query=user_query,
        metadata={},
    )


def _followup(
    *,
    user_query: str,
    previous_query: str,
    canonical_query: str,
    followup_type: str,
    applied: dict[str, Any],
) -> ContextualFollowup:
    return ContextualFollowup(
        is_followup=True,
        resolved_query=canonical_query,
        canonical_query=canonical_query,
        metadata={
            "is_followup": True,
            "type": followup_type,
            "original_query": user_query,
            "previous_query": previous_query,
            "resolved_query": canonical_query,
            "applied": applied,
        },
    )


def _replace_or_append_year(previous_query: str, year: str) -> str:
    if YEAR_RE.search(previous_query):
        return YEAR_RE.sub(year, previous_query, count=1)
    return _append_clause(previous_query, f"em {year}")


def _append_clause(previous_query: str, clause: str) -> str:
    base = previous_query.strip().rstrip("?.!")
    if clause.lower() in base.lower():
        return previous_query.strip()
    return f"{base} {clause}?"


def _normalize_dimension(raw: str) -> str:
    lowered = raw.strip().lower()
    return DIMENSION_LABELS.get(lowered, lowered)
