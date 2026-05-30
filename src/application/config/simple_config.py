"""Runtime configuration for the simple text-to-SQL chatbot."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class InterfaceType(Enum):
    CLI_BASIC = "cli_basic"
    CLI_INTERACTIVE = "cli_interactive"


def infer_database_type(database_path: str | None) -> str:
    value = (database_path or "").lower()
    if value.startswith("postgresql"):
        return "postgresql"
    return "duckdb"


@dataclass
class ApplicationConfig:
    database_type: str = "duckdb"
    database_path: str | None = field(
        default_factory=lambda: os.getenv("DATABASE_URL") or os.getenv("DATABASE_PATH") or None
    )

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_timeout: int = 120
    llm_max_retries: int = 3

    schema_type: str = "sus"
    ui_type: str = "cli"
    interface_type: InterfaceType = InterfaceType.CLI_INTERACTIVE

    enable_error_logging: bool = True
    error_handling_type: str = "simple"
    query_processing_type: str = "simple"
    prompt_version: str = "simple-v1"


@dataclass
class OrchestratorConfig:
    """Small compatibility config recorded by evaluation outputs."""

    max_query_length: int = 1000
    enable_query_history: bool = True
    enable_statistics: bool = True
    session_timeout: int = 3600
    enable_conversational_response: bool = True
    conversational_fallback: bool = True
    prompt_version: str = "simple-v1"
    ablation_variant: str = "simple_agent"

    # Ignored compatibility flags accepted by older evaluation scripts.
    disable_cot_reasoning: bool = True
    disable_validation: bool = False
    disable_repair: bool = False
    disable_schema_enrichment: bool = True
    disable_rules: bool = False
    disable_semantic_planner: bool = True
    disable_semantic_plan_validation: bool = True
    disable_semantic_contract_validation: bool = True
    disable_semantic_repair_guidance: bool = True
    enable_llamaindex_context: bool = False
    enable_llamaindex_sql_draft: bool = False
    enable_analytic_response_templates: bool = False
    llamaindex_index_dir: str = ".llamaindex_schema"
    llamaindex_top_k_tables: int = 6
    llamaindex_mode: str = "disabled"
    llamaindex_rebuild_index: bool = False
    verify_llamaindex_schema_with_db: bool = False
