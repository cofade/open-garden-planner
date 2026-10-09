"""Application logging configuration for Open Garden Planner (AUD-063, TD-023, #405).

Ensures handled errors, warnings, and diagnostic information reach a persistent
rotating log file in the user data directory, including in the windowed frozen
executable where ``sys.stderr is None``.
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Any, ClassVar

LOG_FILENAME = "app.log"
DEFAULT_MAX_BYTES = 1_000_000  # 1 MB
DEFAULT_BACKUP_COUNT = 3

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_CONSOLE_FORMAT = "%(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class OgpRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Marker subclass to identify Open Garden Planner file handlers."""

    _ogp_managed: ClassVar[bool] = True


class OgpConsoleHandler(logging.StreamHandler[Any]):
    """Marker subclass to identify Open Garden Planner console handlers."""

    _ogp_managed: ClassVar[bool] = True


def resolve_log_dir() -> Path:
    """Resolve the directory for persistent log files.

    Uses ``QStandardPaths.StandardLocation.AppDataLocation`` when PyQt6 is
    available and configured, matching ``crash.log`` in ``main.py``. Falls back
    to platform-specific application data locations or ``~/.open_garden_planner``
    in headless environments.
    """
    with contextlib.suppress(Exception):
        from PyQt6.QtCore import QStandardPaths

        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if base:
            p = Path(base)
            p.mkdir(parents=True, exist_ok=True)
            return p

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            p = Path(appdata) / "cofade" / "Open Garden Planner"
            p.mkdir(parents=True, exist_ok=True)
            return p

    p = Path.home() / ".open_garden_planner"
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_logging(
    log_dir: Path | None = None,
    level: int = logging.INFO,
    console_level: int = logging.WARNING,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> Path:
    """Configure the root logger with a rotating file handler and optional console output.

    Parameters:
        log_dir: Directory where ``app.log`` should be written. If None, resolves
            via ``resolve_log_dir()``.
        level: Minimum log level for the persistent rotating file handler.
        console_level: Minimum log level for the stderr console handler.
        max_bytes: Maximum size of each log file before rotation.
        backup_count: Number of rotated backup files to keep.

    Returns:
        The Path to the active ``app.log`` file.
    """
    target_dir = log_dir or resolve_log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = (target_dir / LOG_FILENAME).resolve()

    root_logger = logging.getLogger()

    # If an OGP file handler already exists pointing to the same file, do not duplicate.
    for handler in list(root_logger.handlers):
        if (
            getattr(handler, "_ogp_managed", False)
            and isinstance(handler, OgpRotatingFileHandler)
            and Path(handler.baseFilename).resolve() == log_path
        ):
            return log_path

    # Set root logger level to allow INFO records through to handlers
    if root_logger.level == logging.NOTSET or root_logger.level > level:
        root_logger.setLevel(level)

    # Persistent rotating file handler (UTF-8 encoded)
    file_handler = OgpRotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    )
    root_logger.addHandler(file_handler)

    # Console stream handler ONLY when sys.stderr is a valid stream (issue #291 condition)
    if sys.stderr is not None:
        console_handler = OgpConsoleHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
        root_logger.addHandler(console_handler)

    return log_path


def reset_logging() -> None:
    """Flush, close, and remove all OGP-managed handlers from the root logger.

    Primarily used in unit tests to ensure test isolation.
    """
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if getattr(handler, "_ogp_managed", False):
            handler.flush()
            handler.close()
            root_logger.removeHandler(handler)
