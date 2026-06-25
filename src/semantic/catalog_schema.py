"""Validation helpers for the declarative semantic catalog."""

from __future__ import annotations

from .catalog import SemanticCatalog, load_semantic_catalog

DERIVED_METRIC_TYPES = {"rate", "ratio", "proportion"}


def validate_semantic_catalog(catalog: SemanticCatalog | None = None) -> list[str]:
    """Return schema and contract errors for the semantic catalog."""
    catalog = catalog or load_semantic_catalog()
    errors: list[str] = []

    for name, metric in catalog.metrics.items():
        if not metric.grain:
            errors.append(f"metric.{name}: grain is required")
        if metric.expression_type in DERIVED_METRIC_TYPES:
            if not metric.numerator:
                errors.append(f"metric.{name}: numerator is required for derived metrics")
            if not metric.denominator:
                errors.append(f"metric.{name}: denominator is required for derived metrics")
            if not metric.denominator_scope:
                errors.append(f"metric.{name}: denominator_scope is required for derived metrics")
        if metric.expression_type == "avg" and not (
            metric.expression or metric.numerator or metric.denominator
        ):
            errors.append(f"metric.{name}: average metric requires expression")

    for name, dimension in catalog.dimensions.items():
        if not dimension.source:
            errors.append(f"dimension.{name}: source is required")
        if dimension.joins and not dimension.join_path:
            errors.append(f"dimension.{name}: join_path is required when joins are declared")
        for join in dimension.join_path:
            if "->" not in join:
                errors.append(f"dimension.{name}: invalid join_path entry {join!r}")
        if dimension.join_path and not dimension.grain:
            errors.append(f"dimension.{name}: grain is required when join_path is declared")

    for name, macro in catalog.macros.items():
        if not macro.template.strip():
            errors.append(f"macro.{name}: template is required")

    for name, rule in catalog.rules.items():
        if rule.severity not in {"info", "warning", "error"}:
            errors.append(f"rule.{name}: unsupported severity {rule.severity!r}")

    return errors


def assert_valid_semantic_catalog(catalog: SemanticCatalog | None = None) -> None:
    errors = validate_semantic_catalog(catalog)
    if errors:
        raise ValueError("Invalid semantic catalog:\n" + "\n".join(errors))
