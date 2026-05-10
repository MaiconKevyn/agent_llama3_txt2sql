"""Temporary display-text normalization for chart labels."""

from __future__ import annotations

from typing import Any

MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "â€“", "â€™")


def normalize_chart_label(value: Any) -> Any:
    """Repair common UTF-8-as-Latin-1 mojibake in labels shown by charts."""

    if not isinstance(value, str) or not _looks_mojibake(value):
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value
    return repaired if _mojibake_score(repaired) < _mojibake_score(value) else value


def _looks_mojibake(value: str) -> bool:
    return any(marker in value for marker in MOJIBAKE_MARKERS)


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in MOJIBAKE_MARKERS)
