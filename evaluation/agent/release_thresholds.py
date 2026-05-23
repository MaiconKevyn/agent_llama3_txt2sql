from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReleaseThresholds:
    global_score: float = 0.90
    critical_domain_score: float = 0.85
    out_of_schema_score: float = 0.95
    ambiguity_score: float = 0.90
    common_median_latency_seconds: float = 12.0
    analytic_p95_latency_seconds: float = 30.0


CRITICAL_DOMAINS = {
    "volume_temporal",
    "geografia",
    "diagnosticos_cid",
    "procedimentos",
    "custos_permanencia",
    "socioeconomico_populacao",
    "qualidade_dados",
    "fora_do_schema",
    "ambiguidade",
}


def evaluate_release_thresholds(
    benchmark_result: dict[str, Any],
    *,
    thresholds: ReleaseThresholds = ReleaseThresholds(),
) -> dict[str, Any]:
    summary = benchmark_result.get("summary") or {}
    category_scores = summary.get("category_scores") or {}
    items = benchmark_result.get("items") or []
    checks = [
        _check_score("global_score", summary.get("score"), thresholds.global_score),
    ]

    for domain in sorted(CRITICAL_DOMAINS):
        domain_score = (category_scores.get(domain) or {}).get("score")
        minimum = thresholds.critical_domain_score
        if domain == "fora_do_schema":
            minimum = thresholds.out_of_schema_score
        elif domain == "ambiguidade":
            minimum = thresholds.ambiguity_score
        checks.append(_check_score(f"domain:{domain}", domain_score, minimum))

    latencies = [
        item.get("latency_seconds")
        for item in items
        if item.get("answerability") == "answerable"
        and isinstance(item.get("latency_seconds"), int | float)
    ]
    if latencies:
        checks.append(
            _check_score(
                "latency:answerable_median",
                statistics.median(latencies),
                thresholds.common_median_latency_seconds,
                lower_is_better=True,
            )
        )
        checks.append(
            _check_score(
                "latency:answerable_p95",
                _percentile(latencies, 95),
                thresholds.analytic_p95_latency_seconds,
                lower_is_better=True,
            )
        )
    else:
        checks.append(
            {
                "name": "latency:answerable_median",
                "passed": False,
                "actual": None,
                "threshold": thresholds.common_median_latency_seconds,
                "reason": "no answerable latency samples",
            }
        )

    return {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "thresholds": thresholds.__dict__,
    }


def render_release_threshold_report(evaluation: dict[str, Any]) -> str:
    lines = [
        "# Release V1 Threshold Check",
        "",
        f"- Status: {'passed' if evaluation['passed'] else 'failed'}",
        "",
        "| Check | Actual | Threshold | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for check in evaluation["checks"]:
        actual = "n/a" if check["actual"] is None else f"{check['actual']:.3f}"
        threshold = f"{check['threshold']:.3f}"
        status = "passed" if check["passed"] else "failed"
        lines.append(f"| `{check['name']}` | {actual} | {threshold} | {status} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate benchmark result against release v1 gates."
    )
    parser.add_argument("benchmark_json", help="Path to generalization benchmark JSON result.")
    parser.add_argument("--report", help="Optional Markdown report path.")
    args = parser.parse_args()

    benchmark_result = json.loads(Path(args.benchmark_json).read_text(encoding="utf-8"))
    evaluation = evaluate_release_thresholds(benchmark_result)
    report = render_release_threshold_report(evaluation)
    print(report)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding="utf-8")
    return 0 if evaluation["passed"] else 1


def _check_score(
    name: str,
    actual: float | None,
    threshold: float,
    *,
    lower_is_better: bool = False,
) -> dict[str, Any]:
    if actual is None:
        return {
            "name": name,
            "passed": False,
            "actual": None,
            "threshold": threshold,
            "reason": "missing score",
        }
    passed = actual <= threshold if lower_is_better else actual >= threshold
    return {
        "name": name,
        "passed": passed,
        "actual": float(actual),
        "threshold": threshold,
        "reason": "",
    }


def _percentile(values: list[float], percentile: int) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


if __name__ == "__main__":
    raise SystemExit(main())
