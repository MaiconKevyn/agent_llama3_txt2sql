"""Root-cause guided semantic SQL repair helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..semantic.error_taxonomy import (
    SemanticErrorCategory,
    SemanticErrorRecord,
    build_semantic_error_record,
)
from ..semantic.plan_schema import SemanticPlan

REPAIR_GUIDANCE_PATH = Path(__file__).parents[1] / "semantic" / "repair_guidance.yml"


class SemanticRepairGuidance(BaseModel):
    title: str
    instruction: str
    contract_focus: list[str] = Field(default_factory=list)
    preserve_scope_filters: bool = True


class SemanticRepairCatalog(BaseModel):
    version: int
    description: str | None = None
    guidance: dict[SemanticErrorCategory, SemanticRepairGuidance]


class SemanticRepairContext(BaseModel):
    error: SemanticErrorRecord
    guidance: SemanticRepairGuidance
    violated_contract: dict
    prompt_block: str


@lru_cache(maxsize=1)
def load_repair_guidance(path: str | Path | None = None) -> SemanticRepairCatalog:
    guidance_path = Path(path) if path else REPAIR_GUIDANCE_PATH
    raw = yaml.safe_load(guidance_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Semantic repair guidance must be a mapping: {guidance_path}")
    return SemanticRepairCatalog.model_validate(raw)


def build_semantic_repair_context(
    error_message: str | None,
    semantic_plan: SemanticPlan | dict | None,
) -> SemanticRepairContext:
    error = build_semantic_error_record(error_message)
    catalog = load_repair_guidance()
    guidance = (
        catalog.guidance.get(error.category) or catalog.guidance[SemanticErrorCategory.UNKNOWN]
    )
    violated_contract = extract_violated_contract(semantic_plan, guidance.contract_focus)
    prompt_block = render_semantic_repair_prompt(error, guidance, violated_contract)
    return SemanticRepairContext(
        error=error,
        guidance=guidance,
        violated_contract=violated_contract,
        prompt_block=prompt_block,
    )


def extract_violated_contract(
    semantic_plan: SemanticPlan | dict | None,
    focus_paths: list[str],
) -> dict:
    if semantic_plan is None:
        return {}
    if isinstance(semantic_plan, SemanticPlan):
        plan_data = semantic_plan.model_dump(exclude_none=True)
    else:
        plan_data = SemanticPlan.model_validate(semantic_plan).model_dump(exclude_none=True)

    if not focus_paths:
        return plan_data

    contract: dict[str, object] = {}
    for path in focus_paths:
        value = _get_path(plan_data, path)
        if value is not None:
            contract[path] = value
    return contract


def render_semantic_repair_prompt(
    error: SemanticErrorRecord,
    guidance: SemanticRepairGuidance,
    violated_contract: dict,
) -> str:
    contract_lines = (
        "\n".join(f"- {key}: {value}" for key, value in violated_contract.items())
        if violated_contract
        else "- semantic_plan: nao disponivel"
    )
    preserve = (
        "Preserve todos os filtros de escopo corretos da pergunta."
        if guidance.preserve_scope_filters
        else "Reavalie filtros de escopo se eles violarem o contrato."
    )
    return (
        f"[SEMANTIC REPAIR]\n"
        f"category: {error.category.value}\n"
        f"title: {guidance.title}\n"
        f"error: {error.message}\n"
        f"instruction: {guidance.instruction.strip()}\n"
        f"{preserve}\n"
        f"violated_contract:\n{contract_lines}"
    )


def _get_path(data: dict, path: str) -> object | None:
    current: object = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list):
            values = []
            for item in current:
                if isinstance(item, dict) and part in item:
                    values.append(item[part])
            return values or None
        return None
    return current
