"""Minimal OpenAI + SQLDatabase manager for the simple text-to-SQL agent."""

from __future__ import annotations

import os
from typing import Any

from langchain_community.utilities import SQLDatabase
from langchain_core.messages import BaseMessage

from ..application.config.simple_config import ApplicationConfig
from ..utils.logging_config import get_llm_manager_logger
from .runtime_budget import record_llm_call

logger = get_llm_manager_logger()


class OpenAILLMManager:
    """Owns the OpenAI chat client and the database connection."""

    def __init__(self, config: ApplicationConfig):
        self.config = config
        self._llm: Any | None = None
        self._sql_database: SQLDatabase | None = None
        self._initialize_database()
        self._initialize_llm()

    def _initialize_database(self) -> None:
        db_url = self.config.database_path or ""
        if not (db_url.startswith("postgresql") or db_url.startswith("duckdb")):
            raise ValueError("Defina DATABASE_PATH ou DATABASE_URL com uma URL DuckDB valida")

        if db_url.startswith("postgresql+psycopg2://"):
            db_url = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)

        logger.info("Connecting to database", extra={"connection_string": _redact_url(db_url)})
        self._sql_database = SQLDatabase.from_uri(
            db_url,
            lazy_table_reflection=db_url.startswith("duckdb"),
        )
        if not self._sql_database.get_usable_table_names():
            raise ValueError("No usable tables found in database")

    def _initialize_llm(self) -> None:
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self._llm = ChatOpenAI(
            model=self.config.llm_model,
            temperature=self.config.llm_temperature,
            timeout=self.config.llm_timeout,
            max_retries=self.config.llm_max_retries,
            api_key=api_key,
            seed=42,
        )
        logger.info("OpenAI LLM initialized", extra={"model": self.config.llm_model})

    def get_database(self) -> SQLDatabase:
        if self._sql_database is None:
            raise RuntimeError("Database not initialized")
        return self._sql_database

    def invoke_chat(self, messages: list[BaseMessage]) -> Any:
        if self._llm is None:
            raise RuntimeError("LLM not initialized")
        record_llm_call("chat")
        return self._llm.invoke(messages)

    def invoke_chat_structured(self, messages: list[BaseMessage], output_schema: Any) -> Any:
        if self._llm is None:
            raise RuntimeError("LLM not initialized")
        record_llm_call("structured_chat")
        return self._llm.with_structured_output(output_schema).invoke(messages)

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "openai",
            "model_name": self.config.llm_model,
            "temperature": self.config.llm_temperature,
            "timeout": self.config.llm_timeout,
            "available": self._llm is not None,
            "database_connected": self._sql_database is not None,
        }

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._llm and self._sql_database else "degraded",
            "components": {
                "llm_status": "healthy" if self._llm else "failed",
                "database_status": "healthy" if self._sql_database else "failed",
            },
            "model_info": self.get_model_info(),
        }


def _redact_url(db_url: str) -> str:
    try:
        if "://" in db_url and "@" in db_url:
            scheme, rest = db_url.split("://", 1)
            after_at = rest.split("@", 1)[1]
            return f"{scheme}://****@{after_at}"
    except Exception:
        return "[redacted]"
    return db_url


def create_openai_llm_manager(config: ApplicationConfig) -> OpenAILLMManager:
    return OpenAILLMManager(config)


_llm_manager: OpenAILLMManager | None = None


def set_global_llm_manager(manager: OpenAILLMManager) -> None:
    global _llm_manager
    _llm_manager = manager
    logger.info(
        "Global LLM manager updated",
        extra={"provider": "openai", "model": manager.config.llm_model},
    )


def get_llm_manager() -> OpenAILLMManager:
    global _llm_manager
    if _llm_manager is None:
        logger.warning("LLM manager not initialized; creating default instance")
        _llm_manager = OpenAILLMManager(ApplicationConfig())
    return _llm_manager
