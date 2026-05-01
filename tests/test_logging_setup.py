import logging
import logging.handlers

from src.utils.logging_setup import LoggingSetup


def test_configure_orchestrator_logger_sets_debug_level_for_non_production():
    logger = logging.getLogger("tests.logging_setup.debug")
    logger.handlers.clear()

    configured = LoggingSetup.configure_orchestrator_logger(
        "development",
        logger=logger,
    )

    assert configured.level == logging.DEBUG
    assert configured is logger


def test_ensure_production_file_handler_is_idempotent(tmp_path):
    logger = logging.getLogger("tests.logging_setup.production")
    logger.handlers.clear()

    LoggingSetup.ensure_production_file_handler(
        logger,
        log_dir=str(tmp_path),
        filename="orchestrator.log",
    )
    LoggingSetup.ensure_production_file_handler(
        logger,
        log_dir=str(tmp_path),
        filename="orchestrator.log",
    )

    handlers = [
        handler
        for handler in logger.handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]
    assert len(handlers) == 1
    assert handlers[0].baseFilename.endswith("orchestrator.log")
