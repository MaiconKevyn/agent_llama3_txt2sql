"""Versioned semantic catalog loader.

The catalog is a declarative source of reusable metrics, dimensions, SQL macros,
and semantic rules. It is intentionally benchmark-agnostic and can be used by
planning, prompting, validation, and future evaluation tooling.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .plan_schema import SemanticPlan

CATALOG_PATH = Path(__file__).with_name("catalog.yml")


class CatalogMetric(BaseModel):
    label: str
    grain: str
    expression_type: str
    expression: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    denominator_scope: str | None = None
    required_filters: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class CatalogDimension(BaseModel):
    label: str
    source: str
    joins: list[str] = Field(default_factory=list)
    default_for: list[str] = Field(default_factory=list)
    output_policy: str | None = None


class CatalogMacro(BaseModel):
    description: str
    required_sql_features: list[str] = Field(default_factory=list)
    template: str


class CatalogRule(BaseModel):
    severity: str
    description: str


class SemanticCatalog(BaseModel):
    version: int
    description: str
    metrics: dict[str, CatalogMetric] = Field(default_factory=dict)
    dimensions: dict[str, CatalogDimension] = Field(default_factory=dict)
    macros: dict[str, CatalogMacro] = Field(default_factory=dict)
    rules: dict[str, CatalogRule] = Field(default_factory=dict)

    def metric(self, name: str) -> CatalogMetric:
        return self.metrics[name]

    def dimension(self, name: str) -> CatalogDimension:
        return self.dimensions[name]

    def rule_descriptions(self, rule_names: list[str]) -> list[str]:
        descriptions: list[str] = []
        for name in rule_names:
            rule = self.rules.get(name)
            if rule:
                descriptions.append(f"{name}: {rule.description.strip()}")
        return descriptions


@lru_cache(maxsize=1)
def load_semantic_catalog(path: str | Path | None = None) -> SemanticCatalog:
    catalog_path = Path(path) if path else CATALOG_PATH
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Semantic catalog must be a mapping: {catalog_path}")
    return SemanticCatalog.model_validate(raw)


def render_catalog_prompt_context(
    metric_names: list[str] | None = None,
    dimension_names: list[str] | None = None,
    rule_names: list[str] | None = None,
) -> str:
    """Render selected catalog entries as compact prompt context."""
    catalog = load_semantic_catalog()
    lines: list[str] = ["[SEMANTIC CATALOG CONTEXT]"]

    if metric_names:
        lines.append("metrics:")
        for name in metric_names:
            metric = catalog.metrics.get(name)
            if metric:
                lines.append(f"- {name}: grain={metric.grain}; type={metric.expression_type}")
                expression = metric.expression or metric.numerator
                if expression:
                    lines.append(f"  expression={expression}")
                if metric.denominator:
                    lines.append(f"  denominator={metric.denominator}")

    if dimension_names:
        lines.append("dimensions:")
        for name in dimension_names:
            dimension = catalog.dimensions.get(name)
            if dimension:
                joins = "; ".join(dimension.joins) if dimension.joins else "none"
                lines.append(f"- {name}: source={dimension.source}; joins={joins}")

    selected_rules = _catalog_rule_names(catalog, rule_names)
    if selected_rules:
        lines.append("rules:")
        for rule_line in catalog.rule_descriptions(selected_rules):
            lines.append(f"- {rule_line}")

    return "\n".join(lines)


def render_catalog_context_for_plan(plan: SemanticPlan | dict) -> str:
    """Render catalog entries relevant to a concrete semantic plan."""
    if isinstance(plan, dict):
        plan = SemanticPlan.model_validate(plan)

    metric_names = [metric.name for metric in plan.metrics]
    dimension_names = [
        _catalog_dimension_name(name) for name in plan.answer_shape.required_dimensions
    ]
    dimension_names = [name for name in dimension_names if name]
    return render_catalog_prompt_context(
        metric_names=metric_names,
        dimension_names=dimension_names,
        rule_names=plan.constraints + plan.null_policy,
    )


def _catalog_rule_names(catalog: SemanticCatalog, rule_names: list[str] | None) -> list[str]:
    if rule_names is None:
        return []
    return [name for name in rule_names if name in catalog.rules]


def _catalog_dimension_name(plan_dimension: str) -> str | None:
    mapping = {
        "estado": "estado_residencia",
        "municipio": "municipio_residencia",
        "hospital": "hospital",
        "procedimento": "procedimento",
        "sexo": "sexo",
        "ano": "ano_internacao",
    }
    return mapping.get(plan_dimension)


def catalog_summary() -> dict[str, Any]:
    """Return stable metadata useful for telemetry and tests."""
    catalog = load_semantic_catalog()
    return {
        "version": catalog.version,
        "metric_count": len(catalog.metrics),
        "dimension_count": len(catalog.dimensions),
        "macro_count": len(catalog.macros),
        "rule_count": len(catalog.rules),
    }
