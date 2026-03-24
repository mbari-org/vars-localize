"""Application-wide Loguru configuration helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger


def configure_logging() -> None:
    """Configure Loguru sinks and formatting for the application."""
    logger.remove()

    log_level = os.getenv("VARS_LOCALIZE_LOG_LEVEL", "INFO").upper()
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "| <level>{level: <8}</level> "
            "| <cyan>{extra[module]}</cyan> "
            "| <level>{message}</level>"
        ),
        backtrace=False,
        diagnose=False,
    )

    log_file = Path(os.getenv("VARS_LOCALIZE_LOG_FILE", "vars-localize.log"))
    logger.add(
        log_file,
        level=log_level,
        rotation="5 MB",
        retention=5,
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[module]} | {message}",
        backtrace=True,
        diagnose=False,
    )


def get_logger(module: str):
    """Return a logger bound to a module name.

    Args:
        module: Human-readable module/component name.

    Returns:
        Bound Loguru logger.
    """
    return logger.bind(module=module)
