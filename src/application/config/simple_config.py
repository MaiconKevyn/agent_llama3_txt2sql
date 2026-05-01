from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import os

class InterfaceType(Enum):
    """Interface type configuration"""
    CLI_BASIC = "cli_basic"
    CLI_INTERACTIVE = "cli_interactive"


@dataclass
class ApplicationConfig:
    """Simple configuration for the application"""
    # Database configuration (loaded from environment when available)
    database_type: str = "postgresql"
    database_path: Optional[str] = field(
        default_factory=lambda: (
            os.getenv("DATABASE_URL")
            or os.getenv("DATABASE_PATH")
            or None
        )
    )
    
    # LLM configuration (for SQL generation)
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_timeout: int = 120
    llm_max_retries: int = 3

    # Conversational LLM configuration (share same model by default)
    conversational_llm_model: str = "gpt-4o-mini"
    conversational_llm_temperature: float = 0.7
    conversational_llm_max_tokens: int = 1000
    conversational_llm_timeout: int = 60
    conversational_llm_max_retries: int = 3

    # Schema configuration
    schema_type: str = "sus"
    
    # UI configuration
    ui_type: str = "cli"
    interface_type: InterfaceType = InterfaceType.CLI_INTERACTIVE
    
    # Error handling configuration
    error_handling_type: str = "comprehensive"
    enable_error_logging: bool = True
    
    # Query processing configuration
    query_processing_type: str = "comprehensive"
    
    # Query classification configuration
    enable_query_classification: bool = True
    query_classification_confidence_threshold: float = 0.7
    # Prompt versioning (mirrors OrchestratorConfig.prompt_version)
    prompt_version: str = "v1"

@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator"""
    max_query_length: int = 1000
    enable_query_history: bool = True
    enable_statistics: bool = True
    session_timeout: int = 3600  # seconds
    enable_conversational_response: bool = True
    conversational_fallback: bool = True
    enable_query_routing: bool = True
    routing_confidence_threshold: float = 0.7
    # Prompt versioning — bump when RULES A-O or prompt templates change.
    # Stored in every evaluation result so runs are comparable across versions.
    prompt_version: str = "v1"
