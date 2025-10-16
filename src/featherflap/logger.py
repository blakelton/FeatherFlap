"""Centralised logging utilities for FeatherFlap."""

from __future__ import annotations

import logging
from typing import Optional

from .config import AppSettings, get_settings

LOGGER_NAME = "featherflap"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _LevelToggleFilter(logging.Filter):
    """Filter log records based on AppSettings level toggles."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if record.levelno >= logging.ERROR:
            return self._settings.log_error_enabled
        if record.levelno >= logging.WARNING:
            return self._settings.log_warning_enabled
        if record.levelno >= logging.INFO:
            return self._settings.log_info_enabled
        return self._settings.log_debug_enabled

    def update(self, settings: AppSettings) -> None:
        self._settings = settings


_configured = False
_filter: Optional[_LevelToggleFilter] = None


def configure_logging(settings: Optional[AppSettings] = None, *, force: bool = False) -> None:
    """Configure the shared FeatherFlap logger."""

    global _configured, _filter
    settings = settings or get_settings()
    logger = logging.getLogger(LOGGER_NAME)

    if _configured and not force:
        if _filter:
            _filter.update(settings)
        return

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))

    _filter = _LevelToggleFilter(settings)
    handler.addFilter(_filter)

    logger.addHandler(handler)
    logger.propagate = False
    logging.captureWarnings(True)

    _configured = True


def refresh_logging(settings: Optional[AppSettings] = None) -> None:
    """Refresh the logging configuration with updated settings."""

    if settings is None:
        settings = get_settings()
    configure_logging(settings=settings, force=False)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger scoped under the FeatherFlap namespace."""

    configure_logging()
    if not name or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
