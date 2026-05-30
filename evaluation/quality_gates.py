"""Executable quality gates for database question-answering releases."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QualityGateThresholds:
    sql_read_only_rate: float = 1.0
    no_missing_table_rate: float = 1.0
    schema_unavailable_score: float = 0.95
    table_selection_accuracy: float = 0.95
    dev_smoke_runtime_success: float = 1.0
    regression_ex: float = 0.90
    max_regression_ex_drop: float = 0.02
    latency_or_token_reduction: float = 0.20
    fallback_boundary_violations: int = 0


@dataclass(frozen=True)
class QualityGateCheck:
    name: str
    passed: bool
    actual: float | int | None
    threshold: float | int
    reason: str = ""


def evaluate_quality_gates(
    payload: dict[str, Any],
    *,
    thresholds: QualityGateThresholds = QualityGateThresholds(),
) -> dict[str, Any]:
    """Evaluate release gates from runner summaries.

    Expected payload keys are intentionally simple so runners can emit them
    without depending on chatbot runtime modules.
    """

    checks = [
        _at_least(
            "sql_read_only",
            _get_number(payload, "sql_safety.read_only_rate"),
            thresholds.sql_read_only_rate,
        ),
        _at_least(
            "no_missing_table",
            _get_number(payload, "sql_safety.no_missing_table_rate"),
            thresholds.no_missing_table_rate,
        ),
        _at_least(
            "schema_unavailable",
            _get_number(payload, "schema_unavailable.score"),
            thresholds.schema_unavailable_score,
        ),
        _at_least(
            "table_selection",
            _get_number(payload, "table_selection.accuracy"),
            thresholds.table_selection_accuracy,
        ),
        _at_least(
            "dev_smoke_runtime",
            _get_number(payload, "dev_smoke.runtime_success_rate"),
            thresholds.dev_smoke_runtime_success,
        ),
        _at_least(
            "regression_ex",
            _get_number(payload, "regression.ex_overall"),
            thresholds.regression_ex,
        ),
        _regression_drop_check(payload, thresholds),
        _efficiency_check(payload, thresholds),
        _at_most(
            "fallback_llm_boundary",
            _get_number(payload, "fallback.invalid_fallback_count"),
            thresholds.fallback_boundary_violations,
        ),
    ]
    return {
        "passed": all(check.passed for check in checks),
        "checks": [asdict(check) for check in checks],
        "thresholds": asdict(thresholds),
    }


def render_quality_gate_report(evaluation: dict[str, Any]) -> str:
    lines = [
        "# Quality Gates",
        "",
        f"- Status: {'passed' if evaluation['passed'] else 'failed'}",
        "",
        "| Gate | Actual | Threshold | Status | Reason |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for check in evaluation["checks"]:
        actual = "n/a" if check["actual"] is None else _format_number(check["actual"])
        threshold = _format_number(check["threshold"])
        status = "passed" if check["passed"] else "failed"
        lines.append(
            f"| `{check['name']}` | {actual} | {threshold} | {status} | {check['reason']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate quality gates from a JSON summary.")
    parser.add_argument("summary_json", help="Path to a JSON summary with gate metrics.")
    parser.add_argument("--report", help="Optional Markdown report path.")
    args = parser.parse_args()

    payload = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    evaluation = evaluate_quality_gates(payload)
    report = render_quality_gate_report(evaluation)
    print(report)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding="utf-8")
    return 0 if evaluation["passed"] else 1


def _regression_drop_check(
    payload: dict[str, Any],
    thresholds: QualityGateThresholds,
) -> QualityGateCheck:
    current = _get_number(payload, "regression.ex_overall")
    baseline = _get_number(payload, "regression.baseline_ex_overall")
    if current is None or baseline is None:
        return QualityGateCheck(
            name="regression_no_material_drop",
            passed=False,
            actual=None,
            threshold=thresholds.max_regression_ex_drop,
            reason="missing current or baseline EX",
        )
    drop = max(0.0, baseline - current)
    return _at_most(
        "regression_no_material_drop",
        drop,
        thresholds.max_regression_ex_drop,
    )


def _efficiency_check(
    payload: dict[str, Any],
    thresholds: QualityGateThresholds,
) -> QualityGateCheck:
    latency_reduction = _reduction(
        _get_number(payload, "efficiency.baseline_p50_latency_seconds"),
        _get_number(payload, "efficiency.candidate_p50_latency_seconds"),
    )
    token_reduction = _reduction(
        _get_number(payload, "efficiency.baseline_tokens"),
        _get_number(payload, "efficiency.candidate_tokens"),
    )
    reductions = [value for value in (latency_reduction, token_reduction) if value is not None]
    actual = max(reductions) if reductions else None
    return _at_least("latency_or_token_reduction", actual, thresholds.latency_or_token_reduction)


def _reduction(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or baseline <= 0:
        return None
    return max(0.0, 1.0 - candidate / baseline)


def _at_least(name: str, actual: float | int | None, threshold: float | int) -> QualityGateCheck:
    if actual is None:
        return QualityGateCheck(name, False, None, threshold, "missing metric")
    return QualityGateCheck(name, float(actual) >= float(threshold), actual, threshold)


def _at_most(name: str, actual: float | int | None, threshold: float | int) -> QualityGateCheck:
    if actual is None:
        return QualityGateCheck(name, False, None, threshold, "missing metric")
    return QualityGateCheck(name, float(actual) <= float(threshold), actual, threshold)


def _get_number(payload: dict[str, Any], dotted_path: str) -> float | int | None:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _format_number(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
