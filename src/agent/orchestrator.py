import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from ..application.config.simple_config import ApplicationConfig, OrchestratorConfig
from ..utils.logging_setup import LoggingSetup
from ..visualization import (
    build_chart_plan,
    build_chart_planning_input,
    detect_visualization_intent,
    plan_chart,
)
from ..visualization.renderer_contract import build_chart_response
from ..visualization.schema import ChartPlan, ChartSpec, VisualizationIntent
from .cli_session import InteractiveSession, WorkflowVisualizer
from .llamaindex_context import normalize_llamaindex_mode
from .llm_manager import OpenAILLMManager
from .metrics import MetricsCollector
from .mlflow_tracker import log_query_run
from .orchestrator_support import (
    AVAILABLE_OPENAI_MODELS,
    build_application_config,
    build_factory_app_config,
    build_health_report,
    build_orchestrator_error_result,
    build_workflow_config,
    initialize_orchestrator_runtime,
    resolve_database_url,
)
from .workflow import execute_sql_workflow, stream_sql_workflow

load_dotenv()


def _orch_config_to_flags(cfg: OrchestratorConfig) -> dict:
    """Return ablation flag fields from OrchestratorConfig as a plain dict."""
    if cfg is None:
        return {}
    import dataclasses

    return {k: v for k, v in dataclasses.asdict(cfg).items()}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _orchestrator_config_from_env() -> OrchestratorConfig:
    """Create optional experimental flags for API/factory-created orchestrators."""
    mode = normalize_llamaindex_mode(os.getenv("LLAMAINDEX_MODE") or "context")
    return OrchestratorConfig(
        enable_llamaindex_context=_env_bool("ENABLE_LLAMAINDEX_CONTEXT")
        or mode in {"context", "sql_draft", "hybrid"},
        enable_llamaindex_sql_draft=_env_bool("ENABLE_LLAMAINDEX_SQL_DRAFT") or mode == "sql_draft",
        enable_analytic_response_templates=_env_bool(
            "ENABLE_ANALYTIC_RESPONSE_TEMPLATES", True
        ),
        llamaindex_mode=mode,
        llamaindex_top_k_tables=_env_int("LLAMAINDEX_TOP_K_TABLES", 6),
        llamaindex_index_dir=os.getenv("LLAMAINDEX_INDEX_DIR", ".llamaindex_schema"),
        llamaindex_rebuild_index=_env_bool("LLAMAINDEX_REBUILD_INDEX"),
        verify_llamaindex_schema_with_db=_env_bool("VERIFY_LLAMAINDEX_SCHEMA_WITH_DB"),
    )


def build_tracing_context(
    *,
    user_query: str,
    project_name: str,
    current_model_metadata: dict[str, Any],
    environment: str,
    query_number: int,
) -> tuple[str, list[str], dict[str, Any]]:
    query_slug = "".join(char if char.isalnum() else "_" for char in user_query.lower()).strip("_")[
        :48
    ]
    run_name = f"{project_name}_{query_number}_{query_slug or 'query'}"
    return (
        run_name,
        ["txt2sql", environment, project_name],
        {
            "project_name": project_name,
            "environment": environment,
            "query_number": query_number,
            "model": current_model_metadata,
        },
    )


@dataclass
class ModelConfig:
    """Configuration for OpenAI model"""

    provider: str  # always "openai"
    model_name: str  # e.g., gpt-4o-mini
    temperature: float = 0.1
    timeout: int = 30
    max_retries: int = 3


class LangGraphOrchestrator:
    """
    Main Orchestrator for LangGraph V3 SQL Agent

    This is the primary interface that provides:
    - Easy LLM model switching
    - Production-ready SQL Agent workflow
    - Complete API compatibility with legacy system
    - Official LangGraph best practices
    - Performance monitoring and metrics
    """

    def __init__(
        self,
        app_config: ApplicationConfig = None,
        orchestrator_config: OrchestratorConfig = None,
        environment: str = "production",
    ):
        """
        Initialize LangGraph Orchestrator

        Args:
            app_config: Application configuration
            orchestrator_config: Orchestrator configuration
            environment: "production", "development", or "testing"
        """

        # Configuration
        self.app_config = app_config or ApplicationConfig()
        self.orchestrator_config = orchestrator_config or OrchestratorConfig()
        self.environment = environment

        # State
        self._workflow = None
        self._memory = None
        self._memory_conn = None
        self._llm_manager = None
        self._current_model = None
        self._metrics = MetricsCollector(max_history=1000)
        self._last_result_by_session: dict[str, dict[str, Any]] = {}

        # Setup structured logging first
        self._setup_logging()

        # Initialize workflow
        self._initialize_workflow()

    def _initialize_workflow(self):
        """Initialize the appropriate workflow based on environment"""
        try:
            (
                self._workflow,
                self._memory,
                self._memory_conn,
                self._llm_manager,
                self._current_model,
            ) = initialize_orchestrator_runtime(
                self.app_config,
                self.environment,
                self.logger,
                self._create_model_config,
                orchestrator_config=self.orchestrator_config,
            )
        except Exception as e:
            self.logger.error(
                "Failed to initialize LangGraph Orchestrator", extra={"error": str(e)}
            )
            raise

    def _setup_logging(self):
        """Setup structured logging for production monitoring"""
        try:
            self.logger = LoggingSetup.configure_orchestrator_logger(self.environment)
        except Exception as e:
            from ..utils.logging_config import get_orchestrator_logger

            self.logger = get_orchestrator_logger()
            self.logger.warning("Failed to setup production file handler", extra={"error": str(e)})

    def _current_model_metadata(self) -> dict[str, Any]:
        return {
            "provider": self._current_model.provider,
            "model_name": self._current_model.model_name,
            "temperature": self._current_model.temperature,
        }

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

    def switch_model(self, model_name: str, temperature: float = None, timeout: int = None) -> bool:
        """Switch to a different OpenAI model."""
        try:
            self.logger.info("Switching model", extra={"model": model_name, "provider": "openai"})

            new_config = build_application_config(
                self.app_config,
                model_name=model_name,
                temperature=temperature,
                timeout=timeout,
            )

            new_llm_manager = OpenAILLMManager(new_config)
            test_result = new_llm_manager.health_check()
            if test_result["status"] != "healthy":
                self.logger.error("Model switch failed", extra={"test_result": test_result})
                return False

            self.app_config = new_config
            self._llm_manager = new_llm_manager

            from .nodes import set_global_llm_manager

            set_global_llm_manager(new_llm_manager)

            self._current_model = self._create_model_config(
                model_name=model_name,
                temperature=temperature or self.app_config.llm_temperature,
                timeout=timeout or self.app_config.llm_timeout,
                max_retries=self.app_config.llm_max_retries,
            )

            self.logger.info(
                "Model switched successfully", extra={"model": model_name, "provider": "openai"}
            )
            return True

        except Exception as e:
            self.logger.error("Model switch failed", extra={"error": str(e)})
            return False

    def process_query(
        self,
        user_query: str,
        session_id: str = None,
        streaming: bool = False,
        config: dict = None,
        force_single_query: bool = False,
        run_name: str = None,
        tags: list[str] = None,
        metadata: dict[str, Any] = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Process a user query using the LangGraph workflow.

        Args:
            user_query: User's natural language question
            session_id: Optional session identifier for checkpointing
            streaming: Whether to return streaming results
            config: Additional LangGraph config (merged with workflow defaults)
            force_single_query: Skip multi-query planner
            run_name: Optional LangSmith/LangGraph run name
            tags: Optional tracing tags
            metadata: Optional tracing metadata

        Returns:
            Query result dictionary or list of streaming updates
        """
        start_time = time.time()
        query_number = self._metrics.begin_query()

        if session_id is None:
            session_id = f"session_{int(time.time() * 1000) % 100000}"

        self.logger.info(
            "Query started",
            extra={
                "query_id": query_number,
                "session_id": session_id,
                "user_query": user_query[:100] + "..." if len(user_query) > 100 else user_query,
                "streaming": streaming,
                "model": f"openai/{self._current_model.model_name}",
            },
        )

        try:
            visualization_intent = detect_visualization_intent(user_query)
            chart_plan = build_chart_plan(user_query, visualization_intent)
            effective_force_single_query = force_single_query or visualization_intent.requested
            if visualization_intent.requested and visualization_intent.uses_last_result:
                cached_result = self._last_result_by_session.get(session_id)
                if cached_result:
                    return self._build_followup_chart_result(
                        user_query=user_query,
                        session_id=session_id,
                        visualization_intent=visualization_intent,
                        cached_result=cached_result,
                        started_at=start_time,
                    )
                return self._build_missing_chart_context_result(
                    user_query=user_query,
                    session_id=session_id,
                    visualization_intent=visualization_intent,
                    started_at=start_time,
                )

            workflow_config = build_workflow_config(config=config, session_id=session_id)
            if run_name:
                workflow_config["run_name"] = run_name
            if tags:
                workflow_config["tags"] = list(tags)
            if metadata:
                workflow_config.setdefault("metadata", {}).update(metadata)

            if streaming:
                results = []
                for update in stream_sql_workflow(
                    workflow=self._workflow,
                    user_query=user_query,
                    session_id=session_id,
                    config=workflow_config,
                    force_single_query=effective_force_single_query,
                    ablation_flags=_orch_config_to_flags(self.orchestrator_config),
                    visualization_intent=visualization_intent.model_dump(mode="json"),
                    chart_plan=chart_plan.model_dump(mode="json"),
                ):
                    results.append(update)
                execution_time = time.time() - start_time
                self._metrics.record_streaming_success(execution_time)
                return results

            result = execute_sql_workflow(
                workflow=self._workflow,
                user_query=user_query,
                session_id=session_id,
                config=workflow_config,
                force_single_query=effective_force_single_query,
                ablation_flags=_orch_config_to_flags(self.orchestrator_config),
                visualization_intent=visualization_intent.model_dump(mode="json"),
                chart_plan=chart_plan.model_dump(mode="json"),
            )

            execution_time = time.time() - start_time
            result["execution_time"] = execution_time
            result = self._attach_visualization_if_requested(
                result=result,
                user_query=user_query,
                visualization_intent=visualization_intent,
                chart_plan=chart_plan,
            )
            self._remember_result_if_available(session_id=session_id, result=result)
            self._metrics.record_result(
                user_query,
                result,
                execution_time,
                model_id=f"{self._current_model.provider}/{self._current_model.model_name}",
            )

            if result.get("success", False):
                self.logger.info(
                    "Query completed successfully",
                    extra={
                        "query_id": query_number,
                        "session_id": session_id,
                        "execution_time": execution_time,
                        "row_count": len(result.get("results", [])),
                    },
                )
            else:
                self.logger.error(
                    "Query failed",
                    extra={
                        "query_id": query_number,
                        "session_id": session_id,
                        "execution_time": execution_time,
                        "error_message": result.get("error_message", "Unknown error"),
                    },
                )

            log_query_run(
                result=result,
                session_id=session_id,
                model=self._current_model.model_name,
                environment=self.environment,
                query=user_query,
            )

            result["metadata"] = result.get("metadata", {})
            result["metadata"].update(
                {
                    "orchestrator_v3": True,
                    "current_model": self._current_model_metadata(),
                    "environment": self.environment,
                    "session_id": session_id,
                    "query_number": query_number,
                    "orchestrator_execution_time": execution_time,
                }
            )
            return result

        except Exception as e:
            execution_time = time.time() - start_time
            self._metrics.record_exception(execution_time)
            return build_orchestrator_error_result(
                user_query=user_query,
                execution_time=execution_time,
                error=e,
                current_model_metadata=self._current_model_metadata(),
                environment=self.environment,
            )

    def _attach_visualization_if_requested(
        self,
        *,
        result: dict[str, Any],
        user_query: str,
        visualization_intent: VisualizationIntent,
        chart_plan: ChartPlan | None = None,
    ) -> dict[str, Any]:
        """Attach a validated chart payload only for explicit chart requests."""

        result["metadata"] = result.get("metadata", {}) or {}
        result["metadata"]["visualization_intent"] = visualization_intent.model_dump(mode="json")
        if chart_plan is not None:
            result["metadata"]["chart_plan"] = chart_plan.model_dump(mode="json")

        if not visualization_intent.requested:
            result["chart"] = None
            return result

        chart_spec = self._plan_chart_for_result(
            user_query=user_query,
            result=result,
            visualization_intent=visualization_intent,
            chart_plan=chart_plan,
        )
        result["chart"] = build_chart_response(intent=visualization_intent, spec=chart_spec)
        result["metadata"]["chart_spec"] = (
            chart_spec.model_dump(mode="json") if chart_spec else None
        )
        self._append_chart_notice_to_response(result=result, chart_spec=chart_spec)
        return result

    def _append_chart_notice_to_response(
        self,
        *,
        result: dict[str, Any],
        chart_spec: ChartSpec | None,
    ) -> None:
        if not chart_spec or not chart_spec.warnings:
            return
        notices = [
            warning.message
            for warning in chart_spec.warnings
            if warning.code == "excluded_unfilled_category"
        ]
        if not notices:
            return
        notice = f"Observacao: {notices[0]}"
        response = result.get("response") or ""
        if "nao preenchido" in response.lower() or "não preenchido" in response.lower():
            result["response"] = (
                "Grafico gerado considerando apenas registros com causa, diagnostico "
                "ou motivo preenchido.\n\n"
                f"{notice}"
            )
            return
        if notice not in response:
            result["response"] = f"{response}\n\n{notice}" if response else notice

    def _plan_chart_for_result(
        self,
        *,
        user_query: str,
        result: dict[str, Any],
        visualization_intent: VisualizationIntent,
        chart_plan: ChartPlan | None = None,
    ) -> ChartSpec | None:
        if not result.get("success") or not result.get("results"):
            return ChartSpec(
                chartable=False,
                chart_type="table",
                reason="Sem resultado tabular validado para gerar grafico.",
            )
        try:
            planning_input = build_chart_planning_input(
                user_query=user_query,
                sql_query=result.get("sql_query"),
                results=result.get("results") or [],
                row_count=int(result.get("row_count") or len(result.get("results") or [])),
                semantic_plan=(result.get("metadata") or {}).get("semantic_plan"),
                chart_hint=visualization_intent.chart_hint,
                chart_plan=chart_plan or (result.get("metadata") or {}).get("chart_plan"),
            )
            return plan_chart(planning_input)
        except Exception as exc:
            self.logger.warning("Chart planning failed", extra={"error": str(exc)})
            return ChartSpec(
                chartable=False,
                chart_type="table",
                data=[],
                reason=f"Nao foi possivel gerar grafico validado: {exc}",
            )

    def _remember_result_if_available(self, *, session_id: str, result: dict[str, Any]) -> None:
        if not result.get("success") or not result.get("results"):
            return
        self._last_result_by_session[session_id] = {
            "response": result.get("response"),
            "sql_query": result.get("sql_query"),
            "results": result.get("results") or [],
            "row_count": result.get("row_count") or len(result.get("results") or []),
            "metadata": result.get("metadata") or {},
        }

    def _build_followup_chart_result(
        self,
        *,
        user_query: str,
        session_id: str,
        visualization_intent: VisualizationIntent,
        cached_result: dict[str, Any],
        started_at: float,
    ) -> dict[str, Any]:
        base_result = {
            "success": True,
            "question": user_query,
            "sql_query": cached_result.get("sql_query"),
            "results": cached_result.get("results") or [],
            "row_count": cached_result.get("row_count") or len(cached_result.get("results") or []),
            "execution_time": time.time() - started_at,
            "error_message": None,
            "response": "Grafico gerado a partir do ultimo resultado da sessao.",
            "timestamp": datetime.now().isoformat(),
            "final_result_rows": None,
            "metadata": {
                **(cached_result.get("metadata") or {}),
                "session_id": session_id,
                "visualization_followup": True,
            },
        }
        return self._attach_visualization_if_requested(
            result=base_result,
            user_query=user_query,
            visualization_intent=visualization_intent,
        )

    def _build_missing_chart_context_result(
        self,
        *,
        user_query: str,
        session_id: str,
        visualization_intent: VisualizationIntent,
        started_at: float,
    ) -> dict[str, Any]:
        chart_payload = build_chart_response(intent=visualization_intent, spec=None)
        return {
            "success": True,
            "question": user_query,
            "sql_query": None,
            "results": [],
            "row_count": 0,
            "execution_time": time.time() - started_at,
            "error_message": None,
            "response": (
                "Para gerar um grafico disso, primeiro preciso de uma resposta de dados "
                "na mesma sessao."
            ),
            "timestamp": datetime.now().isoformat(),
            "final_result_rows": None,
            "chart": chart_payload,
            "metadata": {
                "session_id": session_id,
                "visualization_intent": visualization_intent.model_dump(mode="json"),
                "visualization_missing_context": True,
            },
        }

    def get_performance_metrics(self) -> dict[str, Any]:
        """
        Get comprehensive performance metrics

        Returns:
            Dictionary with performance statistics
        """
        llm_health = (
            self._llm_manager.health_check() if self._llm_manager else {"status": "unavailable"}
        )
        return self._metrics.build_snapshot(
            environment=self.environment,
            current_model=self._current_model_metadata(),
            llm_health=llm_health,
            version="3.0",
        )

    def get_available_models(self) -> dict[str, list[str]]:
        """
        Get list of available models by provider

        Returns:
            Dictionary mapping providers to available models
        """
        return {"openai": AVAILABLE_OPENAI_MODELS}

    def get_current_model(self) -> dict[str, Any]:
        """Get current model information"""
        if not self._llm_manager:
            return {"error": "LLM manager not initialized"}

        model_info = self._llm_manager.get_model_info()
        model_info.update(
            {
                "orchestrator_config": {
                    "provider": self._current_model.provider,
                    "model_name": self._current_model.model_name,
                    "temperature": self._current_model.temperature,
                    "timeout": self._current_model.timeout,
                    "max_retries": self._current_model.max_retries,
                }
            }
        )

        return model_info

    def get_workflow_visualization(self, xray: bool = True) -> bytes:
        """Generate workflow visualization using LangGraph's built-in method."""
        return WorkflowVisualizer.get_workflow_visualization(self._workflow, xray=xray)

    def display_workflow(self, xray: bool = True):
        """Display workflow in Jupyter notebook."""
        WorkflowVisualizer.display_workflow(self._workflow, self.logger, xray=xray)

    def save_workflow_diagram(self, filename: str = "workflow.png", xray: bool = True):
        """Save workflow diagram to file."""
        WorkflowVisualizer.save_workflow_diagram(
            self._workflow,
            self.logger,
            filename=filename,
            xray=xray,
        )

    def print_workflow_structure(self):
        """Print text representation of workflow structure"""
        WorkflowVisualizer.print_workflow_structure(self._workflow, self.logger)

    def process_query_with_tracing(
        self,
        user_query: str,
        session_id: str = None,
        run_name: str = None,
        project_name: str = "txt2sql-agent",
    ) -> dict[str, Any]:
        """
        Process a query with enriched tracing metadata.

        Args:
            user_query: User's natural language question
            session_id: Optional session identifier
            run_name: Custom name for the trace
            project_name: Logical project name stored in tracing metadata

        Returns:
            Query result with enhanced tracing metadata
        """
        # Generate meaningful run name if not provided
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

        # Execute with tracing
        return self.process_query(
            user_query=user_query,
            session_id=session_id,
            run_name=run_name,
            tags=tags,
            metadata=metadata,
        )

    def health_check(self) -> dict[str, Any]:
        """
        Comprehensive health check for the orchestrator

        Returns:
            Health status dictionary
        """
        try:
            llm_health = (
                self._llm_manager.health_check() if self._llm_manager else {"status": "failed"}
            )
            return build_health_report(
                environment=self.environment,
                current_model_metadata=self._current_model_metadata(),
                workflow_available=bool(self._workflow),
                llm_health=llm_health,
                metrics=self._metrics,
            )
        except Exception as e:
            return {
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "orchestrator": {"version": "3.0", "error": True},
            }

    def reset_metrics(self):
        """Reset performance metrics"""
        self._metrics.reset()
        self.logger.info("Performance metrics reset")

    def start_interactive_session(self):
        """Start the interactive CLI session."""
        InteractiveSession.start(self, self.logger, self.environment)

    def __del__(self):
        """Close SQLite connection on garbage collection."""
        try:
            if self._memory_conn is not None:
                self._memory_conn.close()
        except Exception:
            pass

    def __str__(self) -> str:
        """String representation of orchestrator"""
        return (
            f"LangGraphOrchestrator(v3.0, {self.environment}, "
            f"{self._current_model.model_name}@{self._current_model.provider}, "
            f"queries={self._metrics.total_queries})"
        )


# Factory functions for easy instantiation
def create_orchestrator(
    provider: str = "openai",
    model_name: str = "gpt-4o-mini",
    environment: str = "production",
    database_url: str | None = None,
) -> LangGraphOrchestrator:
    """
    Factory function to create LangGraph Orchestrator

    Args:
        provider: LLM provider (only "openai")
        model_name: Model name
        environment: Environment mode
        database_url: DuckDB SQLAlchemy URL

    Returns:
        Configured LangGraphOrchestrator instance
    """

    resolved_db_url = resolve_database_url(database_url)
    app_config = build_factory_app_config(
        database_url=resolved_db_url,
        model_name=model_name,
    )

    orchestrator_config = _orchestrator_config_from_env()

    return LangGraphOrchestrator(
        app_config=app_config, orchestrator_config=orchestrator_config, environment=environment
    )


def create_production_orchestrator(
    provider: str = "openai", model_name: str = "gpt-4o-mini"
) -> LangGraphOrchestrator:
    """Create production-ready orchestrator"""
    return create_orchestrator(provider=provider, model_name=model_name, environment="production")


def create_development_orchestrator(
    provider: str = "openai", model_name: str = "gpt-4o-mini"
) -> LangGraphOrchestrator:
    """Create development orchestrator with debugging"""
    return create_orchestrator(provider=provider, model_name=model_name, environment="development")


# Export main classes and functions
__all__ = [
    "LangGraphOrchestrator",
    "ModelConfig",
    "create_orchestrator",
    "create_production_orchestrator",
    "create_development_orchestrator",
]
