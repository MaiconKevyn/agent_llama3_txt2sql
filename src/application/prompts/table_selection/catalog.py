"""Versioned table-selection prompt and description catalog."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ...config.table_descriptions import TABLE_DESCRIPTIONS

CATALOG_PATH = Path(__file__).with_name("variants.yml")


@lru_cache(maxsize=1)
def load_table_selection_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid table selection catalog in {CATALOG_PATH}")
    return data


def get_available_description_variants() -> list[str]:
    catalog = load_table_selection_catalog()
    return list(catalog.get("description_variants", {}).keys())


def get_available_prompt_variants() -> list[str]:
    catalog = load_table_selection_catalog()
    return list(catalog.get("prompt_variants", {}).keys())


def get_available_table_selection_presets() -> list[str]:
    catalog = load_table_selection_catalog()
    return list(catalog.get("presets", {}).keys())


def resolve_table_selection_strategy(
    *,
    preset_name: str | None = None,
    mode: str | None = None,
    description_variant: str | None = None,
    prompt_variant: str | None = None,
) -> dict[str, str]:
    catalog = load_table_selection_catalog()
    presets = catalog.get("presets", {})
    selected_preset = preset_name or "llm_best"
    preset_cfg = presets.get(selected_preset)
    if not preset_cfg:
        raise ValueError(f"Unknown table selection preset: {selected_preset}")

    return {
        "preset_name": selected_preset,
        "mode": mode or preset_cfg["mode"],
        "description_variant": description_variant or preset_cfg["description_variant"],
        "prompt_variant": prompt_variant or preset_cfg["prompt_variant"],
    }


def _join_items(values: Iterable[str]) -> str:
    return ", ".join(value for value in values if value)


def _resolve_source_value(
    source: str,
    table_name: str,
    desc: dict[str, Any],
    metadata: dict[str, Any],
) -> Any:
    if source == "join_hint":
        relationships = desc.get("relationships", [])
        return relationships[0] if relationships else "join_path=none"
    if source == "role_hint":
        return metadata.get("role_hints", {}).get(table_name, desc.get("title", table_name))
    if source == "grain_hint":
        return metadata.get("grain_hints", {}).get(table_name, "grain=unknown")
    if source == "do_not_use_hint":
        return metadata.get("do_not_use_hints", {}).get(table_name, "do_not_use=not specified")
    return desc.get(source)


def render_table_description_lines(
    available_tables: list[str],
    description_variant: str,
) -> list[str]:
    catalog = load_table_selection_catalog()
    variant_cfg = catalog.get("description_variants", {}).get(description_variant)
    if not variant_cfg:
        raise ValueError(f"Unknown table description variant: {description_variant}")

    metadata = catalog.get("metadata", {})
    lines: list[str] = []

    for table_name in available_tables:
        desc = TABLE_DESCRIPTIONS.get(table_name)
        if not desc:
            lines.append(f"- {table_name}: Database table")
            continue

        title = desc.get("title", table_name)
        context: dict[str, Any] = {
            "table_name": table_name,
            "title": title,
            "role_hint": metadata.get("role_hints", {}).get(table_name, title),
        }

        for section_name, section_cfg in variant_cfg.get("sections", {}).items():
            source = section_cfg["source"]
            raw_value = _resolve_source_value(source, table_name, desc, metadata)

            rendered = ""
            if isinstance(raw_value, list):
                max_items = int(section_cfg.get("max_items", len(raw_value)))
                items = _join_items(raw_value[:max_items])
                if items:
                    rendered = section_cfg["template"].format(items=items, value=items)
            elif raw_value:
                rendered = section_cfg["template"].format(value=raw_value)

            context[f"{section_name}_section"] = rendered

        for section_name in variant_cfg.get("sections", {}):
            context.setdefault(f"{section_name}_section", "")

        line = variant_cfg["line_template"].format(**context).strip()
        lines.append(line)

    return lines


def render_table_selection_prompt(
    user_query: str,
    available_tables: list[str],
    description_variant: str,
    prompt_variant: str,
) -> str:
    catalog = load_table_selection_catalog()
    prompt_cfg = catalog.get("prompt_variants", {}).get(prompt_variant)
    if not prompt_cfg:
        raise ValueError(f"Unknown table selection prompt variant: {prompt_variant}")

    table_descriptions = "\n".join(
        render_table_description_lines(
            available_tables,
            description_variant=description_variant,
        )
    )

    return prompt_cfg["template"].format(
        table_descriptions=table_descriptions,
        user_query=user_query,
    )
