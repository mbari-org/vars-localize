"""Application-wide Loguru configuration helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

_DEBUG_INPUT_ENABLED = False


def configure_logging(debug_input: bool = False) -> None:
    """Configure Loguru sinks and formatting for the application.

    Args:
        debug_input: Enable verbose mouse/dialog/SAM-async lifecycle
            diagnostics (see `debug_input_enabled`) and force DEBUG-level
            logging for this run, regardless of VARS_LOCALIZE_LOG_LEVEL.
    """
    global _DEBUG_INPUT_ENABLED
    _DEBUG_INPUT_ENABLED = (
        bool(debug_input) or os.getenv("VARS_LOCALIZE_DEBUG_INPUT") == "1"
    )

    logger.remove()

    log_level = (
        "DEBUG"
        if _DEBUG_INPUT_ENABLED
        else os.getenv("VARS_LOCALIZE_LOG_LEVEL", "INFO").upper()
    )
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

    # Qt (and PyQt6 in particular) swallows exceptions raised inside a Python
    # override of a C++ virtual method (event handlers, slots, paint(), etc.):
    # by default it prints to stderr via sys.excepthook and returns control to
    # C++ as if nothing happened, potentially leaving Qt's internal state
    # (e.g. mouse grab bookkeeping) half-updated. On a packaged/GUI-launched
    # app (no visible terminal, notably on macOS) that default printing may
    # never be seen by anyone. Route it into the same log sinks above so it's
    # never silently lost again.
    _install_exception_logging()


def _install_exception_logging() -> None:
    def _log_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.bind(module="Uncaught").opt(
            exception=(exc_type, exc_value, exc_traceback)
        ).error(
            "Unhandled exception (Qt likely swallowed this at the C++/Python "
            "boundary and continued running): {}",
            exc_value,
        )

    sys.excepthook = _log_uncaught_exception


def debug_input_enabled() -> bool:
    """Whether verbose input/dialog/SAM-async diagnostics are enabled.

    Controlled by the `--debug-input` CLI flag or the
    VARS_LOCALIZE_DEBUG_INPUT=1 environment variable. Intended for
    diagnosing input-freeze-style bugs (see mbari-org/vars-feedback#317);
    produces very verbose DEBUG-level output, including on every mouse move.
    """
    return _DEBUG_INPUT_ENABLED


def get_logger(module: str):
    """Return a logger bound to a module name.

    Args:
        module: Human-readable module/component name.

    Returns:
        Bound Loguru logger.
    """
    return logger.bind(module=module)
