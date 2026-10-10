"""Tests for core logging configuration (AUD-063, TD-023, #405).

Verifies that handled errors, warnings, and messages reach persistent rotating
disk files even under the windowed frozen executable condition (sys.stderr is None).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.core.logging_config import (
    OgpConsoleHandler,
    OgpRotatingFileHandler,
    reset_logging,
    resolve_log_dir,
    setup_logging,
)


@pytest.fixture(autouse=True)
def clean_logging() -> Any:
    """Ensure logging is reset before and after every test."""
    reset_logging()
    yield
    reset_logging()


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    """setup_logging creates app.log in the specified directory."""
    log_file = setup_logging(log_dir=tmp_path)
    assert log_file == tmp_path / "app.log"
    assert log_file.exists()


def test_handled_logs_written_to_app_log(tmp_path: Path) -> None:
    """Handled log records at INFO, WARNING, and ERROR reach app.log."""
    log_file = setup_logging(log_dir=tmp_path, level=logging.INFO)

    test_logger = logging.getLogger("open_garden_planner.test_module")
    test_logger.info("Informational message 12345")
    test_logger.warning("Warning message 67890")
    test_logger.error("Error message 11223")

    content = log_file.read_text(encoding="utf-8")
    assert "[INFO] open_garden_planner.test_module: Informational message 12345" in content
    assert "[WARNING] open_garden_planner.test_module: Warning message 67890" in content
    assert "[ERROR] open_garden_planner.test_module: Error message 11223" in content


def test_windowed_exe_condition_sys_stderr_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When sys.stderr is None (windowed exe / #291 condition), no console handler is attached.

    Handled errors still write to app.log without crashing or dropping records.
    """
    monkeypatch.setattr("sys.stderr", None)

    log_file = setup_logging(log_dir=tmp_path, level=logging.INFO)

    root = logging.getLogger()
    console_handlers = [h for h in root.handlers if isinstance(h, OgpConsoleHandler)]
    assert len(console_handlers) == 0

    file_handlers = [h for h in root.handlers if isinstance(h, OgpRotatingFileHandler)]
    assert len(file_handlers) == 1

    # Log handled warning and error under sys.stderr is None
    test_logger = logging.getLogger("open_garden_planner.windowed_test")
    test_logger.warning("Handled warning with sys.stderr=None")
    test_logger.error("Handled error with sys.stderr=None")

    content = log_file.read_text(encoding="utf-8")
    assert "Handled warning with sys.stderr=None" in content
    assert "Handled error with sys.stderr=None" in content


def test_console_handler_attached_when_stderr_is_present(tmp_path: Path) -> None:
    """When sys.stderr is available, OgpConsoleHandler is attached to root logger."""
    setup_logging(log_dir=tmp_path)
    root = logging.getLogger()
    console_handlers = [h for h in root.handlers if isinstance(h, OgpConsoleHandler)]
    assert len(console_handlers) == 1


def test_setup_logging_is_idempotent(tmp_path: Path) -> None:
    """Calling setup_logging multiple times does not duplicate handlers."""
    setup_logging(log_dir=tmp_path)
    setup_logging(log_dir=tmp_path)

    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, OgpRotatingFileHandler)]
    assert len(file_handlers) == 1


def test_log_rotation(tmp_path: Path) -> None:
    """Log file rotates when max_bytes threshold is exceeded."""
    # Small max_bytes to trigger rotation quickly
    log_file = setup_logging(
        log_dir=tmp_path,
        max_bytes=200,
        backup_count=2,
    )

    test_logger = logging.getLogger("open_garden_planner.rotation")
    for i in range(20):
        test_logger.warning("Repeated long message line number %d to trigger file rotation", i)

    backup_1 = tmp_path / "app.log.1"
    assert log_file.exists()
    assert backup_1.exists()


def test_resolve_log_dir_returns_valid_path() -> None:
    """resolve_log_dir returns an existing directory path."""
    p = resolve_log_dir()
    assert isinstance(p, Path)
    assert p.exists()


def test_resolve_log_dir_fallbacks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """resolve_log_dir falls back gracefully when QStandardPaths is unavailable."""
    from PyQt6.QtCore import QStandardPaths

    # 1. When QStandardPaths returns empty string, falls back to APPDATA on Windows
    monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _loc: "")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "mock_appdata"))
    p_appdata = resolve_log_dir()
    assert p_appdata == tmp_path / "mock_appdata" / "cofade" / "Open Garden Planner"
    assert p_appdata.exists()

    # 2. When APPDATA is also missing or empty, falls back to Path.home() / .open_garden_planner
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "mock_home")
    p_home = resolve_log_dir()
    assert p_home == tmp_path / "mock_home" / ".open_garden_planner"
    assert p_home.exists()


def test_setup_logging_relative_dir_deduplication(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """setup_logging resolves relative log_dir so idempotent deduplication works."""
    monkeypatch.chdir(tmp_path)
    rel_dir = Path("relative_logs")

    path1 = setup_logging(log_dir=rel_dir)
    assert path1.is_absolute()
    assert (tmp_path / "relative_logs" / "app.log").exists()

    # Calling again with the same relative path should not duplicate handlers
    path2 = setup_logging(log_dir=rel_dir)
    assert path1 == path2
    root_logger = logging.getLogger()
    ogp_handlers = [h for h in root_logger.handlers if getattr(h, "_ogp_managed", False)]
    file_handlers = [h for h in ogp_handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
