"""Structured logging configuration."""

from __future__ import annotations

import logging
from typing import Any


def configure_logging(level: str) -> None:
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
        "%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(numeric_level)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = " ".join([f"{key}={value}" for key, value in fields.items()])
    logger.info("event=%s %s", event, payload.strip())
