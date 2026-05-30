"""Aggregate evaluation metrics by domain family."""

from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_by_family(
    items: list[dict[str, Any]],
    *,
    family_key: str = "category",
) -> dict[str, dict[str, Any]]:
    families = sorted({_family(item, family_key) for item in items})
    summary: dict[str, dict[str, Any]] = {}
    for family in families:
        family_items = [item for item in items if _family(item, family_key) == family]
        scored_items = [item for item in family_items if _is_scored(item)]
        passed = sum(1 for item in scored_items if _is_passed(item))
        latencies = _numeric_values(family_items, "latency_seconds", "elapsed_s")
        total_tokens = sum(_number_or_zero(item.get("total_tokens")) for item in family_items)
        total_cost = sum(_number_or_zero(item.get("total_cost_usd")) for item in family_items)
        error_counts = Counter(
            str(item.get("root_cause") or item.get("error_category") or "unknown")
            for item in family_items
            if _is_failed(item)
        )
        summary[family] = {
            "passed": passed,
            "total": len(scored_items),
            "score": round(passed / len(scored_items), 4) if scored_items else 0.0,
            "avg_latency_s": _average(latencies),
            "p95_latency_s": _percentile(latencies, 95),
            "total_tokens": int(total_tokens),
            "total_cost_usd": round(total_cost, 6),
            "error_counts": dict(error_counts),
            "answerability_counts": dict(Counter(item.get("answerability") for item in family_items)),
        }
    return summary


def render_family_summary_markdown(
    family_summary: dict[str, dict[str, Any]],
    *,
    title: str = "Family Metrics",
) -> str:
    lines = [
        f"## {title}",
        "",
        "| Family | Passed | Total | Score | Avg latency | p95 latency | Tokens | Cost | Errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for family, row in sorted(family_summary.items()):
        errors = ", ".join(
            f"{name}:{count}" for name, count in sorted((row.get("error_counts") or {}).items())
        )
        lines.append(
            f"| `{family}` | {row['passed']} | {row['total']} | "
            f"{float(row['score']):.1%} | {_format_seconds(row['avg_latency_s'])} | "
            f"{_format_seconds(row['p95_latency_s'])} | {row['total_tokens']} | "
            f"{float(row['total_cost_usd']):.4f} | {errors or '-'} |"
        )
    return "\n".join(lines)


def _family(item: dict[str, Any], family_key: str) -> str:
    return str(item.get(family_key) or item.get("family") or item.get("category") or "unknown")


def _is_scored(item: dict[str, Any]) -> bool:
    return item.get("status") in {"passed", "failed"} or isinstance(item.get("ex"), bool)


def _is_passed(item: dict[str, Any]) -> bool:
    if isinstance(item.get("ex"), bool):
        return bool(item["ex"])
    return item.get("status") == "passed"


def _is_failed(item: dict[str, Any]) -> bool:
    if isinstance(item.get("ex"), bool):
        return not bool(item["ex"])
    return item.get("status") == "failed"


def _numeric_values(items: list[dict[str, Any]], *keys: str) -> list[float]:
    values: list[float] = []
    for item in items:
        for key in keys:
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            values.append(float(value))
            break
    return values


def _number_or_zero(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * percentile / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 3)


def _format_seconds(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):.2f}s"
