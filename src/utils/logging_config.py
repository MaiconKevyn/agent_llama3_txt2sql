"""
Centralized logging configuration for TXT2SQL System

Production-ready logging with RotatingFileHandler, structured output,
and proper log levels for different components.
"""

import json
import logging
import logging.handlers
import os
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging with JSON output option"""

    def __init__(self, include_json: bool = False):
        self.include_json = include_json
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        # Base formatting
        timestamp = datetime.fromtimestamp(record.created).isoformat()

        # Build structured message
        log_data = {
            "timestamp": timestamp,
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "getMessage",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                ]:
                    log_data[key] = value

        if self.include_json:
            return json.dumps(log_data, ensure_ascii=False)
        else:
            # Human-readable format for console
            extra_info = ""
            if hasattr(record, "query_id"):
                extra_info += f" [query_id={record.query_id}]"
            if hasattr(record, "execution_time"):
                extra_info += f" [time={record.execution_time:.3f}s]"

            return f"{timestamp} - {record.name} - {record.levelname} - {record.getMessage()}{extra_info}"


class TXT2SQLLogger:
    """Centralized logger factory for TXT2SQL system"""

    _loggers: dict[str, logging.Logger] = {}
    _initialized: bool = False

    @classmethod
    def setup_logging(
        cls,
        log_level: str = "INFO",
        log_dir: str = "logs",
        max_bytes: int = 100 * 1024 * 1024,  # 100MB
        backup_count: int = 10,
        enable_console: bool = True,
        enable_file: bool = True,
        json_format: bool = False,
    ) -> None:
        """
        Setup centralized logging configuration

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_dir: Directory for log files
            max_bytes: Max size per log file before rotation
            backup_count: Number of backup files to keep
            enable_console: Enable console logging
            enable_file: Enable file logging
            json_format: Use JSON format for file logs
        """

        if cls._initialized:
            return

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

        # Set root logger level
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))

        # Clear existing handlers to avoid duplicates
        root_logger.handlers.clear()

        # Console handler
        if enable_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, log_level.upper()))
            console_formatter = StructuredFormatter(include_json=False)
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

        # File handlers for different components
        if enable_file:
            components = [
                "txt2sql.orchestrator",
                "txt2sql.nodes",
                "txt2sql.llm_manager",
                "txt2sql.api",
                "txt2sql.cli",
            ]

            for component in components:
                cls._setup_file_handler(
                    component, log_dir, max_bytes, backup_count, log_level, json_format
                )

        cls._initialized = True

    @classmethod
    def _setup_file_handler(
        cls,
        component: str,
        log_dir: str,
        max_bytes: int,
        backup_count: int,
        log_level: str,
        json_format: bool,
    ) -> None:
        """Setup rotating file handler for a component"""

        # Create component-specific logger
        logger = logging.getLogger(component)

        # File handler with rotation
        log_file = os.path.join(log_dir, f"{component.replace('.', '_')}.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )

        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_formatter = StructuredFormatter(include_json=json_format)
        file_handler.setFormatter(file_formatter)

        logger.addHandler(file_handler)

    @classmethod
    def get_logger(cls, component: str) -> logging.Logger:
        """
        Get logger for a specific component

        Args:
            component: Component name (e.g., 'nodes', 'llm_manager', 'api')

        Returns:
            Configured logger instance
        """

        # Ensure logging is initialized
        if not cls._initialized:
            cls.setup_logging()

        # Full component name for logger hierarchy
        full_name = f"txt2sql.{component}"

        if full_name not in cls._loggers:
            cls._loggers[full_name] = logging.getLogger(full_name)

        return cls._loggers[full_name]

    @classmethod
    def log_with_context(cls, logger: logging.Logger, level: str, message: str, **context) -> None:
        """
        Log message with structured context

        Args:
            logger: Logger instance
            level: Log level (info, debug, error, warning)
            message: Log message
            **context: Additional context fields
        """

        log_method = getattr(logger, level.lower())
        log_method(message, extra=context)


# Convenience functions for quick logger access
def get_nodes_logger() -> logging.Logger:
    """Get logger for nodes component"""
    return TXT2SQLLogger.get_logger("nodes")


def get_llm_manager_logger() -> logging.Logger:
    """Get logger for LLM manager component"""
    return TXT2SQLLogger.get_logger("llm_manager")


def get_api_logger() -> logging.Logger:
    """Get logger for API component"""
    return TXT2SQLLogger.get_logger("api")


def get_cli_logger() -> logging.Logger:
    """Get logger for CLI component"""
    return TXT2SQLLogger.get_logger("cli")


def get_orchestrator_logger() -> logging.Logger:
    """Get logger for orchestrator component"""
    return TXT2SQLLogger.get_logger("orchestrator")


# Generic access for dynamic component names (module-level API)
def get_logger(component: str) -> logging.Logger:
    """Get logger for an arbitrary component name.

    Wrapper to keep compatibility with call sites that import
    `get_logger` from this module.
    """
    return TXT2SQLLogger.get_logger(component)


# Setup logging on module import
def setup_default_logging():
    """Setup default logging configuration"""
    TXT2SQLLogger.setup_logging(
        log_level="INFO",
        log_dir="logs",
        max_bytes=100 * 1024 * 1024,  # 100MB
        backup_count=10,
        enable_console=True,
        enable_file=True,
        json_format=False,
    )


# Auto-setup for production
if __name__ != "__main__":
    # Only setup if running as module, not as script
    setup_default_logging()
