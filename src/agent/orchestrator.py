import time
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

from .workflow import (
    execute_sql_workflow,
    stream_sql_workflow
)
from .cli_session import InteractiveSession, WorkflowVisualizer
from .llm_manager import OpenAILLMManager
from .metrics import MetricsCollector
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
from .mlflow_tracker import log_query_run
from ..utils.logging_setup import LoggingSetup
from ..application.config.simple_config import ApplicationConfig, OrchestratorConfig

load_dotenv()


def _orch_config_to_flags(cfg: OrchestratorConfig) -> dict:
    """Return ablation flag fields from OrchestratorConfig as a plain dict."""
    if cfg is None:
        return {}
    import dataclasses
    return {k: v for k, v in dataclasses.asdict(cfg).items()}


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
        environment: str = "production"
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
            self.logger.error("Failed to initialize LangGraph Orchestrator", extra={"error": str(e)})
            raise
    
    def _setup_logging(self):
        """Setup structured logging for production monitoring"""
        try:
            self.logger = LoggingSetup.configure_orchestrator_logger(self.environment)
        except Exception as e:
            from ..utils.logging_config import get_orchestrator_logger

            self.logger = get_orchestrator_logger()
            self.logger.warning("Failed to setup production file handler", extra={"error": str(e)})

    def _current_model_metadata(self) -> Dict[str, Any]:
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
    
    def switch_model(
        self,
        model_name: str,
        temperature: float = None,
        timeout: int = None
    ) -> bool:
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
                max_retries=self.app_config.llm_max_retries
            )

            self.logger.info("Model switched successfully", extra={
                "model": model_name,
                "provider": "openai"
            })
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
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Process a user query using the LangGraph workflow.

        Args:
            user_query: User's natural language question
            session_id: Optional session identifier for checkpointing
            streaming: Whether to return streaming results
            config: Additional LangGraph config (merged with workflow defaults)
            force_single_query: Skip multi-query planner

        Returns:
            Query result dictionary or list of streaming updates
        """
        start_time = time.time()
        query_number = self._metrics.begin_query()

        if session_id is None:
            session_id = f"session_{int(time.time() * 1000) % 100000}"

        self.logger.info("Query started", extra={
            "query_id": query_number,
            "session_id": session_id,
            "user_query": user_query[:100] + "..." if len(user_query) > 100 else user_query,
            "streaming": streaming,
            "model": f"openai/{self._current_model.model_name}",
        })

        try:
            workflow_config = build_workflow_config(config=config, session_id=session_id)

            if streaming:
                results = []
                for update in stream_sql_workflow(
                    workflow=self._workflow,
                    user_query=user_query,
                    session_id=session_id,
                    config=workflow_config,
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
                force_single_query=force_single_query,
                ablation_flags=_orch_config_to_flags(self.orchestrator_config),
            )

            execution_time = time.time() - start_time
            result["execution_time"] = execution_time
            self._metrics.record_result(
                user_query,
                result,
                execution_time,
                model_id=f"{self._current_model.provider}/{self._current_model.model_name}",
            )

            if result.get("success", False):
                self.logger.info("Query completed successfully", extra={
                    "query_id": query_number,
                    "session_id": session_id,
                    "execution_time": execution_time,
                    "row_count": len(result.get("results", [])),
                })
            else:
                self.logger.error("Query failed", extra={
                    "query_id": query_number,
                    "session_id": session_id,
                    "execution_time": execution_time,
                    "error_message": result.get("error_message", "Unknown error"),
                })

            log_query_run(
                result=result,
                session_id=session_id,
                model=self._current_model.model_name,
                environment=self.environment,
                query=user_query,
            )

            result["metadata"] = result.get("metadata", {})
            result["metadata"].update({
                "orchestrator_v3": True,
                "current_model": self._current_model_metadata(),
                "environment": self.environment,
                "session_id": session_id,
                "query_number": query_number,
                "orchestrator_execution_time": execution_time,
            })
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
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics
        
        Returns:
            Dictionary with performance statistics
        """
        llm_health = (
            self._llm_manager.health_check()
            if self._llm_manager
            else {"status": "unavailable"}
        )
        return self._metrics.build_snapshot(
            environment=self.environment,
            current_model=self._current_model_metadata(),
            llm_health=llm_health,
            version="3.0",
        )
    
    def get_available_models(self) -> Dict[str, List[str]]:
        """
        Get list of available models by provider
        
        Returns:
            Dictionary mapping providers to available models
        """
        return {"openai": AVAILABLE_OPENAI_MODELS}
    
    def get_current_model(self) -> Dict[str, Any]:
        """Get current model information"""
        if not self._llm_manager:
            return {"error": "LLM manager not initialized"}
        
        model_info = self._llm_manager.get_model_info()
        model_info.update({
            "orchestrator_config": {
                "provider": self._current_model.provider,
                "model_name": self._current_model.model_name,
                "temperature": self._current_model.temperature,
                "timeout": self._current_model.timeout,
                "max_retries": self._current_model.max_retries
            }
        })
        
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
        project_name: str = "txt2sql-agent"
    ) -> Dict[str, Any]:
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
            metadata=metadata
        )

    def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check for the orchestrator
        
        Returns:
            Health status dictionary
        """
        try:
            llm_health = self._llm_manager.health_check() if self._llm_manager else {"status": "failed"}
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
                "orchestrator": {"version": "3.0", "error": True}
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
    database_url: Optional[str] = None
) -> LangGraphOrchestrator:
    """
    Factory function to create LangGraph Orchestrator
    
    Args:
        provider: LLM provider (only "openai")
        model_name: Model name
        environment: Environment mode
        database_url: PostgreSQL connection URL
        
    Returns:
        Configured LangGraphOrchestrator instance
    """
    
    resolved_db_url = resolve_database_url(database_url)
    app_config = build_factory_app_config(
        database_url=resolved_db_url,
        model_name=model_name,
    )
    
    orchestrator_config = OrchestratorConfig()
    
    return LangGraphOrchestrator(
        app_config=app_config,
        orchestrator_config=orchestrator_config,
        environment=environment
    )


def create_production_orchestrator(
    provider: str = "openai",
    model_name: str = "gpt-4o-mini"
) -> LangGraphOrchestrator:
    """Create production-ready orchestrator"""
    return create_orchestrator(
        provider=provider,
        model_name=model_name,
        environment="production"
    )


def create_development_orchestrator(
    provider: str = "openai",
    model_name: str = "gpt-4o-mini"
) -> LangGraphOrchestrator:
    """Create development orchestrator with debugging"""
    return create_orchestrator(
        provider=provider,
        model_name=model_name,
        environment="development"
    )


# Export main classes and functions
__all__ = [
    "LangGraphOrchestrator",
    "ModelConfig",
    "create_orchestrator",
    "create_production_orchestrator", 
    "create_development_orchestrator"
]
