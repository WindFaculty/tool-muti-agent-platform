from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import Settings

LOGGER_NAME = "assistant"
LOG_FILE_NAME = "assistant.log"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def app_log_path(settings: Settings) -> Path:
    return settings.log_dir / LOG_FILE_NAME


def configure_logging(settings: Settings) -> Path:
    settings.ensure_directories()
    log_path = app_log_path(settings)
    logger = logging.getLogger(LOGGER_NAME)
    current_path = getattr(logger, "_assistant_log_path", None)
    if getattr(logger, "_assistant_configured", False) and current_path == str(log_path):
        return log_path
    if getattr(logger, "_assistant_configured", False):
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger._assistant_configured = True  # type: ignore[attr-defined]
    logger._assistant_log_path = str(log_path)  # type: ignore[attr-defined]
    logger.info("Backend logging configured at %s", log_path)
    return log_path


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
