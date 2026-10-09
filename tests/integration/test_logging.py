"""Integration tests for persistent application logging (AUD-063, TD-023, #405).

Verifies that handled errors and warnings emitted across application components
reach the persistent app.log file in the user data directory.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.core.logging_config import (
    reset_logging,
    setup_logging,
)
from open_garden_planner.ui.theme import ThemeMode, _theme_listeners, apply_theme


@pytest.fixture(autouse=True)
def clean_logging() -> Any:
    reset_logging()
    yield
    reset_logging()


def test_handled_component_errors_reach_app_log(
    tmp_path: Path, qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Handled component failures (such as a failing theme listener) are written to app.log.

    This verifies the end-to-end contract that no handled warning or error is silently
    swallowed without reaching persistent storage.
    """
    log_file = setup_logging(log_dir=tmp_path, level=logging.INFO)

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Register a deliberately failing listener to trigger logger.exception() in apply_theme()
    error_called: list[bool] = []

    def failing_listener(colors: dict[str, str]) -> None:
        error_called.append(True)
        raise RuntimeError("Simulated listener crash for logging integration test")

    _theme_listeners.append(failing_listener)
    try:
        # Applying theme should handle the exception gracefully without aborting
        apply_theme(app, ThemeMode.DARK)
        assert len(error_called) == 1
    finally:
        _theme_listeners.remove(failing_listener)

    # Verify that the exception traceback was logged to app.log
    content = log_file.read_text(encoding="utf-8")
    assert "Theme listener failed" in content
    assert "RuntimeError: Simulated listener crash for logging integration test" in content


def test_handled_project_warnings_reach_app_log(
    tmp_path: Path, qtbot: Any
) -> None:
    """Project-level handled warnings reach app.log."""
    log_file = setup_logging(log_dir=tmp_path, level=logging.INFO)

    project_logger = logging.getLogger("open_garden_planner.core.project")
    project_logger.warning("Simulated project warning for test")

    content = log_file.read_text(encoding="utf-8")
    assert "[WARNING] open_garden_planner.core.project: Simulated project warning for test" in content
