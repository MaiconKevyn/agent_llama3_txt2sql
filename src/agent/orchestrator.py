"""Simple SQL orchestrator.

The public class name is kept for API/evaluation compatibility, but the runtime
is intentionally small:

question -> schema prompt -> SQL -> execute -> conversational answer
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from ..application.config.simple_config import ApplicationConfig, OrchestratorConfig
from ..utils.logging_setup import LoggingSetup
from .llm_manager import OpenAILLMManager, set_global_llm_manager
from .metrics import MetricsCollector
from .orchestrator_support import (
    AVAILABLE_OPENAI_MODELS,
    build_application_config,
    build_factory_app_config,
    build_health_report,
    build_orchestrator_error_result,
    resolve_database_url,
)
from .simple_agent import SimpleSQLAgent

load_dotenv()


def _orch_config_to_flags(cfg: OrchestratorConfig | None) -> dict[str, Any]:
    """Return ablation flag fields from OrchestratorConfig as a plain dict."""
    return asdict(cfg) if cfg is not None else {}


def _orchestrator_config_from_env() -> OrchestratorConfig:
    """Return a config object that documents the simplified runtime."""
    cfg = OrchestratorConfig()
    cfg.ablation_variant = "simple_agent"
    return cfg


def build_tracing_context(
    *,
    user_query: str,
    project_name: str,
    current_model_metadata: dict[str, Any],
    environment: str,
    query_number: int,
) -> tuple[str, list[str], dict[str, Any]]:
    query_slug = "".join(char if char.isalnum() else "_" for char in user_query.lower()).strip("_")
    query_slug = query_slug[:48]
    run_name = f"{project_name}_{query_number}_{query_slug or 'query'}"
    return (
        run_name,
        ["txt2sql", environment, project_name, "simple-agent"],
        {
            "project_name": project_name,
            "environment": environment,
            "query_number": query_number,
            "model": current_model_metadata,
        },
    )


@dataclass
class ModelConfig:
    provider: str
    model_name: str
    temperature: float = 0.0
    timeout: int = 120
    max_retries: int = 3


class SimpleSQLOrchestrator:
    """Compatibility facade around the simple SQL agent."""

    def __init__(
        self,
        app_config: ApplicationConfig | None = None,
        orchestrator_config: OrchestratorConfig | None = None,
        environment: str = "production",
    ) -> None:
        self.app_config = app_config or ApplicationConfig()
        self.orchestrator_config = orchestrator_config or _orchestrator_config_from_env()
        self.environment = environment
        self._llm_manager: OpenAILLMManager | None = None
        self._simple_agent: SimpleSQLAgent | None = None
        self._current_model: ModelConfig | None = None
        self._metrics = MetricsCollector(max_history=1000)

        self._setup_logging()
        self._initialize_runtime()

    def _setup_logging(self) -> None:
        try:
            self.logger = LoggingSetup.configure_orchestrator_logger(self.environment)
        except Exception as exc:
            from ..utils.logging_config import get_orchestrator_logger

            self.logger = get_orchestrator_logger()
            self.logger.warning("Failed to setup production logger", extra={"error": str(exc)})

    def _initialize_runtime(self) -> None:
        self._llm_manager = OpenAILLMManager(self.app_config)
        set_global_llm_manager(self._llm_manager)
        self._simple_agent = SimpleSQLAgent(self._llm_manager)
        self._current_model = self._create_model_config(
            model_name=self.app_config.llm_model,
            temperature=self.app_config.llm_temperature,
            timeout=self.app_config.llm_timeout,
            max_retries=self.app_config.llm_max_retries,
        )
        self.logger.info(
            "Simple SQL orchestrator initialized",
            extra={
                "environment": self.environment,
                "model": self._current_model.model_name,
                "provider": self._current_model.provider,
            },
        )

    def _create_model_config(
        self,
        *,
        model_name: str,
        temperature: float,
        timeout: int,
        max_retries: int,
    ) -> ModelConfig:
        return ModelConfig(
            provider="openai",
            model_name=model_name,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )

    def _current_model_metadata(self) -> dict[str, Any]:
        if self._current_model is None:
            return {"provider": "openai", "model_name": "unknown", "temperature": None}
        return {
            "provider": self._current_model.provider,
            "model_name": self._current_model.model_name,
            "temperature": self._current_model.temperature,
        }

    def switch_model(
        self,
        model_name: str,
        temperature: float | None = None,
        timeout: int | None = None,
    ) -> bool:
        try:
            new_config = build_application_config(
                self.app_config,
                model_name=model_name,
                temperature=temperature,
                timeout=timeout,
            )
            new_llm_manager = OpenAILLMManager(new_config)
            health = new_llm_manager.health_check()
            if health["status"] != "healthy":
                self.logger.error("Model switch failed", extra={"health": health})
                return False

            self.app_config = new_config
            self._llm_manager = new_llm_manager
            self._simple_agent = SimpleSQLAgent(new_llm_manager)
            set_global_llm_manager(new_llm_manager)
            self._current_model = self._create_model_config(
                model_name=model_name,
                temperature=temperature or new_config.llm_temperature,
                timeout=timeout or new_config.llm_timeout,
                max_retries=new_config.llm_max_retries,
            )
            return True
        except Exception as exc:
            self.logger.error("Model switch failed", extra={"error": str(exc)})
            return False

    def process_query(
        self,
        user_query: str,
        session_id: str | None = None,
        streaming: bool = False,
        config: dict | None = None,
        force_single_query: bool = True,
        run_name: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        chart_from_last_result: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        start_time = time.time()
        query_number = self._metrics.begin_query()
        session_id = session_id or f"session_{int(time.time() * 1000) % 100000}"

        try:
            if self._simple_agent is None:
                raise RuntimeError("Simple agent is not initialized")

            result = self._simple_agent.run(user_query, session_id=session_id)
            execution_time = time.time() - start_time
            result["execution_time"] = execution_time
            result["metadata"] = result.get("metadata", {}) or {}
            result["metadata"].update(
                {
                    "orchestrator": "simple_agent",
                    "orchestrator_v3": False,
                    "current_model": self._current_model_metadata(),
                    "environment": self.environment,
                    "session_id": session_id,
                    "query_number": query_number,
                    "orchestrator_execution_time": execution_time,
                    "force_single_query": force_single_query,
                    "chart_from_last_result": chart_from_last_result,
                }
            )
            if config or run_name or tags or metadata:
                result["metadata"]["caller_config"] = {
                    "config": config or {},
                    "run_name": run_name,
                    "tags": list(tags or []),
                    "metadata": metadata or {},
                }

            self._metrics.record_result(
                user_query,
                result,
                execution_time,
                model_id=f"{self._current_model_metadata()['provider']}/{self._current_model_metadata()['model_name']}",
            )

            if streaming:
                return [
                    {
                        "simple_agent": {
                            "user_query": user_query,
                            "simple_result": result,
                            "current_error": result.get("error_message"),
                        }
                    }
                ]
            return result
        except Exception as exc:
            execution_time = time.time() - start_time
            self._metrics.record_exception(execution_time)
            return build_orchestrator_error_result(
                user_query=user_query,
                execution_time=execution_time,
                error=exc,
                current_model_metadata=self._current_model_metadata(),
                environment=self.environment,
            )

    def process_query_with_tracing(
        self,
        user_query: str,
        session_id: str | None = None,
        run_name: str | None = None,
        project_name: str = "txt2sql-agent",
    ) -> dict[str, Any]:
        if not run_name:
            run_name, tags, metadata = build_tracing_context(
                user_query=user_query,
                project_name=project_name,
                current_model_metadata=self._current_model_metadata(),
                environment=self.environment,
                query_number=self._metrics.total_queries + 1,
            )
        else:
            _, tags, metadata = build_tracing_context(
                user_query=user_query,
                project_name=project_name,
                current_model_metadata=self._current_model_metadata(),
                environment=self.environment,
                query_number=self._metrics.total_queries + 1,
            )
        return self.process_query(
            user_query=user_query,
            session_id=session_id,
            run_name=run_name,
            tags=tags,
            metadata=metadata,
        )

    def get_performance_metrics(self) -> dict[str, Any]:
        llm_health = (
            self._llm_manager.health_check() if self._llm_manager else {"status": "unavailable"}
        )
        return self._metrics.build_snapshot(
            environment=self.environment,
            current_model=self._current_model_metadata(),
            llm_health=llm_health,
            version="simple",
        )

    def get_available_models(self) -> dict[str, list[str]]:
        return {"openai": AVAILABLE_OPENAI_MODELS}

    def get_current_model(self) -> dict[str, Any]:
        if self._llm_manager is None:
            return {"error": "LLM manager not initialized"}
        return {
            **self._llm_manager.get_model_info(),
            "orchestrator_config": self._current_model_metadata(),
        }

    def health_check(self) -> dict[str, Any]:
        try:
            llm_health = (
                self._llm_manager.health_check() if self._llm_manager else {"status": "failed"}
            )
            return build_health_report(
                environment=self.environment,
                current_model_metadata=self._current_model_metadata(),
                workflow_available=bool(self._simple_agent),
                llm_health=llm_health,
                metrics=self._metrics,
            )
        except Exception as exc:
            return {
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
                "error": str(exc),
                "orchestrator": {"version": "simple", "error": True},
            }

    def reset_metrics(self) -> None:
        self._metrics.reset()

    def get_workflow_visualization(self, xray: bool = True) -> bytes:
        return b"Simple agent runtime: question -> SQL -> execute -> answer"

    def display_workflow(self, xray: bool = True) -> None:
        print("Simple agent runtime: question -> SQL -> execute -> answer")

    def save_workflow_diagram(self, filename: str = "workflow.txt", xray: bool = True) -> None:
        with open(filename, "wb") as handle:
            handle.write(self.get_workflow_visualization(xray=xray))

    def print_workflow_structure(self) -> None:
        print("question -> schema context -> SQL generation -> SQL execution -> answer")

    def start_interactive_session(self) -> None:
        print("Simple TXT2SQL session. Type 'exit' to finish.")
        while True:
            query = input("> ").strip()
            if query.lower() in {"exit", "quit", "sair"}:
                return
            result = self.process_query(query)
            print(result.get("response") or result.get("error_message"))

    def __str__(self) -> str:
        model = self._current_model_metadata()
        return (
            f"SimpleSQLOrchestrator({self.environment}, "
            f"{model['model_name']}@{model['provider']}, "
            f"queries={self._metrics.total_queries})"
        )


def create_orchestrator(
    provider: str = "openai",
    model_name: str = "gpt-4o-mini",
    environment: str = "production",
    database_url: str | None = None,
) -> SimpleSQLOrchestrator:
    resolved_db_url = resolve_database_url(database_url)
    app_config = build_factory_app_config(
        database_url=resolved_db_url,
        model_name=model_name,
    )
    return SimpleSQLOrchestrator(
        app_config=app_config,
        orchestrator_config=_orchestrator_config_from_env(),
        environment=environment,
    )


def create_production_orchestrator(
    provider: str = "openai",
    model_name: str = "gpt-4o-mini",
) -> SimpleSQLOrchestrator:
    return create_orchestrator(provider=provider, model_name=model_name, environment="production")


def create_development_orchestrator(
    provider: str = "openai",
    model_name: str = "gpt-4o-mini",
) -> SimpleSQLOrchestrator:
    return create_orchestrator(provider=provider, model_name=model_name, environment="development")


LangGraphOrchestrator = SimpleSQLOrchestrator


__all__ = [
    "LangGraphOrchestrator",
    "ModelConfig",
    "SimpleSQLOrchestrator",
    "_orch_config_to_flags",
    "_orchestrator_config_from_env",
    "build_tracing_context",
    "create_orchestrator",
    "create_production_orchestrator",
    "create_development_orchestrator",
]
