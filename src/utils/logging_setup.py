import logging
import logging.handlers
import os
from typing import Optional

from .logging_config import get_orchestrator_logger


class LoggingSetup:
    """Configures orchestrator logging without embedding setup details in the orchestrator."""

    @staticmethod
    def configure_orchestrator_logger(
        environment: str,
        logger: Optional[logging.Logger] = None,
    ) -> logging.Logger:
        configured_logger = logger or get_orchestrator_logger()
        log_level = logging.INFO if environment == "production" else logging.DEBUG
        configured_logger.setLevel(log_level)

        if environment == "production":
            LoggingSetup.ensure_production_file_handler(configured_logger)

        return configured_logger

    @staticmethod
    def ensure_production_file_handler(
        logger: logging.Logger,
        *,
        log_dir: str = "logs",
        filename: str = "orchestrator_v3.log",
        max_bytes: int = 100 * 1024 * 1024,
        backup_count: int = 10,
    ) -> None:
        has_rotating_handler = any(
            isinstance(handler, logging.handlers.RotatingFileHandler)
            for handler in logger.handlers
        )
        if has_rotating_handler:
            return

        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, filename),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
