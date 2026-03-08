"""Pytest configuration and fixtures."""

import os
import sys
from pathlib import Path

import pytest

# Force Qt offscreen rendering before any Qt imports so no windows pop up.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(autouse=True, scope="session")
def isolate_qsettings():
    """Redirect QSettings to a test-only registry key for the entire test session.

    This prevents tests from polluting the real user settings (e.g. recent files).
    The test key is cleared at the end of the session.
    """
    from PyQt6.QtCore import QSettings

    def _test_init(self: object) -> None:
        self._settings = QSettings("cofade_test", "Open Garden Planner Test")  # type: ignore[attr-defined]

    import open_garden_planner.app.settings as settings_module

    original_init = settings_module.AppSettings.__init__
    settings_module.AppSettings.__init__ = _test_init  # type: ignore[method-assign]

    # Also reset the module-level singleton so a fresh test instance is created
    settings_module._settings_instance = None  # type: ignore[attr-defined]

    yield

    # Clean up: clear the test registry key and restore original init
    QSettings("cofade_test", "Open Garden Planner Test").clear()
    settings_module.AppSettings.__init__ = original_init  # type: ignore[method-assign]
    settings_module._settings_instance = None  # type: ignore[attr-defined]
